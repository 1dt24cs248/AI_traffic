"""
Tests for the PEMS08 training pipeline's leakage protection (Part 3) and reporting
integrity. Does NOT retrain models (too slow for a test suite in this sandbox -
~6.5 minutes measured) - instead validates assert_no_leakage() directly against
real preprocessing output, and validates the already-written report files for
structural correctness (model selection used validation, not test, metrics).

Run: pytest ml/tests/test_pems08_training.py -v
"""
import json
import os
import pytest

from ml.preprocessing.pems08_features import run as preprocess_pems08
from ml.training.train_pems08_models import assert_no_leakage, FEATURE_COLUMNS, TARGET_COLUMN

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "pems08")


@pytest.fixture(scope="module")
def split_data():
    df, thresholds, split_idx, stats = preprocess_pems08(verbose=False)
    train_df = df.iloc[:split_idx["train_end_idx"]]
    val_df = df.iloc[split_idx["train_end_idx"]:split_idx["val_end_idx"]]
    test_df = df.iloc[split_idx["val_end_idx"]:]
    return train_df, val_df, test_df


def test_assert_no_leakage_passes_on_real_data(split_data):
    """The trainer's own leakage gate must pass without raising on real preprocessed data."""
    train_df, val_df, test_df = split_data
    assert_no_leakage(train_df, val_df, test_df)  # raises AssertionError if it fails


def test_assert_no_leakage_catches_injected_overlap(split_data):
    """
    The leakage gate must actually DETECT a violation, not just pass silently on
    correct data - verified by deliberately injecting a fake overlap and confirming
    assert_no_leakage raises.
    """
    train_df, val_df, test_df = split_data
    broken_val = val_df.copy()
    broken_val.loc[broken_val.index[0], "target_timestamp"] = train_df["target_timestamp"].iloc[0]
    with pytest.raises(AssertionError):
        assert_no_leakage(train_df, broken_val, test_df)


def test_assert_no_leakage_catches_feature_target_leak(split_data):
    """The leakage gate must catch target columns appearing in FEATURE_COLUMNS."""
    import ml.training.train_pems08_models as trainer_module
    original = trainer_module.FEATURE_COLUMNS
    try:
        trainer_module.FEATURE_COLUMNS = original + ["target_speed"]
        train_df, val_df, test_df = split_data
        with pytest.raises(AssertionError):
            trainer_module.assert_no_leakage(train_df, val_df, test_df)
    finally:
        trainer_module.FEATURE_COLUMNS = original


def test_model_comparison_report_exists_and_is_well_formed():
    """Structural check on the actual report written by the real training run."""
    path = os.path.join(REPORTS_DIR, "model_comparison.json")
    assert os.path.exists(path), "model_comparison.json was not written by the training run"
    with open(path) as f:
        report = json.load(f)

    assert report["selected_regressor"] in report["regression"]
    assert report["selected_classifier"] in report["classification"]
    assert "known_label_imbalance" in report, "Label imbalance must be documented in the report, not hidden"


def test_model_selection_uses_validation_not_test_metrics():
    """
    Requirement (Part 3, #8): the test set must never be used for model selection.
    Verified structurally: the selected regressor must genuinely have the lowest
    VALIDATION MAE among candidates - re-derived independently from the report,
    not just trusted from the 'selected_regressor' field.
    """
    path = os.path.join(REPORTS_DIR, "model_comparison.json")
    with open(path) as f:
        report = json.load(f)

    reg_candidates = {k: v for k, v in report["regression"].items() if not k.startswith("_")}
    best_by_val_mae = min(reg_candidates, key=lambda k: reg_candidates[k]["validation"]["mae"])
    assert report["selected_regressor"] == best_by_val_mae, \
        "selected_regressor does not match the model with the lowest VALIDATION MAE - selection may have used test data"

    best_clf_by_val_f1 = max(report["classification"], key=lambda k: report["classification"][k]["validation"]["f1_macro"])
    assert report["selected_classifier"] == best_clf_by_val_f1, \
        "selected_classifier does not match the model with the highest VALIDATION macro-F1"


def test_severe_class_metrics_present_and_reported():
    """SEVERE class metrics must be explicitly present, not omitted due to its small size."""
    path = os.path.join(REPORTS_DIR, "classification_report.json")
    with open(path) as f:
        report = json.load(f)

    for model_name, result in report.items():
        for split in ["validation", "test"]:
            assert "SEVERE" in result[split]["per_class"], \
                f"{model_name}/{split} is missing SEVERE class metrics"
            severe = result[split]["per_class"]["SEVERE"]
            assert "precision" in severe and "recall" in severe and "support" in severe


def test_model_artifacts_exist():
    """All four required model files must exist on disk with non-trivial size."""
    models_dir = os.path.join(os.path.dirname(__file__), "..", "models", "pems08")
    expected = [
        "pems08_speed_baseline.joblib",
        "pems08_speed_random_forest.joblib",
        "pems08_congestion_logistic.joblib",
        "pems08_congestion_random_forest.joblib",
    ]
    for filename in expected:
        path = os.path.join(models_dir, filename)
        assert os.path.exists(path), f"Missing model artifact: {filename}"
        assert os.path.getsize(path) > 100, f"{filename} exists but is suspiciously small"
