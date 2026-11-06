from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.incident import IncidentSeverity, IncidentSource, IncidentType


class IncidentAlert(BaseModel):
    id: UUID
    incident_id: UUID
    type: IncidentType
    severity: IncidentSeverity
    status: Literal["active", "resolved"]
    latitude: float
    longitude: float
    road_id: Optional[str]
    road_reference: Optional[str]
    description: Optional[str]
    source: IncidentSource
    created_at: datetime
    verified_at: Optional[datetime]
    ended_at: Optional[datetime]
