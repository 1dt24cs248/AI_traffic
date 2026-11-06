from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.routing.recommendation import RouteCandidate, rank_routes
from app.routing.weather import (
    WeatherProviderError,
    assess_route_weather,
    clear_weather_cache,
    get_forecasts,
    sample_route_locations,
)


def _open_meteo_payload(times=None):
    times = times or [
        "2026-10-19T09:00",
        "2026-10-19T10:00",
        "2026-10-19T11:00",
        "2026-10-19T12:00",
    ]
    return {
        "current": {
            "time": "2026-10-19T10:00",
            "temperature_2m": 24.5,
            "precipitation": 0.1,
            "rain": 0.1,
            "wind_speed_10m": 8.0,
            "wind_gusts_10m": 12.0,
            "weather_code": 2,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [23.0, 24.0, 25.0, 24.0][:len(times)],
            "precipitation": [0.0, 1.0, 2.0, 0.0][:len(times)],
            "rain": [0.0, 1.0, 2.0, 0.0][:len(times)],
            "wind_speed_10m": [5.0, 10.0, 15.0, 8.0][:len(times)],
            "wind_gusts_10m": [8.0, 15.0, 25.0, 10.0][:len(times)],
            "snowfall": [0.0] * len(times),
            "weather_code": [1, 61, 63, 2][:len(times)],
        },
    }


def _response(payload, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    return response


@pytest.fixture(autouse=True)
def clear_cache():
    clear_weather_cache()
    yield
    clear_weather_cache()


def test_samples_actual_route_vertices_evenly_by_distance():
    coords = [[77.0 + index * 0.01, 13.0] for index in range(10)]

    samples = sample_route_locations(coords, max_locations=3)

    assert len(samples) == 3
    assert samples[0] == (13.0, 77.0)
    assert samples[-1] == (13.0, 77.09)
    assert samples[1][1] in {77.04, 77.05}


def test_samples_reject_invalid_points_and_deduplicate():
    assert sample_route_locations([[200, 13], [77, 13], [77, 13]]) == [(13.0, 77.0)]


def test_open_meteo_success_requests_current_hourly_and_batches_locations():
    payload = [_open_meteo_payload(), _open_meteo_payload()]
    first = (13.0, 77.0)
    second = (13.1, 77.1)
    with patch("app.routing.weather.requests.get", return_value=_response(payload)) as request:
        result = get_forecasts([first, second])

    assert set(result) == {first, second}
    assert request.call_count == 1
    assert request.call_args.kwargs["timeout"] == (3.05, 15.0)
    parameters = request.call_args.kwargs["params"]
    assert parameters["latitude"] == "13.0,13.1"
    assert parameters["longitude"] == "77.0,77.1"
    assert parameters["current"] == "temperature_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m,weather_code"
    assert parameters["hourly"] == "temperature_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m,snowfall,weather_code"
    assert parameters["wind_speed_unit"] == "kmh"
    assert parameters["forecast_days"] == 2


def test_forecast_cache_is_scoped_to_requested_horizon():
    with patch(
        "app.routing.weather.requests.get",
        side_effect=[
            _response(_open_meteo_payload()),
            _response(_open_meteo_payload()),
        ],
    ) as request:
        get_forecasts([(13.0, 77.0)], forecast_days=2)
        get_forecasts([(13.0, 77.0)], forecast_days=3)

    assert request.call_count == 2
    assert [
        call.kwargs["params"]["forecast_days"]
        for call in request.call_args_list
    ] == [2, 3]


@pytest.mark.parametrize(
    ("status", "message"),
    [(429, "rate limit"), (503, "HTTP 503")],
)
def test_http_failures_are_reported_as_provider_errors(status, message):
    with patch("app.routing.weather.time.sleep"), patch(
        "app.routing.weather.requests.get", return_value=_response({}, status)
    ) as request:
        with pytest.raises(WeatherProviderError, match=message):
            get_forecasts([(13.0, 77.0)])
    assert request.call_count == (2 if status == 503 else 1)


def test_timeout_is_reported_as_provider_error():
    with patch("app.routing.weather.time.sleep"), patch(
        "app.routing.weather.requests.get",
        side_effect=requests.Timeout("request timed out"),
    ) as request:
        with pytest.raises(WeatherProviderError, match="timed out"):
            get_forecasts([(13.0, 77.0)])
    assert request.call_count == 2
    assert all(call.kwargs["timeout"] == (3.05, 15.0) for call in request.call_args_list)


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_errors_are_distinguished_and_not_retried(status):
    with patch("app.routing.weather.requests.get", return_value=_response({}, status)) as request:
        with pytest.raises(WeatherProviderError, match="does not normally require authentication"):
            get_forecasts([(13.0, 77.0)])
    assert request.call_count == 1


def test_timeout_retries_once_then_returns_success():
    with patch("app.routing.weather.time.sleep"), patch(
        "app.routing.weather.requests.get",
        side_effect=[requests.Timeout(), _response(_open_meteo_payload())],
    ) as request:
        forecasts = get_forecasts([(13.0, 77.0)])
    assert request.call_count == 2
    assert forecasts[(13.0, 77.0)]["stale"] is False


def test_invalid_json_and_response_shapes_are_rejected():
    invalid_json = _response({})
    invalid_json.json.side_effect = ValueError("invalid")
    with patch("app.routing.weather.requests.get", return_value=invalid_json):
        with pytest.raises(WeatherProviderError, match="invalid JSON"):
            get_forecasts([(13.0, 77.0)])

    with patch("app.routing.weather.requests.get", return_value=_response({"unexpected": True})):
        with pytest.raises(WeatherProviderError, match="hourly forecast timeline"):
            get_forecasts([(13.0, 77.0)])


def test_forecast_is_cached_and_reused():
    with patch(
        "app.routing.weather.requests.get",
        return_value=_response(_open_meteo_payload()),
    ) as request:
        first = get_forecasts([(13.0, 77.0)])
        second = get_forecasts([(13.0, 77.0)])

    assert request.call_count == 1
    assert first == second


def test_provider_failure_uses_recent_cache_but_disables_scoring():
    location = (13.0, 77.0)
    monotonic_values = [100.0, 100.0, 100.0 + 901.0]
    with patch(
        "app.routing.weather.time.monotonic",
        side_effect=monotonic_values,
    ), patch(
        "app.routing.weather.requests.get",
        side_effect=[
            _response(_open_meteo_payload()),
            _response({}, 503),
            _response({}, 503),
        ],
    ), patch("app.routing.weather.time.sleep"):
        get_forecasts([location])
        forecasts = get_forecasts([location])

    assert forecasts[location]["stale"] is True
    summary = assess_route_weather(
        [location],
        forecasts,
        duration_seconds=20 * 60,
        now=datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc),
    )
    assert summary["status"] == "partial"
    assert summary["stale"] is True
    assert summary["weather_exposure_index"] is None
    assert "cached forecast" in summary["reason"]
    assert "HTTP 503" in summary["reason"]


def test_forecast_summary_uses_estimated_travel_window_and_reports_freshness():
    location = (13.0, 77.0)
    with patch(
        "app.routing.weather.requests.get",
        return_value=_response(_open_meteo_payload()),
    ):
        forecast = get_forecasts([location])
    summary = assess_route_weather(
        [location],
        forecast,
        duration_seconds=20 * 60,
        now=datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc),
    )

    assert summary["status"] == "available"
    assert summary["forecast_start"] == datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc)
    assert summary["forecast_end"] == datetime(2026, 10, 19, 10, 50, tzinfo=timezone.utc)
    assert summary["avg_precipitation_mm_per_hour"] == 1.0
    assert summary["avg_wind_speed_kmh"] == 10.0
    assert summary["weather_exposure_index"] is not None
    assert summary["retrieved_at"] is not None
    assert summary["locations"][0]["current_temperature_c"] == 24.5


def test_missing_forecast_variables_disable_weather_score():
    payload = _open_meteo_payload()
    del payload["hourly"]["wind_gusts_10m"]
    with patch("app.routing.weather.requests.get", return_value=_response(payload)):
        forecast = get_forecasts([(13.0, 77.0)])
    summary = assess_route_weather(
        [(13.0, 77.0)],
        forecast,
        duration_seconds=20 * 60,
        now=datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc),
    )

    assert summary["status"] == "partial"
    assert summary["weather_exposure_index"] is None
    assert "wind_gusts_10m" in summary["reason"]


def test_weather_weighted_comparison_is_explainable_and_respects_closures():
    candidates = [
        RouteCandidate(index=0, distance_meters=1000, duration_seconds=320, feasible=True),
        RouteCandidate(index=1, distance_meters=1200, duration_seconds=300, feasible=True),
        RouteCandidate(
            index=2,
            distance_meters=900,
            duration_seconds=200,
            feasible=False,
            infeasibility_reason="Verified closure",
        ),
    ]

    result = rank_routes(
        candidates,
        preference="fastest",
        weather_exposure_indexes={0: 0.0, 1: 100.0},
    )

    assert result.recommended_index == 0
    assert result.comparison_scores == {0: 95.3, 1: 70.0}
    assert "70% normalized OSRM duration" in result.ranking_basis
    assert "not a trained AI prediction" in result.ranking_basis
    assert "confirmed road closures" in result.ranking_basis


def test_missing_weather_preserves_ordinary_route_ranking():
    candidates = [
        RouteCandidate(index=0, distance_meters=1000, duration_seconds=600, feasible=True),
        RouteCandidate(index=1, distance_meters=1200, duration_seconds=300, feasible=True),
    ]

    result = rank_routes(candidates, preference="fastest")

    assert result.recommended_index == 1
    assert result.comparison_scores == {}
