from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.fuel_impact_config import (
    MAX_ALLOWED_EXTRA_CONSUMPTION_PERCENT,
    MAX_DEFAULT_EXTRA_CONSUMPTION_PERCENT,
)
from app.schemas.tomtom import RouteTrafficResult


class FuelVehicle(str, Enum):
    PETROL_CAR = "petrol-car"
    DIESEL_CAR = "diesel-car"
    PETROL_TWO_WHEELER = "petrol-two-wheeler"
    EV = "ev"


class FuelImpactRequest(BaseModel):
    vehicle: FuelVehicle
    distance_km: float = Field(gt=0, le=5000)
    efficiency: float = Field(gt=0, le=1000)
    price_per_unit: float | None = Field(default=None, gt=0, le=1_000_000)
    battery_capacity_kwh: float | None = Field(default=None, gt=0, le=1000)
    battery_charge_percent: float | None = Field(default=None, ge=0, le=100)
    max_extra_consumption_percent: float = Field(
        default=MAX_DEFAULT_EXTRA_CONSUMPTION_PERCENT,
        ge=0,
        le=MAX_ALLOWED_EXTRA_CONSUMPTION_PERCENT,
    )
    traffic: RouteTrafficResult | None = None
    weather: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_vehicle_inputs(self):
        if self.vehicle == FuelVehicle.EV and self.price_per_unit is not None and self.battery_capacity_kwh is None and self.battery_charge_percent is not None:
            raise ValueError("Battery charge requires a battery capacity.")
        if self.vehicle != FuelVehicle.EV and (self.battery_capacity_kwh is not None or self.battery_charge_percent is not None):
            raise ValueError("Battery inputs are only valid for an electric vehicle.")
        return self


class FuelImpactEstimate(BaseModel):
    vehicle: FuelVehicle
    distance_km: float
    energy_unit: str
    baseline: float
    additional: float | None
    total: float | None
    additional_cost: float | None
    additional_battery_percent: float | None
    estimated_remaining_charge_percent: float | None
    sample_count: int
    reduced_count: int
    heavy_reduction_count: int
    severe_reduction_count: int
    categories: list[str]
    average_speed_deficit: float | None
    traffic_latest_retrieved_at: str | None
    traffic_latest_observation_at: str | None
    traffic_coverage: str
    weather_adjustment_applied: bool
    weather_adjustment_reason: str
    idling_estimate: None = None
    formula: str
    limitations: str
