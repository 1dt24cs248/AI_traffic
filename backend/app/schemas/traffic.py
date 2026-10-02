"""
Validation schemas for traffic data ingestion.
Field-level constraints here are the first line of defense (Module 2: Validation step).
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TrafficRecordIn(BaseModel):
    """What one row of an uploaded CSV/JSON must look like."""

    road_id: str = Field(min_length=1, max_length=100)
    road_name: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timestamp: datetime
    vehicle_count: int = Field(ge=0, le=20000)
    average_speed: float = Field(ge=0, le=200)  # km/h — impossible above this on urban roads
    road_capacity: Optional[int] = Field(default=None, ge=1)
    occupancy: Optional[float] = Field(default=None, ge=0, le=100)
    weather_condition: Optional[str] = None
    temperature: Optional[float] = None
    rainfall: Optional[float] = Field(default=None, ge=0)
    event_indicator: Optional[str] = None

    @field_validator("road_id")
    @classmethod
    def road_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("road_id cannot be blank")
        return v.strip()


class TrafficRecordOut(BaseModel):
    id: uuid.UUID
    road_id: str
    road_name: Optional[str]
    latitude: float
    longitude: float
    timestamp: datetime
    vehicle_count: int
    average_speed: float
    road_capacity: Optional[int]
    occupancy: Optional[float]
    weather_condition: Optional[str]
    temperature: Optional[float]
    rainfall: Optional[float]
    day_of_week: Optional[int]
    hour: Optional[int]
    event_indicator: Optional[str]
    source: str

    class Config:
        from_attributes = True


class IngestionSummary(BaseModel):
    """Returned after a CSV/JSON upload — tells the user exactly what happened."""

    total_rows_received: int
    rows_inserted: int
    rows_duplicate: int
    rows_invalid: int
    invalid_row_errors: list[str]  # capped list of first N errors, not every single one
