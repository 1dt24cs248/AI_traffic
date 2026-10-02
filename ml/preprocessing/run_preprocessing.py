"""
Module 3 — orchestration: runs load -> clean -> feature engineering -> split -> save.

Run: python -m ml.preprocessing.run_preprocessing
Reads: DATABASE_URL from ../../.env
Writes:
  ml/data/processed/train.csv
  ml/data/processed/val.csv
  ml/data/processed/test.csv
  ml/preprocessing/preprocessing_config.json
"""
import json
import os
from datetime import datetime

from ml.preprocessing.data_loader import load_traffic_records
from ml.preprocessing.clean import clean_pipeline
from ml.preprocessing.features import feature_engineering_pipeline, CONGESTION_BINS, CONGESTION_LABELS
from ml.preprocessing.split import time_based_split, split_summary

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "preprocessing_config.json")

LAG_WINDOW = 3


def run(database_url: str | None = None) -> dict:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    raw = load_traffic_records(database_url)
    if raw.empty:
        raise ValueError(
            "No traffic_records found in the database. "
            "Upload data via POST /api/traffic/upload first (Module 2)."
        )

    cleaned = clean_pipeline(raw)
    featured = feature_engineering_pipeline(cleaned, lag_window=LAG_WINDOW)

    # Rows with no lag history yet (the first observation per road) can't be used for
    # training a next-step predictor — they're real rows, but not valid training examples.
    trainable = featured.dropna(subset=["previous_speed", "previous_vehicle_count"]).copy()

    train_df, val_df, test_df = time_based_split(trainable)

    train_df.to_csv(os.path.join(OUTPUT_DIR, "train.csv"), index=False)
    val_df.to_csv(os.path.join(OUTPUT_DIR, "val.csv"), index=False)
    test_df.to_csv(os.path.join(OUTPUT_DIR, "test.csv"), index=False)

    config = {
        "generated_at": datetime.utcnow().isoformat(),
        "raw_rows": len(raw),
        "rows_after_cleaning": len(cleaned),
        "rows_after_dropping_no_lag_history": len(trainable),
        "lag_window": LAG_WINDOW,
        "congestion_label_method": {
            "basis": "average_speed / road's own 95th-percentile speed (free-flow proxy)",
            "bin_edges": [str(b) for b in CONGESTION_BINS],
            "labels_low_to_severe": list(reversed(CONGESTION_LABELS)),
        },
        "temporal_features": ["hour", "minute", "day_of_week", "month", "is_weekend", "is_rush_hour"],
        "lag_features": ["previous_vehicle_count", "previous_speed", "previous_congestion_level"],
        "rolling_features": ["rolling_average_speed", "rolling_average_vehicle_count"],
        "split_method": "chronological (70/15/15), not random shuffle — see split.py docstring",
        "split_summary": split_summary(train_df, val_df, test_df),
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, default=str)

    return config


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
