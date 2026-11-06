"""
Incident model.

Each row represents one traffic or road-hazard incident.
Incidents are linked to a geographic location and optionally to
a specific road_id from the traffic_records table.

Source field distinguishes real user reports from seeded
demonstration data and from simulation scenarios.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class IncidentType(str, enum.Enum):
    ROAD_CLOSURE = "road_closure"
    ACCIDENT = "accident"
    FALLEN_TREE = "fallen_tree"
    WATERLOGGING = "waterlogging"
    CONSTRUCTION = "construction"
    BROKEN_VEHICLE = "broken_vehicle"
    OBSTRUCTION = "obstruction"
    PARTIAL_OBSTRUCTION = "partial_obstruction"
    OTHER = "other"


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    REPORTED = "reported"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class IncidentSource(str, enum.Enum):
    USER_REPORT = "user_report"
    SYSTEM = "system"
    SIMULATION = "simulation"
    DEMO = "demo"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Type and location
    type = Column(Enum(IncidentType), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Optional road link — null when the incident is not yet matched to a road
    road_id = Column(String(100), nullable=True, index=True)
    road_reference = Column(String(255), nullable=True)

    # Severity, status and provenance
    severity = Column(Enum(IncidentSeverity), nullable=False, default=IncidentSeverity.MEDIUM)
    status = Column(Enum(IncidentStatus), nullable=False, default=IncidentStatus.REPORTED, index=True)
    source = Column(Enum(IncidentSource), nullable=False, default=IncidentSource.USER_REPORT)
    verified = Column(Boolean, nullable=False, default=False)
    confidence = Column(Float, nullable=True)  # 0.0–1.0; null when not applicable
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(UUID(as_uuid=True), nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)  # null = still active

    # Human-readable description
    description = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    created_by = Column(UUID(as_uuid=True), nullable=True)  # FK to users.id (not enforced at DB level for now)

    __table_args__ = (
        Index("ix_incident_lat_lon", "latitude", "longitude"),
        Index("ix_incident_status_type", "status", "type"),
    )
