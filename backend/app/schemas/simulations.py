from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


MAX_SIMULATION_DURATION_MINUTES = 24 * 60
MAX_SIMULATION_INTERVAL_MINUTES = 60


class SimulationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    duration_minutes: int = Field(default=120, ge=5, le=MAX_SIMULATION_DURATION_MINUTES)
    interval_minutes: int = Field(default=5, ge=1, le=MAX_SIMULATION_INTERVAL_MINUTES)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    scenario_type: Literal["baseline"] = "baseline"
    start_time: datetime | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Simulation name cannot be blank.")
        return name

    @model_validator(mode="after")
    def validate_interval(self):
        if self.duration_minutes % self.interval_minutes != 0:
            raise ValueError(
                "duration_minutes must be divisible by interval_minutes."
            )
        return self


class SimulationRunSummary(BaseModel):
    id: UUID
    name: str
    scenario_type: str
    created_at: datetime
    duration_minutes: int
    interval_minutes: int
    seed: int
    record_count: int
    road_count: int
    source: Literal["simulation"] = "simulation"
    status: Literal["completed"] = "completed"
    start_time: datetime
    end_time: datetime


class SimulationRunCreated(SimulationRunSummary):
    pass


class SimulationRunDetail(SimulationRunSummary):
    parameters: dict
    road_ids_affected: list[str]
    scenario_snapshot: dict
    notes: str
