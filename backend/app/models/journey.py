"""
Journey model.

Each row stores one completed journey request — the origin, destination,
vehicle type selected, which route was chosen, and the recommendation
metadata at the time of selection.

This provides the data foundation for journey history and analytics.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class Journey(Base):
    __tablename__ = "journeys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Origin and destination
    origin_lat = Column(Float, nullable=False)
    origin_lon = Column(Float, nullable=False)
    origin_label = Column(String(500), nullable=True)  # display name from geocoding

    destination_lat = Column(Float, nullable=False)
    destination_lon = Column(Float, nullable=False)
    destination_label = Column(String(500), nullable=True)

    # Vehicle and preference
    vehicle_type = Column(String(50), nullable=False, default="car")
    route_preference = Column(String(50), nullable=True)  # fastest, shortest, recommended

    # Selected route metrics
    selected_route_index = Column(Integer, nullable=False, default=0)
    route_distance_km = Column(Float, nullable=True)
    route_duration_minutes = Column(Float, nullable=True)

    # Recommendation context
    recommended_index = Column(Integer, nullable=True)
    shortest_index = Column(Integer, nullable=True)
    fastest_index = Column(Integer, nullable=True)
    ranking_basis = Column(Text, nullable=True)

    # Active incidents at time of journey (snapshot)
    incidents_snapshot = Column(JSONB, nullable=True)

    # Weather snapshot at time of journey
    weather_snapshot = Column(JSONB, nullable=True)

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # FK to users.id
