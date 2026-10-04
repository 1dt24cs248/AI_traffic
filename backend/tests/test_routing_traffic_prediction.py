"""
Tests for AI traffic-aware routing integration.

These tests exercise the REAL traffic_feature_builder and traffic_scoring
logic against constructed TrafficRecord-like objects. The prediction service
(predict_speed/predict_congestion, which load real joblib model files) is
mocked only where a test is specifically about prediction SUCCEEDING or
FAILING at the integration boundary - the feature-building and scoring math
itself is never mocked.

Run: python -m pytest tests/test_routing_traffic_prediction.py -v
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/unused_in_these_tests")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-real")

import pytest

from app.routing.traffic_feature_builder import build_features_for_road
from app.routing.traffic_scoring import compute_route_score
from app.api.routing_routes import _build_ai_traffic_assessment


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
    with patch("app.api.routing_routes.predict_speed") as mock_speed, \
         patch("app.api.routing_routes.predict_congestion") as mock_congestion:
        assessment = _build_ai_traffic_assessment(coverage, traffic_records=[])

    assert assessment.status == "unavailable_no_coverage"
    assert "unavailable" in assessment.reason.lower()
    mock_speed.assert_not_called()
    mock_congestion.assert_not_called()


def test_coverage_but_insufficient_history_means_no_prediction_call():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    incomplete_records = build_complete_history()[:2]  # only T and T-5m
    with patch("app.api.routing_routes.predict_speed") as mock_speed, \
         patch("app.api.routing_routes.predict_congestion") as mock_congestion:
        assessment = _build_ai_traffic_assessment(coverage, incomplete_records)

    assert assessment.status == "unavailable_insufficient_history"
    assert assessment.road_id == "SIM-NH48-01"
    mock_speed.assert_not_called()
    mock_congestion.assert_not_called()


def test_full_coverage_and_history_produces_available_prediction():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    records = build_complete_history()

    with patch("app.api.routing_routes.predict_speed", return_value=42.5) as mock_speed, \
         patch("app.api.routing_routes.predict_congestion", return_value={"congestion_level": "MEDIUM", "probabilities": {"LOW": 0.1, "MEDIUM": 0.6, "HIGH": 0.2, "SEVERE": 0.1}}) as mock_congestion:
        assessment = _build_ai_traffic_assessment(coverage, records)

    mock_speed.assert_called_once()
    mock_congestion.assert_called_once()
    assert assessment.status == "available"
    assert assessment.data_source == "simulation"
    assert assessment.predicted_speed == 42.5
    assert assessment.congestion_level == "MEDIUM"
    assert assessment.route_score == 70
    assert "Simulation-based AI estimate" in assessment.reason
    assert "not a validated real-world traffic forecast" in assessment.reason


def test_prediction_service_failure_is_controlled_not_raised():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 50.0}],
        "match_radius_meters": 500,
    }
    records = build_complete_history()

    with patch("app.api.routing_routes.predict_speed", side_effect=FileNotFoundError("model missing")):
        assessment = _build_ai_traffic_assessment(coverage, records)  # must not raise

    assert assessment.status == "unavailable_prediction_error"
    assert "model missing" in assessment.reason


def test_closest_matched_road_is_used_when_multiple_exist():
    coverage = {
        "traffic_coverage": True,
        "matched_roads": [
            {"road_id": "SIM-NH48-01", "distance_meters": 50.0},
            {"road_id": "SIM-NH48-02", "distance_meters": 200.0},
        ],
        "match_radius_meters": 500,
    }
    records = build_complete_history(road_id="SIM-NH48-01")

    with patch("app.api.routing_routes.predict_speed", return_value=30.0), \
         patch("app.api.routing_routes.predict_congestion", return_value={"congestion_level": "LOW", "probabilities": {}}):
        assessment = _build_ai_traffic_assessment(coverage, records)

    assert assessment.road_id == "SIM-NH48-01"  # the closer one, not SIM-NH48-02