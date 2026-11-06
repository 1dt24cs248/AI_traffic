"""
Pydantic schemas for PEMS08 prediction APIs.
"""

from typing import Annotated, Dict

from pydantic import BaseModel, Field


PEMS08Measurement = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class PEMS08Features(BaseModel):
    """Exact 20-feature input contract used by the trained PEMS08 models."""

    flow: PEMS08Measurement = Field(..., description="Current PEMS08 flow in raw dataset units")
    occupancy: PEMS08Measurement = Field(..., description="Current PEMS08 occupancy in raw dataset units")
    speed: PEMS08Measurement = Field(
        ...,
        description="Current PEMS08 speed in raw dataset units; physical unit not independently verified",
    )

    flow_lag_5m: PEMS08Measurement
    flow_lag_15m: PEMS08Measurement
    flow_lag_30m: PEMS08Measurement
    flow_lag_1h: PEMS08Measurement

    speed_lag_5m: PEMS08Measurement
    speed_lag_15m: PEMS08Measurement
    speed_lag_30m: PEMS08Measurement
    speed_lag_1h: PEMS08Measurement

    occupancy_lag_5m: PEMS08Measurement
    occupancy_lag_15m: PEMS08Measurement
    occupancy_lag_30m: PEMS08Measurement
    occupancy_lag_1h: PEMS08Measurement

    hour: int = Field(..., ge=0, le=23)
    day_of_week: int = Field(..., ge=0, le=6)
    month: int = Field(..., ge=1, le=12)
    is_weekend: int = Field(..., ge=0, le=1)
    is_rush_hour: int = Field(..., ge=0, le=1)


class PEMS08SpeedPrediction(BaseModel):
    model: str
    prediction_horizon: str
    predicted_speed: float
    speed_unit_note: str


class PEMS08CongestionPrediction(BaseModel):
    model: str
    prediction_horizon: str
    congestion_level: str
    probabilities: Dict[str, float]
    probability_note: str
