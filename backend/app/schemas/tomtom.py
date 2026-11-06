from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CurrentTrafficFlow(BaseModel):
    latitude: float
    longitude: float
    current_speed: Optional[float] = None
    free_flow_speed: Optional[float] = None
    current_travel_time_seconds: Optional[int] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    road_closure: Optional[bool] = None
    source: str = "TomTom Traffic Flow API"
    observation_time: Optional[datetime] = None
    retrieved_at: datetime


class RouteTrafficPoint(BaseModel):
    status: str
    flow: Optional[CurrentTrafficFlow] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reason: Optional[str] = None


class RouteTrafficResult(BaseModel):
    status: str
    sampled_point_count: int
    checked_point_count: int
    points: list[RouteTrafficPoint]
    reason: Optional[str] = None
