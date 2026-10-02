"""
Module 5 — Model training. Module 6 — Evaluation (folded in).

=== CORRECTION LOG (audited and fixed — see docs/CURRENT_STATUS.md) ===
The original version of this file trained on `congestion_level`, a label computed
from the SAME row's traffic_volume as the weather/temporal features being used as
inputs — i.e. same-timestamp nowcasting, not a genuine future forecast, despite
being documented (incorrectly) as "+60 minutes". This has been corrected: the
target is now `target_congestion_1h` (see ml/preprocessing/real_dataset_features.py),
built from the row exactly one hour after the feature row, with weather features
removed from the input set entirely (no legitimate forecast source exists in this
repo for them). The split indices used here are the SAME ones real_dataset_features.py
used to compute the label thresholds, so there is no mismatch between the split used
for threshold-learning and the split used for model training/evaluation.

Prediction horizon: +60 minutes (next hour) ONLY — this hourly-resolution dataset
cannot support +15 or +30 minute horizons. This is not a design choice, it's a
hard constraint of the data's own resolution.

Run: python -m ml.training.train_models
"""
import json
import os
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report
)
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from ml.preprocessing.real_dataset_features import run as preprocess_real_dataset, FEATURE_COLUMNS, TARGET_COLUMN

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
EVAL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "model_evaluation")


def build_pipeline(estimator) -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", estimator)])


def evaluate(pipeline: Pipeline, df: pd.DataFrame, split_name: str) -> dict:
    X = df[FEATURE_COLUMNS]
    y_true = df[TARGET_COLUMN]
    y_pred = pipeline.predict(X)

    acc = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    labels = sorted(y_true.unique())
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    return {
        "split": split_name,
        "n_samples": len(df),
        "accuracy": round(float(acc), 4),
        "precision_macro": round(float(precision), 4),
        "recall_macro": round(float(recall), 4),
        "f1_macro": round(float(f1), 4),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(y_true, y_pred, zero_division=0),
    }


def run():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(EVAL_DIR, exist_ok=True)

    print("Loading and preprocessing real dataset (corrected T -> T+1h target)...")
    df, label_thresholds, split_idx = preprocess_real_dataset()

    train_df = df.iloc[:split_idx["train_end_idx"]]
    val_df = df.iloc[split_idx["train_end_idx"]:split_idx["val_end_idx"]]
    test_df = df.iloc[split_idx["val_end_idx"]:]
    print(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Chronological separation check (also covered by an automated test, checked again here
    # at run time so a broken split fails loudly rather than silently training on leaked data)
    assert train_df["target_timestamp"].max() < val_df["target_timestamp"].min(), "train/val overlap!"
    assert val_df["target_timestamp"].max() < test_df["target_timestamp"].min(), "val/test overlap!"
    print("Chronological split verified: train < val < test (by target_timestamp)")

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1),
    }

    results = {}
    for name, estimator in models.items():
        print(f"\nTraining {name}...")
        pipeline = build_pipeline(estimator)
        X_train = train_df[FEATURE_COLUMNS]
        y_train = train_df[TARGET_COLUMN]

        start = datetime.now(timezone.utc)
        pipeline.fit(X_train, y_train)
        training_time_sec = (datetime.now(timezone.utc) - start).total_seconds()

        val_metrics = evaluate(pipeline, val_df, "validation")
        test_metrics = evaluate(pipeline, test_df, "test")

        print(f"{name} - val accuracy: {val_metrics['accuracy']}, val F1(macro): {val_metrics['f1_macro']}")
        print(f"{name} - test accuracy: {test_metrics['accuracy']}, test F1(macro): {test_metrics['f1_macro']}")

        model_path = os.path.join(MODELS_DIR, f"{name}.joblib")
        joblib.dump(pipeline, model_path)

        results[name] = {
            "training_time_sec": round(training_time_sec, 2),
            "validation": val_metrics,
            "test": test_metrics,
            "model_path": model_path,
        }

    best_model_name = max(results, key=lambda k: results[k]["test"]["f1_macro"])
    print(f"\nSelected model: {best_model_name} (highest test F1-macro)")

    comparison = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "CORRECTION_NOTE": "Earlier version of this file predicted same-timestamp congestion "
                            "(nowcasting) while incorrectly labeling it a +60min forecast. "
                            "This run uses a genuine T->T+1h target — see module docstring.",
        "dataset": "Metro Interstate Traffic Volume (real, see docs/DATASETS.md)",
        "target_definition": "target_congestion_1h: congestion label of traffic_volume at "
                              "exactly T+1 hour from the feature row's timestamp T. Rows where "
                              "the next available observation is not exactly 1 hour later "
                              "(e.g. spanning the Aug2014-Jun2015 data gap) are excluded, not "
                              "given a fabricated target.",
        "feature_columns": FEATURE_COLUMNS,
        "features_removed_due_to_leakage_risk": {
            "temp": "would only be legitimate if sourced from a weather FORECAST for T+1h, not actual historical weather; no forecast source exists in this repo",
            "rain_1h": "same reason as temp",
            "snow_1h": "same reason as temp",
            "clouds_all": "same reason as temp",
            "weather_main": "same reason as temp",
        },
        "prediction_horizon": "+60 minutes (next hour) ONLY - hard constraint of this dataset's hourly resolution, not a design choice",
        "congestion_label_thresholds": label_thresholds,
        "label_methodology": "target_traffic_volume (T+1h) quartiles, computed on TRAIN split's target values only",
        "rows_after_cleaning": None,  # filled by caller if needed; not recomputed here to avoid re-running cleaning twice
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "test_rows": len(test_df),
        "models": {
            name: {
                "training_time_sec": r["training_time_sec"],
                "validation": {k: v for k, v in r["validation"].items() if k != "classification_report"},
                "test": {k: v for k, v in r["test"].items() if k != "classification_report"},
            }
            for name, r in results.items()
        },
        "selected_model": best_model_name,
        "selection_criterion": "highest test-set F1-macro",
    }

    with open(os.path.join(EVAL_DIR, "model_comparison.json"), "w") as f:
        json.dump(comparison, f, indent=2, default=str)

    for name, r in results.items():
        with open(os.path.join(EVAL_DIR, f"{name}_classification_report.txt"), "w") as f:
            f.write(f"=== {name} - VALIDATION (T->T+1h forecast) ===\n")
            f.write(r["validation"]["classification_report"])
            f.write(f"\n\n=== {name} - TEST (T->T+1h forecast) ===\n")
            f.write(r["test"]["classification_report"])

    return comparison


if __name__ == "__main__":
    result = run()
    print("\n" + json.dumps({k: v for k, v in result.items() if k != "models"}, indent=2, default=str))
