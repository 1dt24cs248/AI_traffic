from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.schemas.tomtom import CurrentTrafficFlow
from app.traffic import route_flow
from app.traffic import observation_store
from app.traffic.tomtom import TomTomRateLimitError, TomTomUnavailableError, TomTomUpstreamError


def flow(lat, lon):
    return CurrentTrafficFlow(latitude=lat, longitude=lon, current_speed=32, free_flow_speed=50, confidence=0.8, road_closure=False, retrieved_at=datetime.now(timezone.utc))


def route():
    return [[77.0, 12.0], [77.01, 12.0], [77.02, 12.0], [77.03, 12.0], [77.04, 12.0]]


def setup_function():
    route_flow._CACHE.clear()


def test_route_sampling_checks_evenly_spaced_points_and_reports_provider_fields():
    coords = route_flow.sample_route_coordinates(route(), 5)
    assert len(coords) == 5
    assert [round(lon, 4) for _lat, lon in coords] == [77.0, 77.01, 77.02, 77.03, 77.04]
    with patch.object(
        observation_store,
        "persist_tomtom_observation",
        return_value=None,
    ), patch.object(
        route_flow,
        "get_current_flow",
        side_effect=lambda lat, lon: flow(lat, lon),
    ) as get:
        result = route_flow.get_route_flow(route(), 5)
    assert result.status == "available"
    assert result.checked_point_count == result.sampled_point_count == 5
    assert get.call_count == 5
    assert result.points[0].flow.confidence == 0.8
    assert result.points[0].flow.road_closure is False


def test_partial_point_failures_are_reported_without_fabricating_data():
    def provider(lat, lon):
        if lon < 77.001:
            raise TomTomUnavailableError("no flow segment")
        return flow(lat, lon)
    with patch.object(
        observation_store,
        "persist_tomtom_observation",
        return_value=None,
    ) as persist, patch.object(route_flow, "get_current_flow", side_effect=provider):
        result = route_flow.get_route_flow(route(), 5)
    assert result.status == "partial"
    assert result.checked_point_count == 4
    assert result.points[0].flow is None
    assert result.points[0].reason == "no flow segment"
    assert persist.call_count == 4


def test_successful_responses_are_cached_for_repeat_route_checks():
    persist = patch.object(
        observation_store,
        "persist_tomtom_observation",
        return_value=None,
    )
    with persist as save, patch.object(
        route_flow,
        "get_current_flow",
        side_effect=lambda lat, lon: flow(lat, lon),
    ) as get:
        route_flow.get_route_flow(route(), 4)
        route_flow.get_route_flow(route(), 4)
    assert get.call_count == 4
    assert save.call_count == 4


def test_route_flow_returns_live_data_when_persistence_fails():
    with patch.object(
        observation_store,
        "persist_tomtom_observation",
        side_effect=RuntimeError("simulated storage failure"),
    ), patch.object(
        route_flow,
        "get_current_flow",
        side_effect=lambda lat, lon: flow(lat, lon),
    ):
        result = route_flow.get_route_flow(route(), 2)

    assert result.status == "available"
    assert result.checked_point_count == 2
    assert result.points[0].flow.current_speed == 32
    assert set(result.model_dump()) == {
        "status",
        "sampled_point_count",
        "checked_point_count",
        "points",
        "reason",
    }
    assert set(result.points[0].model_dump()) == {
        "status",
        "flow",
        "latitude",
        "longitude",
        "reason",
    }
    assert result.points[0].flow.model_dump()["source"] == "TomTom Traffic Flow API"


def test_sample_count_and_coordinate_count_are_bounded():
    with pytest.raises(ValueError, match="Sample count"):
        route_flow.get_route_flow(route(), route_flow.MAX_SAMPLED_POINTS + 1)
    with pytest.raises(ValueError, match="between 2"):
        route_flow.sample_route_coordinates([[0, 0]], 3)
    too_many = [[float(i % 180), 0.0] for i in range(route_flow.MAX_ROUTE_COORDINATES + 1)]
    with pytest.raises(ValueError, match="between 2"):
        route_flow.sample_route_coordinates(too_many, 3)


@pytest.mark.parametrize("error", [TomTomRateLimitError("quota"), TomTomUpstreamError("timeout")])
def test_provider_errors_become_unavailable_point_statuses(error):
    with patch.object(
        observation_store,
        "persist_tomtom_observation",
    ) as persist, patch.object(route_flow, "get_current_flow", side_effect=error):
        result = route_flow.get_route_flow(route(), 3)
    assert result.status == "unavailable"
    assert result.checked_point_count == 0
    assert all(point.flow is None for point in result.points)
    persist.assert_not_called()


def test_provider_calls_respect_bounded_concurrency():
    from threading import Lock
    from time import sleep

    active = 0
    peak = 0
    lock = Lock()
    def provider(lat, lon):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.01)
        with lock:
            active -= 1
        return flow(lat, lon)
    with patch.object(
        observation_store,
        "persist_tomtom_observation",
        return_value=None,
    ) as persist, patch.object(route_flow, "get_current_flow", side_effect=provider):
        route_flow.get_route_flow(route(), route_flow.MAX_SAMPLED_POINTS)
    assert 1 < peak <= route_flow.MAX_CONCURRENCY
    assert persist.call_count == route_flow.MAX_SAMPLED_POINTS
