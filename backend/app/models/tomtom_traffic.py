"""Append-only TomTom observations and their provider segment registry."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    func,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TomTomRoadSegment(Base):
    __tablename__ = "tomtom_road_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, default="tomtom")
    provider_segment_reference = Column(String(255), nullable=True)
    identity_status = Column(String(20), nullable=False, default="provisional")
    identity_version = Column(String(50), nullable=False, default="unverified-v1")
    mapping_version = Column(String(50), nullable=False, default="unmapped-v1")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_segment_reference",
            name="uq_tomtom_segment_provider_reference",
        ),
        CheckConstraint(
            "identity_status IN ('provisional', 'unverified', 'verified')",
            name="ck_tomtom_segment_identity_status",
        ),
        CheckConstraint(
            "identity_status != 'verified' OR provider_segment_reference IS NOT NULL",
            name="ck_tomtom_verified_segment_has_reference",
        ),
        CheckConstraint(
            "identity_status != 'verified' OR mapping_version != 'unmapped-v1'",
            name="ck_tomtom_verified_segment_has_mapping",
        ),
    )

    @property
    def is_forecast_eligible(self) -> bool:
        return (
            self.identity_status == "verified"
            and self.provider_segment_reference is not None
            and self.mapping_version != "unmapped-v1"
        )


class TomTomTrafficObservation(Base):
    __tablename__ = "tomtom_traffic_observations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    segment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tomtom_road_segments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider = Column(String(50), nullable=False, default="tomtom")
    source = Column(String(100), nullable=False)
    source_endpoint = Column(String(255), nullable=False)
    provenance_version = Column(String(50), nullable=False)

    requested_latitude = Column(Float, nullable=False)
    requested_longitude = Column(Float, nullable=False)
    coordinate_system = Column(String(20), nullable=False, default="EPSG:4326")

    provider_observed_at = Column(DateTime(timezone=True), nullable=True)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    current_speed = Column(Float, nullable=True)
    free_flow_speed = Column(Float, nullable=True)
    travel_time_seconds = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    road_closure = Column(Boolean, nullable=True)
    speed_unit = Column(String(20), nullable=False, default="km/h")
    travel_time_unit = Column(String(20), nullable=False, default="seconds")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "segment_id",
            "provider_observed_at",
            name="uq_tomtom_observation_segment_observed_at",
        ),
        CheckConstraint(
            "requested_latitude >= -90 AND requested_latitude <= 90",
            name="ck_tomtom_observation_latitude",
        ),
        CheckConstraint(
            "requested_longitude >= -180 AND requested_longitude <= 180",
            name="ck_tomtom_observation_longitude",
        ),
        CheckConstraint(
            "current_speed IS NULL OR current_speed >= 0",
            name="ck_tomtom_observation_current_speed",
        ),
        CheckConstraint(
            "free_flow_speed IS NULL OR free_flow_speed >= 0",
            name="ck_tomtom_observation_free_flow_speed",
        ),
        CheckConstraint(
            "travel_time_seconds IS NULL OR travel_time_seconds >= 0",
            name="ck_tomtom_observation_travel_time",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_tomtom_observation_confidence",
        ),
        Index("ix_tomtom_observation_retrieved_at", "retrieved_at"),
    )
