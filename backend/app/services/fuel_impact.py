from datetime import datetime
from math import isfinite

from app.core.fuel_impact_config import SPEED_BANDS
from app.schemas.fuel_impact import FuelImpactEstimate, FuelImpactRequest, FuelVehicle


FORMULA = (
    "baseline × (user-selected scenario cap ÷ 100) × mean sampled speed deficit; "
    "each deficit = max(0, 1 − min(1, current speed ÷ free-flow speed))."
)
LIMITATIONS = (
    "A configurable scenario heuristic, not measured fuel/energy use or a validated "
    "vehicle-specific model. Sparse samples do not represent complete route coverage."
)


def _speed_sample(current: object, free_flow: object) -> float | None:
    if isinstance(current, bool) or isinstance(free_flow, bool):
        return None
    if not isinstance(current, (float, int)) or not isinstance(free_flow, (float, int)):
        return None
    if not isfinite(current) or not isfinite(free_flow) or current < 0 or free_flow <= 0:
        return None
    return current / free_flow


def _category(ratio: float) -> str:
    if ratio >= SPEED_BANDS[0][0]:
        return SPEED_BANDS[0][1]
    if ratio >= SPEED_BANDS[1][0]:
        return SPEED_BANDS[1][1]
    if ratio >= SPEED_BANDS[2][0]:
        return SPEED_BANDS[2][1]
    return "severe-reduction"


def estimate_fuel_impact(request: FuelImpactRequest) -> FuelImpactEstimate:
    is_ev = request.vehicle == FuelVehicle.EV
    baseline = (
        request.distance_km * request.efficiency / 100
        if is_ev
        else request.distance_km / request.efficiency
    )
    ratios: list[float] = []
    retrieved: list[datetime] = []
    observed: list[datetime] = []
    for point in request.traffic.points if request.traffic else []:
        flow = point.flow
        if flow is None:
            continue
        ratio = _speed_sample(flow.current_speed, flow.free_flow_speed)
        if ratio is None:
            continue
        ratios.append(ratio)
        retrieved.append(flow.retrieved_at)
        if flow.observation_time is not None:
            observed.append(flow.observation_time)

    categories = [_category(ratio) for ratio in ratios]
    deficit = (
        sum(max(0.0, 1.0 - min(1.0, ratio)) for ratio in ratios) / len(ratios)
        if ratios
        else None
    )
    additional = (
        baseline * (request.max_extra_consumption_percent / 100) * deficit
        if deficit is not None
        else None
    )
    total = baseline + additional if additional is not None else None
    additional_cost = (
        additional * request.price_per_unit
        if additional is not None and request.price_per_unit is not None
        else None
    )
    additional_battery = (
        additional / request.battery_capacity_kwh * 100
        if is_ev and additional is not None and request.battery_capacity_kwh is not None
        else None
    )
    remaining_charge = (
        request.battery_charge_percent - total / request.battery_capacity_kwh * 100
        if is_ev
        and total is not None
        and request.battery_capacity_kwh is not None
        and request.battery_charge_percent is not None
        else None
    )
    weather_reason = (
        "Forecast is shown for context; no validated vehicle-specific weather-to-energy adjustment is available."
        if request.weather is not None
        else "Weather data is unavailable; no weather adjustment has been applied."
    )
    return FuelImpactEstimate(
        vehicle=request.vehicle,
        distance_km=request.distance_km,
        energy_unit="kWh" if is_ev else "L",
        baseline=baseline,
        additional=additional,
        total=total,
        additional_cost=additional_cost,
        additional_battery_percent=additional_battery,
        estimated_remaining_charge_percent=remaining_charge,
        sample_count=len(ratios),
        reduced_count=sum(category != "near-free-flow" for category in categories),
        heavy_reduction_count=sum(category in {"heavy-reduction", "severe-reduction"} for category in categories),
        severe_reduction_count=categories.count("severe-reduction"),
        categories=categories,
        average_speed_deficit=deficit,
        traffic_latest_retrieved_at=max(retrieved).isoformat() if retrieved else None,
        traffic_latest_observation_at=max(observed).isoformat() if observed else None,
        traffic_coverage="limited point samples; not route-wide coverage" if ratios else "unavailable",
        weather_adjustment_applied=False,
        weather_adjustment_reason=weather_reason,
        formula=FORMULA,
        limitations=LIMITATIONS,
    )
