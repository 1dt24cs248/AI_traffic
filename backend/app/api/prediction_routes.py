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
from app.prediction.service import predict_speed, predict_congestion


router = APIRouter(
    prefix="/api/predictions/pems08",
    tags=["PEMS08 Predictions"],
)


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
            "predicted_speed_kmh": predicted_speed,
        }

    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=500,
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
        }

    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc