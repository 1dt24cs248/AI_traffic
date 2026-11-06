from datetime import datetime

import pytest

from app.schemas.fuel_impact import FuelImpactRequest
from app.schemas.tomtom import CurrentTrafficFlow, RouteTrafficPoint, RouteTrafficResult
from app.services.fuel_impact import estimate_fuel_impact


def flow(current, free=50, retrieved=None):
    return CurrentTrafficFlow(
        latitude=12.9,
        longitude=77.6,
        current_speed=current,
        free_flow_speed=free,
        retrieved_at=retrieved or datetime(2026, 10, 20, 10),
    )


def request(vehicle="petrol-car", **overrides):
    values = {
        "vehicle": vehicle,
        "distance_km": 10,
        "efficiency": 10 if vehicle != "ev" else 18,
        "price_per_unit": 100 if vehicle != "ev" else 8,
        "max_extra_consumption_percent": 15,
        "traffic": RouteTrafficResult(
            status="partial",
            sampled_point_count=4,
            checked_point_count=3,
            points=[
                RouteTrafficPoint(status="available", flow=flow(25)),
                RouteTrafficPoint(status="available", flow=flow(45)),
                RouteTrafficPoint(status="available", flow=flow(15)),
                RouteTrafficPoint(status="available", flow=flow(35)),
            ],
        ),
        "weather": None,
    }
    values.update(overrides)
    return FuelImpactRequest(**values)


@pytest.mark.parametrize("vehicle", ["petrol-car", "diesel-car", "petrol-two-wheeler"])
def test_combustion_baseline_and_cost_use_user_efficiency_and_samples(vehicle):
    estimate = estimate_fuel_impact(request(vehicle))
    assert estimate.baseline == 1.0
    assert estimate.sample_count == 4
    assert estimate.reduced_count == 3
    assert estimate.heavy_reduction_count == 2
    # Deficits: .5, .1, .7, .3; mean=.4; 15% scenario cap; price=100 per litre.
    assert estimate.additional == pytest.approx(0.06)
    assert estimate.total == pytest.approx(1.06)
    assert estimate.additional_cost == pytest.approx(6.0)
    assert estimate.reduced_count == 3
    assert estimate.categories == [
        "heavy-reduction", "near-free-flow", "severe-reduction", "reduced-speed",
    ]
    assert estimate.idling_estimate is None
    assert not hasattr(estimate, "bottleneck_count")


def test_ev_energy_cost_and_optional_battery_percentage_are_unit_consistent():
    estimate = estimate_fuel_impact(request(
        "ev", battery_capacity_kwh=60, battery_charge_percent=80,
    ))
    assert estimate.energy_unit == "kWh"
    assert estimate.baseline == pytest.approx(1.8)
    assert estimate.additional == pytest.approx(0.108)
    assert estimate.additional_cost == pytest.approx(0.864)
    assert estimate.additional_battery_percent == pytest.approx(0.18)
    assert estimate.estimated_remaining_charge_percent == pytest.approx(76.82)


def test_missing_price_and_battery_leave_cost_and_charge_unavailable():
    estimate = estimate_fuel_impact(request("ev", price_per_unit=None))
    assert estimate.additional is not None
    assert estimate.additional_cost is None
    assert estimate.additional_battery_percent is None
    assert estimate.estimated_remaining_charge_percent is None


@pytest.mark.parametrize("speed,free", [(20, 0), (20, None), (None, 50), (-1, 50)])
def test_invalid_paired_speed_observations_are_excluded(speed, free):
    traffic = RouteTrafficResult(
        status="available", sampled_point_count=1, checked_point_count=1,
        points=[RouteTrafficPoint(status="available", flow=flow(speed, free))],
    )
    estimate = estimate_fuel_impact(request(traffic=traffic))
    assert estimate.sample_count == 0
    assert estimate.additional is None
    assert estimate.total is None
    assert estimate.traffic_coverage == "unavailable"


def test_no_traffic_keeps_baseline_but_does_not_fabricate_extra_use_or_bottlenecks():
    estimate = estimate_fuel_impact(request(traffic=None))
    assert estimate.baseline == 1.0
    assert estimate.additional is None
    assert estimate.additional_cost is None
    assert estimate.categories == []
    assert estimate.traffic_coverage == "unavailable"


def test_sample_counts_are_point_samples_and_weather_adjustment_is_never_applied():
    estimate = estimate_fuel_impact(request(weather={"provider": "Open-Meteo", "status": "available"}))
    assert estimate.sample_count == 4
    assert "not route-wide" in estimate.traffic_coverage
    assert estimate.weather_adjustment_applied is False
    assert "no validated vehicle-specific" in estimate.weather_adjustment_reason
    assert "scenario cap" in estimate.formula
    assert estimate.traffic_latest_retrieved_at == "2026-10-20T10:00:00"
    assert estimate.traffic_latest_observation_at is None


def test_missing_weather_is_reported_without_inventing_conditions_or_adjustment():
    estimate = estimate_fuel_impact(request(weather=None))
    assert estimate.weather_adjustment_applied is False
    assert "unavailable" in estimate.weather_adjustment_reason


@pytest.mark.parametrize("changes", [
    {"distance_km": 0}, {"efficiency": 0}, {"efficiency": -3},
    {"price_per_unit": 0}, {"battery_capacity_kwh": 0},
    {"battery_charge_percent": 101}, {"max_extra_consumption_percent": 31},
])
def test_invalid_efficiency_and_optional_inputs_are_rejected(changes):
    with pytest.raises(ValueError):
        request(**changes)


def test_ev_charge_requires_capacity_and_combustion_rejects_battery_inputs():
    with pytest.raises(ValueError, match="Battery charge requires"):
        request("ev", battery_charge_percent=60)
    with pytest.raises(ValueError, match="only valid for an electric"):
        request("diesel-car", battery_capacity_kwh=45)
