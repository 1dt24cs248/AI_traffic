"""
PEMS08 prediction API endpoints.

These endpoints use the actual trained PEMS08 models.
They do not map PEMS08 sensors to application road IDs.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.prediction.schemas import (
    PEMS08Features,
    PEMS08SpeedPrediction,
    PEMS08CongestionPrediction,
)
from app.prediction.service import (
    FEATURE_COLUMNS,
    get_model_status,
    predict_speed,
    predict_congestion,
)


router = APIRouter(
    prefix="/api/predictions/pems08",
    tags=["PEMS08 Predictions"],
)


@router.get("/status")
def get_pems08_status(
    current_user: User = Depends(get_current_user),
):
    artifacts = get_model_status()
    return {
        "dataset": "PEMS08",
        "prediction_horizon": "1h",
        "speed_model_available": artifacts["speed_model_exists"],
        "congestion_model_available": artifacts["congestion_model_exists"],
        "feature_count": len(FEATURE_COLUMNS),
        "features": FEATURE_COLUMNS,
        "limitations": [
            "Inputs must be measured PEMS08 sensor values in the training feature schema.",
            "Application-road and simulation observations are not compatible inputs.",
            "PEMS08 has no verified geographic mapping to application roads.",
        ],
    }


@router.post(
    "/speed",
    response_model=PEMS08SpeedPrediction,
)
def predict_pems08_speed(
    features: PEMS08Features,
    current_user: User = Depends(get_current_user),
):
    """
    Predict sensor speed one hour ahead using the trained PEMS08
    Random Forest regression model.
    """

    try:
        predicted_speed = predict_speed(features.model_dump())

        return {
            "model": "pems08_speed_random_forest",
            "prediction_horizon": "1h",
            "predicted_speed": predicted_speed,
            "speed_unit_note": "PEMS08 dataset speed units; physical unit not independently verified.",
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="The PEMS08 speed model artifact is unavailable.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.post(
    "/congestion",
    response_model=PEMS08CongestionPrediction,
)
def predict_pems08_congestion(
    features: PEMS08Features,
    current_user: User = Depends(get_current_user),
):
    """
    Predict congestion level one hour ahead using the trained PEMS08
    Random Forest classification model.
    """

    try:
        result = predict_congestion(features.model_dump())

        return {
            "model": "pems08_congestion_random_forest",
            "prediction_horizon": "1h",
            "congestion_level": result["congestion_level"],
            "probabilities": result["probabilities"],
            "probability_note": (
                "Random-forest vote proportions; these are not calibrated confidence "
                "estimates and are not validated for Bengaluru roads."
            ),
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="The PEMS08 congestion model artifact is unavailable.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
