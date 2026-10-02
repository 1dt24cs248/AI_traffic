"""
Traffic record model — Module 2: Traffic Data Collection.
Each row is one observation at one road at one point in time.
Schema is intentionally wide so features can be added later without breaking existing data.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, Integer, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class TrafficRecord(Base):
    __tablename__ = "traffic_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    road_id = Column(String(100), nullable=False, index=True)
    road_name = Column(String(255), nullable=True)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    timestamp = Column(DateTime, nullable=False, index=True)

    vehicle_count = Column(Integer, nullable=False)
    average_speed = Column(Float, nullable=False)          # km/h
    road_capacity = Column(Integer, nullable=True)          # max vehicles/hour, if known
    occupancy = Column(Float, nullable=True)                # % of road occupied, if known

    weather_condition = Column(String(50), nullable=True)
    temperature = Column(Float, nullable=True)
    rainfall = Column(Float, nullable=True)

    day_of_week = Column(Integer, nullable=True)            # 0=Monday .. 6=Sunday, derived if absent
    hour = Column(Integer, nullable=True)                   # derived if absent
    event_indicator = Column(String(100), nullable=True)    # e.g. "festival", "accident", null if none

    source = Column(String(50), nullable=False, default="csv_upload")  # csv_upload, json_upload, simulation, api
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_traffic_road_timestamp", "road_id", "timestamp"),
        Index("ix_traffic_lat_lng", "latitude", "longitude"),
        UniqueConstraint("road_id", "timestamp", name="uq_traffic_road_timestamp_record"),
    )
