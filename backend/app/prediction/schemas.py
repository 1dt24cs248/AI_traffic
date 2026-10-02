"""
Pydantic schemas for PEMS08 prediction APIs.
"""

from typing import Dict

from pydantic import BaseModel, Field


class PEMS08Features(BaseModel):
    """Exact 20-feature input contract used by the trained PEMS08 models."""

    flow: float = Field(..., description="Current sensor flow")
    occupancy: float = Field(..., description="Current sensor occupancy")
    speed: float = Field(..., description="Current sensor speed in km/h")

    flow_lag_5m: float
    flow_lag_15m: float
    flow_lag_30m: float
    flow_lag_1h: float

    speed_lag_5m: float
    speed_lag_15m: float
    speed_lag_30m: float
    speed_lag_1h: float

    occupancy_lag_5m: float
    occupancy_lag_15m: float
    occupancy_lag_30m: float
    occupancy_lag_1h: float

    hour: int = Field(..., ge=0, le=23)
    day_of_week: int = Field(..., ge=0, le=6)
    month: int = Field(..., ge=1, le=12)
    is_weekend: int = Field(..., ge=0, le=1)
    is_rush_hour: int = Field(..., ge=0, le=1)


class PEMS08SpeedPrediction(BaseModel):
    model: str
    prediction_horizon: str
    predicted_speed_kmh: float


class PEMS08CongestionPrediction(BaseModel):
    model: str
    prediction_horizon: str
    congestion_level: str
    probabilities: Dict[str, float]