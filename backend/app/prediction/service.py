"""
PEMS08 prediction service.

Loads the already-trained PEMS08 sklearn pipelines and performs
speed and congestion predictions using the exact 20-feature contract
used during training.
"""

from pathlib import Path
import os
from typing import Any

import joblib
import pandas as pd


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _resolve_pems08_model_dir(service_file: Path, configured_dir: str | None = None) -> Path:
    """Resolve artifacts in the source workspace or an explicitly mounted location.

    The development checkout keeps PEMS08 artifacts in the workspace parent.
    The backend container is shallower, so its Compose configuration supplies
    PEMS08_MODEL_DIR for the read-only artifact mount.
    """
    if configured_dir:
        return Path(configured_dir).expanduser().resolve()

    parents = service_file.resolve().parents
    backend_root = next((parent for parent in parents if parent.name == "backend"), None)
    project_root = backend_root.parent.parent if backend_root else parents[-1]
    return project_root / "ml" / "models" / "pems08"


PEMS08_MODEL_DIR = _resolve_pems08_model_dir(
    Path(__file__),
    os.environ.get("PEMS08_MODEL_DIR"),
)


SPEED_MODEL_PATH = PEMS08_MODEL_DIR / "pems08_speed_random_forest.joblib"
CONGESTION_MODEL_PATH = (
    PEMS08_MODEL_DIR / "pems08_congestion_random_forest.joblib"
)


# ---------------------------------------------------------------------------
# Exact feature contract used during PEMS08 training
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "flow",
    "occupancy",
    "speed",
    "flow_lag_5m",
    "flow_lag_15m",
    "flow_lag_30m",
    "flow_lag_1h",
    "speed_lag_5m",
    "speed_lag_15m",
    "speed_lag_30m",
    "speed_lag_1h",
    "occupancy_lag_5m",
    "occupancy_lag_15m",
    "occupancy_lag_30m",
    "occupancy_lag_1h",
    "hour",
    "day_of_week",
    "month",
    "is_weekend",
    "is_rush_hour",
]


# ---------------------------------------------------------------------------
# Lazy model loading
# ---------------------------------------------------------------------------

_speed_model = None
_congestion_model = None


def _load_speed_model():
    global _speed_model

    if _speed_model is None:
        if not SPEED_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"PEMS08 speed model not found: {SPEED_MODEL_PATH}"
            )

        _speed_model = joblib.load(SPEED_MODEL_PATH)

    return _speed_model


def _load_congestion_model():
    global _congestion_model

    if _congestion_model is None:
        if not CONGESTION_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"PEMS08 congestion model not found: {CONGESTION_MODEL_PATH}"
            )

        _congestion_model = joblib.load(CONGESTION_MODEL_PATH)

    return _congestion_model


# ---------------------------------------------------------------------------
# Input preparation
# ---------------------------------------------------------------------------

def _prepare_features(features: dict[str, Any]) -> pd.DataFrame:
    """
    Convert a feature dictionary into the exact dataframe structure
    expected by the trained sklearn pipelines.
    """

    missing = [
        column
        for column in FEATURE_COLUMNS
        if column not in features
    ]

    if missing:
        raise ValueError(
            f"Missing required PEMS08 features: {', '.join(missing)}"
        )

    row = {
        column: features[column]
        for column in FEATURE_COLUMNS
    }

    return pd.DataFrame([row], columns=FEATURE_COLUMNS)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def predict_speed(features: dict[str, Any]) -> float:
    """
    Predict speed one hour ahead using the trained PEMS08 RF regressor.
    """

    model = _load_speed_model()
    X = _prepare_features(features)

    prediction = model.predict(X)[0]

    return float(prediction)


def predict_congestion(features: dict[str, Any]) -> dict[str, Any]:
    """
    Predict congestion one hour ahead using the trained PEMS08 RF classifier.
    """

    model = _load_congestion_model()
    X = _prepare_features(features)

    prediction = model.predict(X)[0]

    probabilities = model.predict_proba(X)[0]
    classes = model.named_steps["model"].classes_

    probability_dict = {
        str(label): float(probability)
        for label, probability in zip(classes, probabilities)
    }

    return {
        "congestion_level": str(prediction),
        "probabilities": probability_dict,
    }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def get_model_status() -> dict[str, Any]:
    """
    Return information about the available PEMS08 model artifacts.
    """

    return {
        "speed_model_exists": SPEED_MODEL_PATH.exists(),
        "congestion_model_exists": CONGESTION_MODEL_PATH.exists(),
        "speed_model_path": str(SPEED_MODEL_PATH),
        "congestion_model_path": str(CONGESTION_MODEL_PATH),
        "feature_count": len(FEATURE_COLUMNS),
        "features": FEATURE_COLUMNS,
    }
