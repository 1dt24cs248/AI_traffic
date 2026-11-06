from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.incident import (
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
    IncidentType,
)


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: IncidentType
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    road_id: Optional[str] = Field(default=None, max_length=100)
    road_reference: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    source: IncidentSource = IncidentSource.USER_REPORT


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Optional[IncidentType] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    severity: Optional[IncidentSeverity] = None
    road_id: Optional[str] = Field(default=None, max_length=100)
    road_reference: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: IncidentType
    latitude: float
    longitude: float
    road_id: Optional[str]
    road_reference: Optional[str]
    severity: IncidentSeverity
    status: IncidentStatus
    source: IncidentSource
    verified: bool
    confidence: Optional[float]
    started_at: datetime
    ended_at: Optional[datetime]
    verified_at: Optional[datetime]
    verified_by: Optional[UUID]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID]


class IncidentVerification(BaseModel):
    verified: bool = True
