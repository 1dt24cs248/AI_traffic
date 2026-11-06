from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.api import traffic_routes
from app.traffic.tomtom import (
    ENDPOINT,
    REQUEST_TIMEOUT_SECONDS,
    TomTomRateLimitError,
    TomTomUnavailableError,
    TomTomUpstreamError,
    get_current_flow,
)


def response(payload, status=200, headers=None):
    result = MagicMock()
    result.status_code = status
    result.headers = headers or {}
    result.json.return_value = payload
    return result


def test_current_flow_maps_tomtom_values_and_keeps_api_key_backend_only(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", "test-key")
    payload = {
        "flowSegmentData": {
            "currentSpeed": 31,
            "freeFlowSpeed": 50,
            "currentTravelTime": 120,
            "confidence": 0.82,
            "roadClosure": False,
        }
    }
    with patch("app.traffic.tomtom.requests.get", return_value=response(payload)) as get:
        result = get_current_flow(12.99, 77.55)

    assert result.current_speed == 31
    assert result.free_flow_speed == 50
    assert result.current_travel_time_seconds == 120
    assert result.confidence == 0.82
    assert result.road_closure is False
    assert result.source == "TomTom Traffic Flow API"
    assert result.retrieved_at.tzinfo is not None
    assert result.observation_time is None
    assert get.call_args.args == (ENDPOINT,)
    assert get.call_args.kwargs["params"] == {
        "point": "12.99,77.55",
        "unit": "kmph",
        "key": "test-key",
    }
    assert get.call_args.kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize("coordinates", [(91, 0), (0, 181), (float("nan"), 0)])
def test_rejects_invalid_coordinates_before_network_call(coordinates):
    with patch("app.traffic.tomtom.requests.get") as get:
        with pytest.raises(ValueError):
            get_current_flow(*coordinates)
    get.assert_not_called()


def test_missing_key_does_not_call_provider(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", None)
    with patch("app.traffic.tomtom.requests.get") as get:
        with pytest.raises(TomTomUnavailableError, match="not configured"):
            get_current_flow(12.99, 77.55)
    get.assert_not_called()


def test_rate_limit_is_reported_separately(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", "test-key")
    with patch("app.traffic.tomtom.requests.get", return_value=response({}, 429)):
        with pytest.raises(TomTomRateLimitError, match="limit"):
            get_current_flow(12.99, 77.55)


def test_unavailable_segment_is_not_fabricated(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", "test-key")
    with patch("app.traffic.tomtom.requests.get", return_value=response({}, 200)):
        with pytest.raises(TomTomUnavailableError, match="no traffic-flow segment"):
            get_current_flow(12.99, 77.55)


def test_http_and_malformed_responses_are_reported(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", "test-key")
    with patch("app.traffic.tomtom.requests.get", return_value=response({}, 503)):
        with pytest.raises(TomTomUpstreamError, match="HTTP 503"):
            get_current_flow(12.99, 77.55)

    malformed = response({"flowSegmentData": {"currentSpeed": "fast"}})
    with patch("app.traffic.tomtom.requests.get", return_value=malformed):
        with pytest.raises(TomTomUpstreamError, match="invalid current speed"):
            get_current_flow(12.99, 77.55)


def test_timeout_is_bounded_and_surfaced(monkeypatch):
    monkeypatch.setattr(settings, "TOMTOM_API_KEY", "test-key")
    with patch(
        "app.traffic.tomtom.requests.get",
        side_effect=requests.Timeout("timeout"),
    ) as get:
        with pytest.raises(TomTomUpstreamError, match="timed out"):
            get_current_flow(12.99, 77.55)
    assert get.call_args.kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS


def test_current_flow_endpoint_returns_provider_model(monkeypatch):
    from app.schemas.tomtom import CurrentTrafficFlow

    expected = CurrentTrafficFlow(
        latitude=12.99,
        longitude=77.55,
        current_speed=31,
        free_flow_speed=50,
        current_travel_time_seconds=120,
        confidence=0.82,
        road_closure=False,
        retrieved_at="2026-10-19T10:00:00Z",
    )
    monkeypatch.setattr(traffic_routes, "get_current_flow", lambda lat, lon: expected)
    persist = MagicMock(return_value=True)
    monkeypatch.setattr(
        traffic_routes,
        "persist_tomtom_observation_best_effort",
        persist,
    )

    result = traffic_routes.current_flow(12.99, 77.55, current_user=object())

    assert result == expected
    persist.assert_called_once_with(expected)
    assert set(result.model_dump()) == {
        "latitude",
        "longitude",
        "current_speed",
        "free_flow_speed",
        "current_travel_time_seconds",
        "confidence",
        "road_closure",
        "source",
        "observation_time",
        "retrieved_at",
    }


def test_current_flow_endpoint_keeps_success_response_when_persistence_fails(
    monkeypatch,
):
    from app.schemas.tomtom import CurrentTrafficFlow
    from app.traffic import observation_store

    expected = CurrentTrafficFlow(
        latitude=12.99,
        longitude=77.55,
        current_speed=31,
        free_flow_speed=50,
        confidence=0.82,
        road_closure=False,
        retrieved_at="2026-10-19T10:00:00Z",
    )
    monkeypatch.setattr(traffic_routes, "get_current_flow", lambda lat, lon: expected)

    def fail(_flow):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(observation_store, "persist_tomtom_observation", fail)

    result = traffic_routes.current_flow(12.99, 77.55, current_user=object())

    assert result == expected


def test_current_flow_endpoint_does_not_persist_failed_provider_response(monkeypatch):
    persist = MagicMock()
    monkeypatch.setattr(
        traffic_routes,
        "persist_tomtom_observation_best_effort",
        persist,
    )
    monkeypatch.setattr(
        traffic_routes,
        "get_current_flow",
        MagicMock(side_effect=TomTomUnavailableError("no segment")),
    )

    with pytest.raises(HTTPException) as error:
        traffic_routes.current_flow(12.99, 77.55, current_user=object())

    assert error.value.status_code == 503
    persist.assert_not_called()


def test_live_traffic_endpoints_still_require_authentication(monkeypatch):
    app = FastAPI()
    app.include_router(traffic_routes.router)
    monkeypatch.setattr(traffic_routes, "get_current_flow", MagicMock())
    monkeypatch.setattr(
        traffic_routes,
        "get_route_flow",
        MagicMock(),
    )

    with TestClient(app) as client:
        current = client.get(
            "/api/traffic/current-flow",
            params={"latitude": 12.99, "longitude": 77.55},
        )
        route = client.post(
            "/api/traffic/route-flow",
            json={"coordinates": [[77.0, 12.0], [77.1, 12.1]]},
        )

    assert current.status_code == 401
    assert route.status_code == 401
    traffic_routes.get_current_flow.assert_not_called()
    traffic_routes.get_route_flow.assert_not_called()


@pytest.mark.parametrize(
    ("provider_error", "status_code"),
    [
        (TomTomUnavailableError("not configured"), 503),
        (TomTomRateLimitError("try later"), 429),
        (TomTomUpstreamError("provider failed"), 502),
    ],
)
def test_current_flow_endpoint_maps_provider_errors_to_http_status(
    monkeypatch, provider_error, status_code
):
    from fastapi import HTTPException

    def fail(_latitude, _longitude):
        raise provider_error

    monkeypatch.setattr(traffic_routes, "get_current_flow", fail)
    with pytest.raises(HTTPException) as error:
        traffic_routes.current_flow(12.99, 77.55, current_user=object())
    assert error.value.status_code == status_code
