"""
SimulationRun model.

Each row stores one complete simulation scenario execution including
the input parameters, baseline snapshot, scenario snapshot, and the
computed comparison.

All snapshots are stored as JSONB so the schema does not need to
change as new output fields are added to the simulation engine.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Human-readable label for the scenario
    name = Column(String(255), nullable=False)
    scenario_type = Column(String(100), nullable=False)  # e.g. road_closure, heavy_rain

    # Inputs stored verbatim so results are reproducible
    parameters = Column(JSONB, nullable=False)

    # Which roads were targeted by incident scenarios (list of road_id strings)
    road_ids_affected = Column(JSONB, nullable=True)

    # Aggregate statistics per road for baseline and modified scenario
    # Structure: {"roads": [{"road_id":..., "avg_speed":..., "avg_volume":...}], "total_records":...}
    baseline_snapshot = Column(JSONB, nullable=True)
    scenario_snapshot = Column(JSONB, nullable=False)

    # Side-by-side delta comparison
    # Structure: {"roads_affected":[...], "avg_speed_change_pct":..., "avg_volume_change_pct":..., "limitations":[...]}
    comparison = Column(JSONB, nullable=True)

    # Duration of the simulated window
    duration_minutes = Column(Integer, nullable=False)
    interval_minutes = Column(Integer, nullable=False)

    # Notes field — stores assumption disclosures and limitation statements
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)  # FK to users.id
