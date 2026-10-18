"""
Tests for AI traffic-aware routing integration.

These tests exercise feature construction and scoring helpers, and verify that
incompatible simulated-road observations are not sent to the PEMS08 model.

Run: python -m pytest tests/test_routing_traffic_prediction.py -v
"""
import os
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/unused_in_these_tests")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-real")

import pytest
from fastapi import HTTPException

from app.routing.traffic_feature_builder import build_features_for_road, _is_rush_hour
from app.routing.traffic_scoring import compute_route_score
from app.traffic.simulation import _rush_hour_multiplier
from app.api import routing_routes
from app.api.routing_routes import _build_ai_traffic_assessment, calculate_routes
from app.routing.schemas import RouteRequest


def make_record(road_id: str, timestamp: datetime, vehicle_count: int, average_speed: float, occupancy):
    """A lightweight stand-in for a TrafficRecord ORM row - same attributes
    the real feature builder reads, nothing invented beyond that."""
    return SimpleNamespace(
        road_id=road_id,
        timestamp=timestamp,
        vehicle_count=vehicle_count,
        average_speed=average_speed,
        occupancy=occupancy,
    )


def build_complete_history(road_id: str = "SIM-NH48-01", base: datetime | None = None) -> list:
    """Five real records at exactly T, T-5m, T-15m, T-30m, T-1h for one road."""
    base = base or datetime(2026, 1, 5, 8, 30, 0)  # a Monday, within rush-hour window
    offsets = [0, 5, 15, 30, 60]
    return [
        make_record(road_id, base - timedelta(minutes=m), vehicle_count=70 + m, average_speed=40.0, occupancy=35.0)
        for m in offsets
    ]


# ---------------- traffic_feature_builder ----------------

def test_complete_history_produces_available_result():
    records = build_complete_history()
    result = build_features_for_road(records, "SIM-NH48-01")

    assert result.available is True
    assert result.road_id == "SIM-NH48-01"
    assert result.observation_timestamp == records[0].timestamp  # most recent = T
    f = result.features
    assert set(f) == {
        "flow", "occupancy", "speed",
        "flow_lag_5m", "flow_lag_15m", "flow_lag_30m", "flow_lag_1h",
        "speed_lag_5m", "speed_lag_15m", "speed_lag_30m", "speed_lag_1h",
        "occupancy_lag_5m", "occupancy_lag_15m", "occupancy_lag_30m", "occupancy_lag_1h",
        "hour", "day_of_week", "month", "is_weekend", "is_rush_hour",
    }


def test_occupancy_conversion_is_divide_by_100():
    records = build_complete_history()
    result = build_features_for_road(records, "SIM-NH48-01")
    assert result.features["occupancy"] == pytest.approx(0.35)
    assert result.features["occupancy_lag_1h"] == pytest.approx(0.35)


def test_flow_is_vehicle_count_passthrough():
    records = build_complete_history()
    result = build_features_for_road(records, "SIM-NH48-01")
    assert result.features["flow"] == float(records[0].vehicle_count)


def test_speed_is_not_converted():
    records = build_complete_history()
    result = build_features_for_road(records, "SIM-NH48-01")
    assert result.features["speed"] == records[0].average_speed  # raw, unconverted


def test_missing_road_is_unavailable():
    result = build_features_for_road([], "SIM-NH48-99")
    assert result.available is False
    assert "No simulation traffic observations" in result.reason


def test_missing_single_lag_is_unavailable_not_interpolated():
    """Remove just the T-30m record; everything else present."""
    records = [r for r in build_complete_history() if (build_complete_history()[0].timestamp - r.timestamp) != timedelta(minutes=30)]
    result = build_features_for_road(records, "SIM-NH48-01")
    assert result.available is False
    assert "T-30m" in result.reason


def test_missing_occupancy_is_unavailable():
    records = build_complete_history()
    records[0] = make_record(records[0].road_id, records[0].timestamp, records[0].vehicle_count, records[0].average_speed, occupancy=None)
    result = build_features_for_road(records, "SIM-NH48-01")
    assert result.available is False
    assert "occupancy" in result.reason.lower()


def test_lag_records_never_cross_road_id():
    """Records exist for the required offsets, but under a DIFFERENT road_id -
    must not be borrowed."""
    base = datetime(2026, 1, 5, 8, 30, 0)
    other_road_full = build_complete_history(road_id="SIM-NH48-02", base=base)
    only_current_for_target = [make_record("SIM-NH48-01", base, 70, 40.0, 35.0)]
    result = build_features_for_road(other_road_full + only_current_for_target, "SIM-NH48-01")
    assert result.available is False  # SIM-NH48-01 has only T, no lag history of its own


@pytest.mark.parametrize(
    "hour,expected",
    [(6, False), (7, True), (9, True), (10, False), (16, False),
     (17, True), (19, True), (20, False)],
)
def test_weekday_rush_hour_boundaries(hour, expected):
    timestamp = datetime(2026, 1, 5, hour)  # Monday
    assert _is_rush_hour(timestamp) is expected


@pytest.mark.parametrize("day", [5, 6])
@pytest.mark.parametrize("hour", [7, 9, 17, 19])
def test_weekends_are_not_calendar_rush_hour(day, hour):
    timestamp = datetime(2026, 1, 5, hour) + timedelta(days=day)
    assert timestamp.weekday() == day
    assert _is_rush_hour(timestamp) is False


@pytest.mark.parametrize(
    "hour,expected",
    [(6, 0.65), (7, 1.55), (9, 1.55), (10, 1.05), (15, 1.05),
     (16, 1.65), (19, 1.65), (20, 0.90), (22, 0.90), (23, 0.65)],
)
def test_simulator_volume_profile_hour_boundaries(hour, expected):
    # This is the all-day generation curve, distinct from the weekday feature flag.
    assert _rush_hour_multiplier(hour) == expected


# ---------------- traffic_scoring ----------------

@pytest.mark.parametrize(
    "level,expected_score",
    [("LOW", 100), ("MEDIUM", 70), ("HIGH", 40), ("SEVERE", 10)],
)
def test_score_mapping_is_exact(level, expected_score):
    score, reason = compute_route_score(level)
    assert score == expected_score
    assert level in reason


def test_score_is_deterministic_across_calls():
    results = [compute_route_score("MEDIUM") for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_unrecognized_congestion_level_raises():
    with pytest.raises(ValueError):
        compute_route_score("NOT_A_REAL_LEVEL")


# ---------------- _build_ai_traffic_assessment (integration point) ----------------

def test_no_coverage_means_no_prediction_call():
    coverage = {"traffic_coverage": False, "matched_roads": [], "match_radius_meters": 500}
    assessment = _build_ai_traffic_assessment(coverage, traffic_records=[])

    assert assessment.status == "unavailable_no_coverage"
    assert "unavailable" in assessment.reason.lower()


def test_coverage_but_insufficient_history_means_no_prediction_call():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    incomplete_records = build_complete_history()[:2]  # only T and T-5m
    assessment = _build_ai_traffic_assessment(coverage, incomplete_records)

    assert assessment.status == "unavailable_incompatible_input"
    assert assessment.road_assessments[0].status == "unavailable_incompatible_input"


def test_full_coverage_and_history_is_unavailable_for_incompatible_model_input():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    records = build_complete_history()

    with patch("app.api.routing_routes.predict_speed", create=True) as mock_speed, \
         patch("app.api.routing_routes.predict_congestion", create=True) as mock_congestion:
        assessment = _build_ai_traffic_assessment(coverage, records)

    mock_speed.assert_not_called()
    mock_congestion.assert_not_called()
    assert assessment.status == "unavailable_incompatible_input"
    assert assessment.data_source == "simulation"
    assert assessment.predicted_speed is None
    assert assessment.congestion_level is None
    assert assessment.route_score is None
    assert "not validated as PEMS08 flow" in assessment.reason
    assert assessment.road_assessments[0].status == "unavailable_incompatible_input"


def test_model_is_not_loaded_for_simulation_route_input():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    records = build_complete_history()

    with patch("app.api.routing_routes.predict_speed", create=True) as mock_speed, \
         patch("app.api.routing_routes.predict_congestion", create=True) as mock_congestion:
        assessment = _build_ai_traffic_assessment(coverage, records)

    assert assessment.status == "unavailable_incompatible_input"
    mock_speed.assert_not_called()
    mock_congestion.assert_not_called()


def test_all_matched_roads_are_reported_incompatible():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [
            {"road_id": "SIM-NH48-01", "distance_meters": 50.0},
            {"road_id": "SIM-NH48-02", "distance_meters": 200.0},
        ],
        "match_radius_meters": 500,
    }
    records = build_complete_history(road_id="SIM-NH48-01")

    assessment = _build_ai_traffic_assessment(coverage, records)

    assert assessment.status == "unavailable_incompatible_input"
    assert [road.road_id for road in assessment.road_assessments] == [
        "SIM-NH48-01", "SIM-NH48-02"
    ]


# ---------------- calculate_routes endpoint integration ----------------

def _valid_route_request():
    return RouteRequest(
        origin_lat=13.0,
        origin_lon=77.5,
        destination_lat=13.1,
        destination_lon=77.6,
        alternatives=True,
        traffic_match_radius_meters=500,
    )


def _osrm_result():
    return {
        "provider": "OSRM",
        "routes": [
            {
                "distance": 2500.0,
                "duration": 600.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[77.55, 13.01], [77.56, 13.02]],
                },
            }
        ],
        "waypoints": [],
    }


def _database_with_records(records):
    # A small explicit mock chain for SessionLocal -> query -> filter -> all.
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = records
    return db


@contextmanager
def _patch_forbidden_predictions():
    with ExitStack() as stack:
        # These route-module call points do not exist in the current endpoint;
        # create=True makes an accidental reintroduction fail the assertions.
        mocks = [
            stack.enter_context(patch("app.api.routing_routes.predict_speed", create=True)),
            stack.enter_context(patch("app.api.routing_routes.predict_congestion", create=True)),
            stack.enter_context(patch("app.api.routing_routes.compute_route_score", create=True)),
            stack.enter_context(patch("app.routing.traffic_scoring.compute_route_score")),
        ]
        yield mocks


def test_calculate_routes_returns_routes_coverage_and_incompatible_status():
    base = datetime(2026, 1, 5, 8, 30)
    records = build_complete_history(base=base)
    for record in records:
        record.latitude = 13.01
        record.longitude = 77.55
    db = _database_with_records(records)

    with patch.object(routing_routes, "get_route", return_value=_osrm_result()), \
         patch.object(routing_routes, "SessionLocal", return_value=db), \
         _patch_forbidden_predictions() as prediction_mocks:
        response = calculate_routes(_valid_route_request())
    for prediction_mock in prediction_mocks:
        prediction_mock.assert_not_called()

    assert response.provider == "OSRM"
    assert len(response.routes) == 1
    assert response.routes[0].distance_meters == 2500.0
    assert response.routes[0].duration_seconds == 600.0
    assert response.traffic.traffic_coverage is True
    assert response.traffic.matched_roads[0].road_id == "SIM-NH48-01"
    assessment = response.routes[0].ai_traffic
    assert assessment.status == "unavailable_incompatible_input"
    assert assessment.predicted_speed is None
    assert assessment.congestion_level is None
    assert assessment.congestion_probabilities is None
    assert assessment.route_score is None
    assert assessment.road_assessments[0].status == "unavailable_incompatible_input"
    assert assessment.road_assessments[0].predicted_speed is None
    assert assessment.road_assessments[0].congestion_level is None
    assert assessment.road_assessments[0].congestion_probabilities is None
    assert assessment.road_assessments[0].route_score is None
    db.close.assert_called_once()


def test_calculate_routes_no_coverage_keeps_route_and_unavailable_status():
    db = _database_with_records([])
    with patch.object(routing_routes, "get_route", return_value=_osrm_result()), \
         patch.object(routing_routes, "SessionLocal", return_value=db), \
         _patch_forbidden_predictions() as prediction_mocks:
        response = calculate_routes(_valid_route_request())
    for prediction_mock in prediction_mocks:
        prediction_mock.assert_not_called()

    assert len(response.routes) == 1
    assert response.traffic.traffic_coverage is False
    assert response.traffic.matched_roads == []
    assessment = response.routes[0].ai_traffic
    assert assessment.status == "unavailable_no_coverage"
    assert assessment.predicted_speed is None
    assert assessment.congestion_level is None
    assert assessment.congestion_probabilities is None
    assert assessment.route_score is None
    db.close.assert_called_once()


def test_calculate_routes_maps_osrm_error_to_502():
    with patch.object(routing_routes, "get_route", side_effect=routing_routes.OSRMError("provider unavailable")), \
         patch.object(routing_routes, "SessionLocal") as session_factory:
        with pytest.raises(HTTPException) as exc_info:
            calculate_routes(_valid_route_request())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "provider unavailable"
    session_factory.assert_not_called()


def test_calculate_routes_closes_database_session_after_coverage_failure():
    db = _database_with_records([])
    with patch.object(routing_routes, "get_route", return_value=_osrm_result()), \
         patch.object(routing_routes, "SessionLocal", return_value=db), \
         patch.object(routing_routes, "find_traffic_coverage", side_effect=RuntimeError("coverage failed")):
        with pytest.raises(RuntimeError, match="coverage failed"):
            calculate_routes(_valid_route_request())

    db.close.assert_called_once()
