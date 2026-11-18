"""
PEMS08 training and evaluation pipeline.

Kept entirely separate from ml/training/train_models.py (Metro) — different dataset,
different sensor structure, different target. See ml/preprocessing/pems08_features.py
for the full feature/target construction and its own leakage tests.

TWO TASKS in this file:
  PART 1: Regression on target_speed (same sensor's speed at T+1h)
  PART 2: Classification on target_congestion_1h (existing thresholds, NOT changed here)

KNOWN, UNRESOLVED ISSUE (not fixed here, not hidden): target_congestion_1h is severely
imbalanced (LOW ~95.8%, MEDIUM ~2.9%, HIGH ~1.2%, SEVERE ~0.14%), because PEMS08's
speed distribution is naturally tight around a high value on this stretch of freeway.
This run reports that reality — including how it degrades SEVERE-class detection —
rather than presenting only accuracy, which would be misleading given the imbalance.

Run: python -m ml.training.train_pems08_models
"""
import json
import os
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report,
)
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from ml.preprocessing.pems08_features import run as preprocess_pems08, FEATURE_COLUMNS, TARGET_COLUMN, AUDIT_COLUMNS

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "pems08")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "pems08")

CONGESTION_LABELS = ["LOW", "MEDIUM", "HIGH", "SEVERE"]


# ============================================================
# PART 3 — Leakage protection: explicit assertions run BEFORE training
# ============================================================
def assert_no_leakage(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame):
    """
    Re-verifies the leakage properties already established by pems08_features.py's own
    test suite, but re-asserted HERE, right before training, as a second independent
    gate — so this trainer never silently trusts an upstream change it didn't re-check.
    Raises AssertionError with a clear message and stops immediately if anything fails.
    """
    forbidden = set(AUDIT_COLUMNS + [TARGET_COLUMN])
    leaked = forbidden & set(FEATURE_COLUMNS)
    assert not leaked, f"LEAKAGE: target/audit columns present in FEATURE_COLUMNS: {leaked}"

    for name, df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        gap = df["target_timestamp"] - df["timestamp"]
        assert (gap == pd.Timedelta(hours=1)).all(), f"LEAKAGE: {name} split has rows where target != T+1h"

    assert train_df["target_timestamp"].max() < val_df["target_timestamp"].min(), \
        "LEAKAGE: train/validation target timestamps overlap"
    assert val_df["target_timestamp"].max() < test_df["target_timestamp"].min(), \
        "LEAKAGE: validation/test target timestamps overlap"

    print("Leakage assertions passed: no target/audit columns in features, "
          "target is exactly T+1h in every split, chronological ordering holds train < val < test.")


def build_pipeline(estimator) -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", estimator)])


# ============================================================
# PART 1 — Regression: predict target_speed
# ============================================================
def evaluate_regression(pipeline: Pipeline, df: pd.DataFrame, split_name: str) -> dict:
    X = df[FEATURE_COLUMNS]
    y_true = df["target_speed"]
    y_pred = pipeline.predict(X)

    return {
        "split": split_name,
        "n_samples": len(df),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def run_regression(train_df, val_df, test_df) -> dict:
    print("\n=== PART 1: REGRESSION (target_speed) ===")
    models = {
        "baseline_linear_regression": LinearRegression(),
        "random_forest_regressor": RandomForestRegressor(
            # Config reduced from a more typical 200-tree/depth-12 setup due to a MEASURED
            # constraint of this sandbox: only 1 CPU core (confirmed via nproc), and a
            # hard 300-second-per-command execution limit discovered during this run.
            # Benchmarked: 20 trees/depth=8/min_samples_leaf=500 on the FULL 2.12M-row
            # train set completes in ~189s. This trains on the complete training set,
            # not a subsample — only the ensemble size/depth were reduced.
            n_estimators=20, max_depth=8, min_samples_leaf=500, random_state=42, n_jobs=1
        ),
    }

    results = {}
    for name, estimator in models.items():
        print(f"Training {name}...")
        pipeline = build_pipeline(estimator)
        t0 = time.time()
        pipeline.fit(train_df[FEATURE_COLUMNS], train_df["target_speed"])
        train_time = round(time.time() - t0, 2)

        val_metrics = evaluate_regression(pipeline, val_df, "validation")
        test_metrics = evaluate_regression(pipeline, test_df, "test")
        print(f"  {name}: val MAE={val_metrics['mae']} RMSE={val_metrics['rmse']} R2={val_metrics['r2']}")
        print(f"  {name}: test MAE={test_metrics['mae']} RMSE={test_metrics['rmse']} R2={test_metrics['r2']}")

        model_path = os.path.join(MODELS_DIR, f"pems08_speed_{'baseline' if 'baseline' in name else 'random_forest'}.joblib")
        joblib.dump(pipeline, model_path)

        results[name] = {
            "training_time_sec": train_time,
            "validation": val_metrics,
            "test": test_metrics,
            "model_path": model_path,
        }

    # Extra, non-required sanity check: a trivial "persistence" baseline (predict T+1h
    # speed = current speed at T). This is NOT one of the two required models — it's
    # included because a forecasting model should be able to beat "assume nothing changes",
    # and reporting this context is more honest than accuracy/MAE numbers alone.
    persistence_pred_test = test_df["speed"]
    persistence_mae = float(mean_absolute_error(test_df["target_speed"], persistence_pred_test))
    persistence_rmse = float(np.sqrt(mean_squared_error(test_df["target_speed"], persistence_pred_test)))
    persistence_r2 = float(r2_score(test_df["target_speed"], persistence_pred_test))
    results["_persistence_baseline_context_only"] = {
        "note": "NOT one of the two required models - a trivial 'predict no change' reference point",
        "test": {"mae": round(persistence_mae, 4), "rmse": round(persistence_rmse, 4), "r2": round(persistence_r2, 4)},
    }
    print(f"  (context) persistence baseline: test MAE={round(persistence_mae,4)} RMSE={round(persistence_rmse,4)} R2={round(persistence_r2,4)}")

    return results


# ============================================================
# PART 2 — Classification: predict target_congestion_1h
# ============================================================
def evaluate_classification(pipeline: Pipeline, df: pd.DataFrame, split_name: str) -> dict:
    X = df[FEATURE_COLUMNS]
    y_true = df[TARGET_COLUMN].astype(str)
    y_pred = pipeline.predict(X)

    acc = accuracy_score(y_true, y_pred)
    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0, labels=CONGESTION_LABELS
    )
    _, _, f1_weighted, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0, labels=CONGESTION_LABELS
    )
    precision_per, recall_per, f1_per, support_per = precision_recall_fscore_support(
        y_true, y_pred, average=None, zero_division=0, labels=CONGESTION_LABELS
    )
    cm = confusion_matrix(y_true, y_pred, labels=CONGESTION_LABELS)

    per_class = {
        label: {
            "precision": round(float(precision_per[i]), 4),
            "recall": round(float(recall_per[i]), 4),
            "f1": round(float(f1_per[i]), 4),
            "support": int(support_per[i]),
        }
        for i, label in enumerate(CONGESTION_LABELS)
    }

    return {
        "split": split_name,
        "n_samples": len(df),
        "accuracy": round(float(acc), 4),
        "precision_macro": round(float(precision_macro), 4),
        "recall_macro": round(float(recall_macro), 4),
        "f1_macro": round(float(f1_macro), 4),
        "f1_weighted": round(float(f1_weighted), 4),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": CONGESTION_LABELS,
        "classification_report": classification_report(y_true, y_pred, labels=CONGESTION_LABELS, zero_division=0),
    }


def run_classification(train_df, val_df, test_df) -> dict:
    print("\n=== PART 2: CLASSIFICATION (target_congestion_1h) ===")
    print("Class distribution (train):")
    print((train_df[TARGET_COLUMN].value_counts(normalize=True) * 100).round(2))

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest_classifier": RandomForestClassifier(
            # Same measured single-core / 300s-per-command constraint as the regressor above.
            n_estimators=20, max_depth=8, min_samples_leaf=500, random_state=42, n_jobs=1, class_weight="balanced"
        ),
    }

    results = {}
    for name, estimator in models.items():
        print(f"Training {name} (class_weight='balanced')...")
        pipeline = build_pipeline(estimator)
        t0 = time.time()
        pipeline.fit(train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN].astype(str))
        train_time = round(time.time() - t0, 2)

        val_metrics = evaluate_classification(pipeline, val_df, "validation")
        test_metrics = evaluate_classification(pipeline, test_df, "test")
        print(f"  {name}: val acc={val_metrics['accuracy']} macro-F1={val_metrics['f1_macro']} "
              f"SEVERE recall={val_metrics['per_class']['SEVERE']['recall']}")
        print(f"  {name}: test acc={test_metrics['accuracy']} macro-F1={test_metrics['f1_macro']} "
              f"SEVERE recall={test_metrics['per_class']['SEVERE']['recall']}")

        model_path = os.path.join(MODELS_DIR, f"pems08_congestion_{'logistic' if 'logistic' in name else 'random_forest'}.joblib")
        joblib.dump(pipeline, model_path)

        results[name] = {
            "training_time_sec": train_time,
            "validation": {k: v for k, v in val_metrics.items() if k != "classification_report"},
            "test": {k: v for k, v in test_metrics.items() if k != "classification_report"},
            "model_path": model_path,
        }

        with open(os.path.join(REPORTS_DIR, f"{name}_classification_report.txt"), "w") as f:
            f.write(f"=== {name} - VALIDATION ===\n{val_metrics['classification_report']}\n")
            f.write(f"\n=== {name} - TEST ===\n{test_metrics['classification_report']}\n")

    return results


def run():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    t_start = time.time()
    print("Loading PEMS08 preprocessed data...")
    df, free_flow_thresholds, split_idx, prep_stats = preprocess_pems08(verbose=False)

    train_df = df.iloc[:split_idx["train_end_idx"]]
    val_df = df.iloc[split_idx["train_end_idx"]:split_idx["val_end_idx"]]
    test_df = df.iloc[split_idx["val_end_idx"]:]
    print(f"Train: {len(train_df):,}  Val: {len(val_df):,}  Test: {len(test_df):,}")

    assert_no_leakage(train_df, val_df, test_df)

    regression_results = run_regression(train_df, val_df, test_df)
    classification_results = run_classification(train_df, val_df, test_df)

    total_elapsed = round(time.time() - t_start, 2)

    # Model selection - VALIDATION metrics only, never test (Part 3, requirement 8)
    reg_candidates = {k: v for k, v in regression_results.items() if not k.startswith("_")}
    best_regressor = min(reg_candidates, key=lambda k: reg_candidates[k]["validation"]["mae"])
    best_classifier = max(classification_results, key=lambda k: classification_results[k]["validation"]["f1_macro"])
    print(f"\nSelected regressor (lowest validation MAE): {best_regressor}")
    print(f"Selected classifier (highest validation macro-F1): {best_classifier}")

    comparison = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "PEMS08 (real, see docs/DATASETS.md)",
        "prediction_horizon": "+60 minutes (12 five-minute steps) - same sensor, exact T+1h target",
        "data": {
            "raw_timestamps": 17856,
            "raw_sensors": 170,
            "raw_sensor_time_rows": prep_stats["long_df_rows"],
            "dropped_incomplete_lag_history": prep_stats["dropped_lag_incomplete_only"],
            "dropped_no_valid_target": prep_stats["dropped_no_target_only"],
            "trainable_rows": prep_stats["trainable_rows"],
            "train_rows": len(train_df),
            "val_rows": len(val_df),
            "test_rows": len(test_df),
        },
        "known_label_imbalance": {
            "note": "target_congestion_1h is severely imbalanced - NOT fixed by changing thresholds, reported honestly",
            "train_distribution_pct": (train_df[TARGET_COLUMN].value_counts(normalize=True) * 100).round(2).to_dict(),
        },
        "feature_columns": FEATURE_COLUMNS,
        "regression": {k: v for k, v in regression_results.items()},
        "classification": classification_results,
        "selected_regressor": best_regressor,
        "selected_classifier": best_classifier,
        "selection_criterion": "regressor: lowest validation MAE. classifier: highest validation macro-F1. Test set used only for final reporting, never selection.",
        "total_elapsed_sec": total_elapsed,
    }

    with open(os.path.join(REPORTS_DIR, "model_comparison.json"), "w") as f:
        json.dump(comparison, f, indent=2, default=str)

    with open(os.path.join(REPORTS_DIR, "regression_report.json"), "w") as f:
        json.dump({k: v for k, v in regression_results.items()}, f, indent=2, default=str)

    with open(os.path.join(REPORTS_DIR, "classification_report.json"), "w") as f:
        json.dump(classification_results, f, indent=2, default=str)

    with open(os.path.join(REPORTS_DIR, "confusion_matrix.json"), "w") as f:
        cm_out = {
            name: {
                "labels": CONGESTION_LABELS,
                "validation": classification_results[name]["validation"]["confusion_matrix"],
                "test": classification_results[name]["test"]["confusion_matrix"],
            }
            for name in classification_results
        }
        json.dump(cm_out, f, indent=2, default=str)

    # Feature importance for the Random Forest models (both regression and classification)
    rf_reg_pipeline = joblib.load(os.path.join(MODELS_DIR, "pems08_speed_random_forest.joblib"))
    rf_clf_pipeline = joblib.load(os.path.join(MODELS_DIR, "pems08_congestion_random_forest.joblib"))
    feature_importance = {
        "random_forest_regressor": dict(zip(FEATURE_COLUMNS, rf_reg_pipeline.named_steps["model"].feature_importances_.round(4).tolist())),
        "random_forest_classifier": dict(zip(FEATURE_COLUMNS, rf_clf_pipeline.named_steps["model"].feature_importances_.round(4).tolist())),
    }
    with open(os.path.join(REPORTS_DIR, "feature_importance.json"), "w") as f:
        json.dump(feature_importance, f, indent=2, default=str)

    # Model versioning
    model_versions = []
    for task_name, results_dict, target_col in [
        ("regression", reg_candidates, "target_speed"),
        ("classification", classification_results, TARGET_COLUMN),
    ]:
        for model_name, r in results_dict.items():
            model_versions.append({
                "model_id": f"pems08_{task_name}_{model_name}_v1",
                "task": task_name,
                "algorithm": model_name,
                "version": "1.0",
                "trained_at": comparison["generated_at"],
                "dataset": "PEMS08.npz (sha-verified in docs/DATASETS.md)",
                "feature_columns": FEATURE_COLUMNS,
                "target": target_col,
                "train_rows": len(train_df),
                "val_rows": len(val_df),
                "test_rows": len(test_df),
                "training_time_sec": r["training_time_sec"],
                "validation_metrics": r["validation"],
                "test_metrics": r["test"],
                "model_file": r["model_path"],
                "status": "active" if model_name in (best_regressor, best_classifier) else "trained_not_selected",
            })
    with open(os.path.join(MODELS_DIR, "model_versions.json"), "w") as f:
        json.dump(model_versions, f, indent=2, default=str)

    print(f"\nTotal elapsed: {total_elapsed}s")
    print(f"Reports written to: {REPORTS_DIR}")
    print(f"Models written to: {MODELS_DIR}")

    return comparison


if __name__ == "__main__":
    run()
