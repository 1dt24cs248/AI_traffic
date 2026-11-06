"""
Phase 1 tests.

Verifies the foundation fixes made in Phase 1:
  - F1: New dependencies importable
  - F2: OSRM URL is configurable from Settings
  - F2: OSRM profile map covers all declared vehicle types
  - Routing schemas: new fields have correct defaults (backwards-compatible)
  - Recommendation module: rank_routes() core logic
  - ML safety gate: unchanged (no PEMS08 call for simulation inputs)
"""
import os

# Ensure env vars are set before any app imports (conftest.py handles this
# at the module level, but explicit here for clarity).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://test:test@localhost:5432/test_traffic_db",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-phase1")

import pytest


# ---------------------------------------------------------------------------
# F1: New dependencies are importable
# ---------------------------------------------------------------------------

def test_requests_importable():
    """requests must be importable after F1 fix."""
    import requests  # noqa: F401


def test_joblib_importable():
    """joblib must be importable after F1 fix."""
    import joblib  # noqa: F401


def test_pandas_importable():
    """pandas must be importable after F1 fix."""
    import pandas  # noqa: F401


def test_numpy_importable():
    """numpy must be importable."""
    import numpy  # noqa: F401


def test_sklearn_importable():
    """scikit-learn must be importable."""
    import sklearn  # noqa: F401


# ---------------------------------------------------------------------------
# F2: OSRM URL is configurable
# ---------------------------------------------------------------------------

def test_osrm_url_comes_from_settings():
    """OSRM_BASE_URL must be read from Settings, not hardcoded in osrm_client."""
    from app.core.config import settings
    from app.routing import osrm_client

    assert osrm_client.OSRM_BASE_URL == settings.OSRM_BASE_URL


def test_osrm_default_is_public_server():
    """Default OSRM URL should point to the public OSRM service."""
    from app.core.config import settings

    assert "router.project-osrm.org" in settings.OSRM_BASE_URL


def test_settings_has_geocoding_user_agent():
    from app.core.config import settings

    assert settings.GEOCODING_USER_AGENT != ""


def test_settings_has_weather_base_url():
    from app.core.config import settings

    assert "open-meteo" in settings.WEATHER_BASE_URL


# ---------------------------------------------------------------------------
# Routing schema: new fields are backward-compatible
# ---------------------------------------------------------------------------

def test_route_request_vehicle_type_defaults_to_car():
    from app.routing.schemas import RouteRequest

    req = RouteRequest(
        origin_lat=13.0, origin_lon=77.5,
        destination_lat=13.1, destination_lon=77.6,
    )
    assert req.vehicle_type == "car"


def test_route_request_route_preference_defaults_to_fastest():
    from app.routing.schemas import RouteRequest

    req = RouteRequest(
        origin_lat=13.0, origin_lon=77.5,
        destination_lat=13.1, destination_lon=77.6,
    )
    assert req.route_preference == "fastest"


def test_route_request_accepts_bicycle():
    from app.routing.schemas import RouteRequest

    req = RouteRequest(
        origin_lat=13.0, origin_lon=77.5,
        destination_lat=13.1, destination_lon=77.6,
        vehicle_type="bicycle",
    )
    assert req.vehicle_type == "bicycle"


def test_route_request_rejects_invalid_vehicle():
    from pydantic import ValidationError
    from app.routing.schemas import RouteRequest

    with pytest.raises(ValidationError):
        RouteRequest(
            origin_lat=13.0, origin_lon=77.5,
            destination_lat=13.1, destination_lon=77.6,
            vehicle_type="spaceship",  # not a valid vehicle type
        )


def test_route_response_has_recommendation_fields():
    """RouteResponse must expose recommended_index, fastest_index, shortest_index."""
    from app.routing.schemas import RouteResponse, TrafficCoverage

    resp = RouteResponse(
        provider="test",
        routes=[],
        traffic=TrafficCoverage(
            traffic_coverage=False,
            matched_roads=[],
            match_radius_meters=500,
        ),
    )
    # All new fields must have safe defaults
    assert resp.recommended_index is None
    assert resp.fastest_index == 0
    assert resp.shortest_index == 0
    assert resp.ranking_basis == ""
    assert resp.vehicle_type == "car"
    assert resp.osrm_profile == "driving"


def test_osrm_profile_map_covers_all_vehicle_types():
    from app.routing.schemas import OSRM_PROFILE_MAP, VehicleType
    import typing

    all_vehicle_types = typing.get_args(VehicleType)
    for vt in all_vehicle_types:
        assert vt in OSRM_PROFILE_MAP, f"vehicle_type '{vt}' missing from OSRM_PROFILE_MAP"


def test_route_summary_defaults_to_feasible():
    """RouteSummary.feasible must default to True — existing routes stay feasible."""
    from app.routing.schemas import RouteSummary

    s = RouteSummary(
        distance_meters=1000,
        distance_km=1.0,
        duration_seconds=120,
        duration_minutes=2.0,
        geometry={"type": "LineString", "coordinates": []},
    )
    assert s.feasible is True
    assert s.infeasibility_reason is None
    assert s.incident_warnings == []
    assert s.vehicle_profile_note is None


# ---------------------------------------------------------------------------
# Recommendation module: rank_routes()
# ---------------------------------------------------------------------------

def test_rank_single_route():
    """A single feasible route is always recommended."""
    from app.routing.recommendation import RouteCandidate, rank_routes

    candidates = [RouteCandidate(index=0, distance_meters=5000, duration_seconds=300, feasible=True)]
    result = rank_routes(candidates)

    assert result.recommended_index == 0
    assert result.fastest_index == 0
    assert result.shortest_index == 0
    assert result.all_infeasible is False


def test_rank_picks_fastest_by_default():
    from app.routing.recommendation import RouteCandidate, rank_routes

    candidates = [
        RouteCandidate(index=0, distance_meters=3000, duration_seconds=600, feasible=True),
        RouteCandidate(index=1, distance_meters=5000, duration_seconds=300, feasible=True),
    ]
    result = rank_routes(candidates, preference="fastest")

    assert result.recommended_index == 1   # shorter duration
    assert result.fastest_index == 1
    assert result.shortest_index == 0      # shorter distance


def test_rank_picks_shortest_when_preferred():
    from app.routing.recommendation import RouteCandidate, rank_routes

    candidates = [
        RouteCandidate(index=0, distance_meters=3000, duration_seconds=600, feasible=True),
        RouteCandidate(index=1, distance_meters=5000, duration_seconds=300, feasible=True),
    ]
    result = rank_routes(candidates, preference="shortest")

    assert result.recommended_index == 0   # shorter distance preferred
    assert result.shortest_index == 0


def test_rank_skips_infeasible_routes():
    """A road_closure-blocked route must not be recommended."""
    from app.routing.recommendation import RouteCandidate, rank_routes

    candidates = [
        RouteCandidate(
            index=0, distance_meters=3000, duration_seconds=600,
            feasible=False, infeasibility_reason="Road closure on segment A"
        ),
        RouteCandidate(index=1, distance_meters=5000, duration_seconds=300, feasible=True),
    ]
    result = rank_routes(candidates)

    assert result.recommended_index == 1
    assert result.all_infeasible is False


def test_rank_all_infeasible_returns_none():
    from app.routing.recommendation import RouteCandidate, rank_routes

    candidates = [
        RouteCandidate(index=0, distance_meters=3000, duration_seconds=600,
                       feasible=False, infeasibility_reason="Closure A"),
        RouteCandidate(index=1, distance_meters=5000, duration_seconds=300,
                       feasible=False, infeasibility_reason="Closure B"),
    ]
    result = rank_routes(candidates)

    assert result.recommended_index is None
    assert result.all_infeasible is True
    assert "No feasible route" in result.ranking_basis


def test_rank_empty_candidates_raises():
    from app.routing.recommendation import rank_routes

    with pytest.raises(ValueError, match="at least one"):
        rank_routes([])


# ---------------------------------------------------------------------------
# ML safety gate: must remain intact
# ---------------------------------------------------------------------------

def test_ml_safety_gate_returns_unavailable_incompatible():
    """
    The _build_ai_traffic_assessment function must still return
    'unavailable_incompatible_input' for simulation-source records.
    This test verifies the safety gate is unchanged.
    """
    from app.api.routing_routes import _build_ai_traffic_assessment

    coverage = {
        "traffic_coverage": True,
        "matched_roads": [
            {"road_id": "SIM-NH48-01", "distance_meters": 42.5}
        ],
        "match_radius_meters": 500,
    }
    # Simulate a list of traffic records (source = simulation)
    class FakeRecord:
        source = "simulation"

    result = _build_ai_traffic_assessment(coverage, [FakeRecord()])

    assert result.status == "unavailable_incompatible_input"
    assert result.predicted_speed is None
    assert result.congestion_level is None
    assert result.route_score is None
    assert result.roads_assessed == 0


def test_ml_safety_gate_no_coverage_returns_unavailable_no_coverage():
    from app.api.routing_routes import _build_ai_traffic_assessment

    coverage = {
        "traffic_coverage": False,
        "matched_roads": [],
        "match_radius_meters": 500,
    }
    result = _build_ai_traffic_assessment(coverage, [])

    assert result.status == "unavailable_no_coverage"
    assert result.predicted_speed is None
