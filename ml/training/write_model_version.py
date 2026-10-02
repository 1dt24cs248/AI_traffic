"""
Module 16 — Model versioning (minimal, honest implementation).
Reads the real evaluation output from Module 5/6 and writes a version record —
it does not compute anything new, just structures what training actually produced.

Run: python -m ml.training.write_model_version   (after train_models.py has run)
"""
import json
import os
from datetime import datetime

EVAL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "model_evaluation", "model_comparison.json")
VERSION_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "model_versions.json")


def run():
    with open(EVAL_PATH) as f:
        comparison = json.load(f)

    selected = comparison["selected_model"]
    selected_metrics = comparison["models"][selected]

    version_record = {
        "model_id": f"{selected}-v1",
        "algorithm": "RandomForestClassifier" if selected == "random_forest" else "LogisticRegression",
        "version": "1.0",
        "trained_at": comparison["generated_at"],
        "dataset": comparison["dataset"],
        "dataset_version": "metro_interstate_traffic_volume.csv, sha256=749c90d720360a4215bb15345526073c079ba4cc95e3fa558796d083f85fce9e",
        "features": None,  # filled below
        "prediction_horizon": comparison["prediction_horizon"],
        "test_accuracy": selected_metrics["test"]["accuracy"],
        "test_f1_macro": selected_metrics["test"]["f1_macro"],
        "status": "active",
        "model_file": f"ml/models/{selected}.joblib (reproducible via `python -m ml.training.train_models`, not committed to the repo zip — see docs/CURRENT_STATUS.md)",
    }

    from ml.training.train_models import FEATURE_COLUMNS
    version_record["features"] = FEATURE_COLUMNS

    os.makedirs(os.path.dirname(VERSION_PATH), exist_ok=True)
    with open(VERSION_PATH, "w") as f:
        json.dump([version_record], f, indent=2)

    print(json.dumps(version_record, indent=2))
    return version_record


if __name__ == "__main__":
    run()
