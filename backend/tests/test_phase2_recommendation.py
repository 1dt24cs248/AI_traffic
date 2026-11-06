"""
Phase 2 tests: Intelligent Route Recommendation

Tests cover:
  - Fastest route selection (OSRM duration)
  - Shortest route selection (OSRM distance)
  - Recommended route selection (default: fastest)
  - Shortest preference selection
  - Feasibility constraint enforcement (infeasible routes skipped)
  - All-infeasible scenario (recommended_index is None)
  - Single-route scenario (always recommended)
  - Unavailable traffic predictions (not fabricated)
  - Incompatible model inputs (safety gate intact)
  - OSRM profile selection per vehicle type
  - Vehicle profile notes for approximate profiles
  - ranking_basis explanation is non-empty and meaningful
  - RouteResponse fields present and correctly typed
  - calculate_routes integration via mocked OSRM + mocked DB
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://test:test@localhost:5432/test_traffic_db",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-phase2")

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_osrm_route(distance: float, duration: float) -> dict:
    return {
        "distance": distance,
        "duration": duration,
        "geometry": {
            "type": "LineString",
            "coordinates": [[77.5, 13.0], [77.6, 13.1]],
        },
    }


def _make_fake_db(records=None):
    """Return a mock that mimics SessionLocal()."""
    db = MagicMock()
    query = MagicMock()
    filtered = MagicMock()
    filtered.all.return_value = records or []
    query.filter.return_value = filtered
    db.query.return_value = query
    return db


# ---------------------------------------------------------------------------
# rank_routes unit tests (extend Phase 1 suite with edge cases)
# ---------------------------------------------------------------------------

class TestRouteRanking:

    def test_fastest_is_lowest_duration(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=1000, duration_seconds=600, feasible=True),
            RouteCandidate(index=1, distance_meters=2000, duration_seconds=120, feasible=True),
            RouteCandidate(index=2, distance_meters=1500, duration_seconds=300, feasible=True),
        ]
        r = rank_routes(c, preference="fastest")
        assert r.fastest_index == 1
        assert r.recommended_index == 1

    def test_shortest_is_lowest_distance(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=1000, duration_seconds=600, feasible=True),
            RouteCandidate(index=1, distance_meters=2000, duration_seconds=120, feasible=True),
            RouteCandidate(index=2, distance_meters=1500, duration_seconds=300, feasible=True),
        ]
        r = rank_routes(c, preference="shortest")
        assert r.shortest_index == 0
        assert r.recommended_index == 0

    def test_fastest_and_shortest_can_differ(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=1000, duration_seconds=600, feasible=True),
            RouteCandidate(index=1, distance_meters=3000, duration_seconds=200, feasible=True),
        ]
        r = rank_routes(c, preference="fastest")
        assert r.fastest_index == 1
        assert r.shortest_index == 0
        # Recommended is fastest when preference is fastest
        assert r.recommended_index == 1

    def test_infeasible_route_excluded_from_recommendation(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(
                index=0, distance_meters=800, duration_seconds=180,
                feasible=False, infeasibility_reason="Road closure: NH48 km 22"
            ),
            RouteCandidate(index=1, distance_meters=1200, duration_seconds=240, feasible=True),
        ]
        r = rank_routes(c, preference="fastest")
        # Fastest overall is route 0, but it's infeasible.
        assert r.fastest_index == 0
        # Recommendation skips infeasible.
        assert r.recommended_index == 1
        assert r.all_infeasible is False

    def test_all_infeasible_returns_none_recommended(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=800, duration_seconds=180,
                           feasible=False, infeasibility_reason="Closure A"),
            RouteCandidate(index=1, distance_meters=1200, duration_seconds=240,
                           feasible=False, infeasibility_reason="Closure B"),
        ]
        r = rank_routes(c)
        assert r.recommended_index is None
        assert r.all_infeasible is True
        assert "No feasible route" in r.ranking_basis

    def test_ranking_basis_is_non_empty(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [RouteCandidate(index=0, distance_meters=1000, duration_seconds=300, feasible=True)]
        r = rank_routes(c)
        assert r.ranking_basis != ""

    def test_ranking_basis_mentions_route_number(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=1000, duration_seconds=300, feasible=True),
            RouteCandidate(index=1, distance_meters=2000, duration_seconds=180, feasible=True),
        ]
        r = rank_routes(c, preference="fastest")
        # Route 2 is fastest (index 1 → Route 2)
        assert "Route 2" in r.ranking_basis

    def test_incident_warnings_included_in_basis(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(
                index=0,
                distance_meters=1000,
                duration_seconds=300,
                feasible=True,
                incident_warnings=["Minor waterlogging reported on NH48"],
            ),
        ]
        r = rank_routes(c)
        assert "waterlogging" in r.ranking_basis

    def test_tie_in_distance_picks_first(self):
        from app.routing.recommendation import RouteCandidate, rank_routes

        c = [
            RouteCandidate(index=0, distance_meters=1000, duration_seconds=300, feasible=True),
            RouteCandidate(index=1, distance_meters=1000, duration_seconds=400, feasible=True),
        ]
        r = rank_routes(c, preference="shortest")
        # Python min() picks the first on tie
        assert r.shortest_index == 0
        assert r.recommended_index == 0


# ---------------------------------------------------------------------------
# OSRM profile and vehicle type mapping
# ---------------------------------------------------------------------------

class TestVehicleProfileMapping:

    def test_car_uses_driving(self):
        from app.routing.schemas import OSRM_PROFILE_MAP
        assert OSRM_PROFILE_MAP["car"] == "driving"

    def test_bicycle_uses_cycling(self):
        from app.routing.schemas import OSRM_PROFILE_MAP
        assert OSRM_PROFILE_MAP["bicycle"] == "cycling"

    def test_motorcycle_uses_driving(self):
        from app.routing.schemas import OSRM_PROFILE_MAP
        assert OSRM_PROFILE_MAP["motorcycle"] == "driving"

    def test_truck_uses_driving(self):
        from app.routing.schemas import OSRM_PROFILE_MAP
        assert OSRM_PROFILE_MAP["truck"] == "driving"

    def test_car_has_no_profile_note(self):
        from app.routing.schemas import VEHICLE_PROFILE_NOTES
        assert VEHICLE_PROFILE_NOTES["car"] is None

    def test_bicycle_has_no_profile_note(self):
        from app.routing.schemas import VEHICLE_PROFILE_NOTES
        assert VEHICLE_PROFILE_NOTES["bicycle"] is None

    def test_motorcycle_has_profile_note(self):
        from app.routing.schemas import VEHICLE_PROFILE_NOTES
        note = VEHICLE_PROFILE_NOTES["motorcycle"]
        assert note is not None
        assert "driving" in note.lower()

    def test_truck_has_profile_note_mentioning_profile(self):
        from app.routing.schemas import VEHICLE_PROFILE_NOTES
        note = VEHICLE_PROFILE_NOTES["truck"]
        assert note is not None
        assert "truck" in note.lower()

    def test_scooter_has_profile_note(self):
        from app.routing.schemas import VEHICLE_PROFILE_NOTES
        assert VEHICLE_PROFILE_NOTES["scooter"] is not None


# ---------------------------------------------------------------------------
# calculate_routes integration tests (mock OSRM + mock DB)
# ---------------------------------------------------------------------------

MOCK_OSRM_TWO_ROUTES = {
    "provider": "OSRM",
    "routes": [
        _make_osrm_route(distance=5000, duration=600),   # route 0: longer, slower
        _make_osrm_route(distance=8000, duration=360),   # route 1: longer dist, faster
    ],
    "waypoints": [],
}

MOCK_OSRM_ONE_ROUTE = {
    "provider": "OSRM",
    "routes": [
        _make_osrm_route(distance=3000, duration=240),
    ],
    "waypoints": [],
}


def _route_request_payload(vehicle_type="car", preference="fastest"):
    return {
        "origin_lat": 13.0,
        "origin_lon": 77.5,
        "destination_lat": 13.1,
        "destination_lon": 77.6,
        "alternatives": True,
        "traffic_match_radius_meters": 500,
        "vehicle_type": vehicle_type,
        "route_preference": preference,
    }


class TestCalculateRoutesIntegration:

    def _call_endpoint(self, osrm_result, request_payload, db_records=None):
        """Call calculate_routes with mocked OSRM + mocked SessionLocal."""
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest

        req = RouteRequest(**request_payload)
        fake_user = MagicMock()
        fake_db = _make_fake_db(db_records or [])

        with patch("app.api.routing_routes.get_route", return_value=osrm_result), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.get_forecasts", return_value={}), \
             patch("app.api.routing_routes.find_traffic_coverage",
                   return_value={"traffic_coverage": False, "matched_roads": []}):
            return calculate_routes(req, fake_user)

    def test_response_has_all_recommendation_fields(self):
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert hasattr(resp, "recommended_index")
        assert hasattr(resp, "fastest_index")
        assert hasattr(resp, "shortest_index")
        assert hasattr(resp, "ranking_basis")
        assert hasattr(resp, "vehicle_type")
        assert hasattr(resp, "osrm_profile")

    def test_fastest_index_identifies_lowest_duration(self):
        # Route 1: duration=360 < Route 0: duration=600
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert resp.fastest_index == 1

    def test_shortest_index_identifies_lowest_distance(self):
        # Route 0: distance=5000 < Route 1: distance=8000
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert resp.shortest_index == 0

    def test_default_preference_recommends_fastest(self):
        # Default preference is 'fastest' → recommended == fastest
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload(preference="fastest"))
        assert resp.recommended_index == resp.fastest_index

    def test_shortest_preference_recommends_shortest(self):
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload(preference="shortest"))
        assert resp.recommended_index == resp.shortest_index

    def test_single_route_is_always_recommended(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload())
        assert resp.recommended_index == 0
        assert resp.fastest_index == 0
        assert resp.shortest_index == 0

    def test_ranking_basis_is_non_empty_string(self):
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert isinstance(resp.ranking_basis, str)
        assert len(resp.ranking_basis) > 0

    def test_vehicle_type_echoed_in_response(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload(vehicle_type="bicycle"))
        assert resp.vehicle_type == "bicycle"

    def test_bicycle_uses_cycling_profile(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload(vehicle_type="bicycle"))
        assert resp.osrm_profile == "cycling"

    def test_car_uses_driving_profile(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload(vehicle_type="car"))
        assert resp.osrm_profile == "driving"

    def test_car_route_summary_has_no_vehicle_profile_note(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload(vehicle_type="car"))
        for summary in resp.routes:
            assert summary.vehicle_profile_note is None

    def test_motorcycle_route_summary_has_profile_note(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload(vehicle_type="motorcycle"))
        for summary in resp.routes:
            assert summary.vehicle_profile_note is not None
            assert "driving" in summary.vehicle_profile_note.lower()

    def test_osrm_error_returns_502(self):
        from fastapi import HTTPException
        from app.api.routing_routes import calculate_routes
        from app.routing.osrm_client import OSRMError
        from app.routing.schemas import RouteRequest

        req = RouteRequest(**_route_request_payload())
        fake_user = MagicMock()

        with patch("app.api.routing_routes.get_route", side_effect=OSRMError("timeout")):
            with pytest.raises(HTTPException) as exc_info:
                calculate_routes(req, fake_user)

        assert exc_info.value.status_code == 502

    def test_traffic_unavailable_does_not_affect_routes(self):
        """Routes are returned even when traffic coverage is zero."""
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert len(resp.routes) == 2
        for s in resp.routes:
            assert s.ai_traffic is not None
            assert s.ai_traffic.status == "unavailable_no_coverage"

    def test_no_traffic_prediction_fabricated(self):
        """predicted_speed and route_score must be None when traffic is unavailable."""
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        for s in resp.routes:
            assert s.ai_traffic.predicted_speed is None
            assert s.ai_traffic.route_score is None
            assert s.ai_traffic.roads_assessed == 0

    def test_ml_safety_gate_preserved_with_simulation_records(self):
        """
        When simulation records match the route, status must be
        'unavailable_incompatible_input' — PEMS08 is never called.
        """
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest

        req = RouteRequest(**_route_request_payload())
        fake_user = MagicMock()
        fake_db = _make_fake_db([])

        # Simulate a coverage hit with a matched road
        coverage_with_match = {
            "traffic_coverage": True,
            "matched_roads": [{"road_id": "SIM-NH48-01", "distance_meters": 42.5}],
        }

        with patch("app.api.routing_routes.get_route", return_value=MOCK_OSRM_ONE_ROUTE), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.get_forecasts", return_value={}), \
             patch("app.api.routing_routes.find_traffic_coverage",
                   return_value=coverage_with_match):
            resp = calculate_routes(req, fake_user)

        for s in resp.routes:
            assert s.ai_traffic.status == "unavailable_incompatible_input"
            assert s.ai_traffic.predicted_speed is None
            assert s.ai_traffic.route_score is None

    def test_db_session_always_closed(self):
        """DB session must be closed even after an exception in coverage."""
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest

        req = RouteRequest(**_route_request_payload())
        fake_user = MagicMock()
        fake_db = _make_fake_db()

        with patch("app.api.routing_routes.get_route", return_value=MOCK_OSRM_ONE_ROUTE), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.find_traffic_coverage",
                   side_effect=RuntimeError("unexpected")):
            with pytest.raises(RuntimeError):
                calculate_routes(req, fake_user)

        fake_db.close.assert_called_once()

    def test_route_summaries_have_correct_distances(self):
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert resp.routes[0].distance_meters == 5000
        assert resp.routes[0].distance_km == pytest.approx(5.0)
        assert resp.routes[1].distance_meters == 8000

    def test_route_summaries_have_correct_durations(self):
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        assert resp.routes[0].duration_seconds == 600
        assert resp.routes[0].duration_minutes == pytest.approx(10.0)
        assert resp.routes[1].duration_seconds == 360
        assert resp.routes[1].duration_minutes == pytest.approx(6.0)

    def test_all_routes_default_feasible(self):
        """Before Phase 5 incident integration, all routes are feasible."""
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        for s in resp.routes:
            assert s.feasible is True
            assert s.infeasibility_reason is None

    def test_no_incident_warnings_before_phase5(self):
        """incident_warnings must be an empty list until Phase 5 is active."""
        resp = self._call_endpoint(MOCK_OSRM_TWO_ROUTES, _route_request_payload())
        for s in resp.routes:
            assert s.incident_warnings == []

    def test_provider_echoed_from_osrm(self):
        resp = self._call_endpoint(MOCK_OSRM_ONE_ROUTE, _route_request_payload())
        assert resp.provider == "OSRM"

    def test_weather_provider_failure_preserves_osrm_route(self):
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest
        from app.routing.weather import WeatherProviderError

        req = RouteRequest(**_route_request_payload())
        fake_db = _make_fake_db([])
        with patch("app.api.routing_routes.get_route", return_value=MOCK_OSRM_TWO_ROUTES), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.get_forecasts", side_effect=WeatherProviderError("rate limit")):
            response = calculate_routes(req, MagicMock())

        assert len(response.routes) == 2
        assert response.recommended_index == response.fastest_index
        assert all(route.weather.status == "unavailable" for route in response.routes)
        assert "ordinary OSRM ranking is retained" in response.ranking_basis
        assert all(route.comparison_score is None for route in response.routes)

    def test_complete_weather_forecasts_are_used_in_route_comparison(self):
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest

        osrm_routes = {
            "provider": "OSRM",
            "routes": [
                _make_osrm_route(distance=5000, duration=330),
                _make_osrm_route(distance=5200, duration=300),
            ],
        }
        weather_assessments = [
            {
                "status": "available",
                "provider": "Open-Meteo",
                "weather_exposure_index": 0.0,
                "sampled_location_count": 2,
                "covered_location_count": 2,
                "locations": [],
                "reason": "Complete forecast.",
            },
            {
                "status": "available",
                "provider": "Open-Meteo",
                "weather_exposure_index": 100.0,
                "sampled_location_count": 2,
                "covered_location_count": 2,
                "locations": [],
                "reason": "Complete forecast.",
            },
        ]
        req = RouteRequest(**_route_request_payload())
        fake_db = _make_fake_db([])
        with patch("app.api.routing_routes.get_route", return_value=osrm_routes), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.get_forecasts", return_value={}) as weather_fetch, \
             patch(
                 "app.api.routing_routes.assess_route_weather",
                 side_effect=weather_assessments,
             ):
            response = calculate_routes(req, MagicMock())

        assert response.recommended_index == 0
        assert response.routes[0].comparison_score == 93.0
        assert response.routes[1].comparison_score == 70.0
        assert "30% forecast weather-exposure index" in response.ranking_basis
        assert "rule-based comparison" in response.comparison_method.lower()
        assert weather_fetch.call_args.kwargs["forecast_days"] == 2

    def test_forecast_horizon_covers_longest_candidate_trip(self):
        from app.api.routing_routes import calculate_routes
        from app.routing.schemas import RouteRequest

        osrm_routes = {
            "provider": "OSRM",
            "routes": [_make_osrm_route(distance=5000, duration=90000)],
        }
        req = RouteRequest(**_route_request_payload())
        fake_db = _make_fake_db([])
        with patch("app.api.routing_routes.get_route", return_value=osrm_routes), \
             patch("app.api.routing_routes.SessionLocal", return_value=fake_db), \
             patch("app.api.routing_routes.get_forecasts", return_value={}) as weather_fetch:
            calculate_routes(req, MagicMock())

        assert weather_fetch.call_args.kwargs["forecast_days"] == 3
