"""Location-based Open-Meteo forecasts used for route comparison."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import threading
import time
from typing import Any

import requests

from app.core.config import settings

PROVIDER = "Open-Meteo"
MAX_ROUTE_SAMPLES = 5
CACHE_TTL_SECONDS = 900
CACHE_STALE_MAX_AGE_SECONDS = 1800
CACHE_MAX_ENTRIES = 256
# Open-Meteo may return separate hourly series for up to 15 sampled points
# (five per route alternative) and a multi-day horizon. Keep connection
# establishment short while allowing the bounded response time needed for
# that batched forecast.
REQUEST_TIMEOUT_SECONDS = (3.05, 15.0)
MAX_REQUEST_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.25
HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "snowfall",
    "weather_code",
)
CURRENT_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
)
_CACHE: dict[tuple[float, float, int], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


class WeatherProviderError(Exception):
    """Raised when a valid forecast cannot be obtained from Open-Meteo."""


def _coordinate_key(latitude: float, longitude: float) -> tuple[float, float]:
    return round(latitude, 3), round(longitude, 3)


def clear_weather_cache() -> None:
    """Clear the process-local forecast cache (primarily useful for tests)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def sample_route_locations(
    coordinates: list[list[float]],
    max_locations: int = MAX_ROUTE_SAMPLES,
) -> list[tuple[float, float]]:
    """Choose up to five actual route vertices at even distance intervals."""
    if max_locations < 1:
        raise ValueError("max_locations must be at least one")
    valid: list[tuple[float, float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            continue
        longitude, latitude = coordinate[0], coordinate[1]
        if (
            isinstance(latitude, (int, float))
            and isinstance(longitude, (int, float))
            and math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            point = (round(float(latitude), 3), round(float(longitude), 3))
            if not valid or point != valid[-1]:
                valid.append(point)
    if not valid:
        return []
    if len(valid) <= max_locations:
        return list(dict.fromkeys(valid))
    segment_lengths = [
        _haversine_meters(valid[index], valid[index + 1])
        for index in range(len(valid) - 1)
    ]
    cumulative = [0.0]
    for segment_length in segment_lengths:
        cumulative.append(cumulative[-1] + segment_length)
    total_length = cumulative[-1]
    if total_length <= 0:
        return [valid[0]]
    if max_locations == 1:
        nearest = min(
            range(len(valid)),
            key=lambda index: abs(cumulative[index] - total_length / 2),
        )
        return [valid[nearest]]

    sampled = []
    for sample_index in range(max_locations):
        target = total_length * sample_index / (max_locations - 1)
        nearest = min(range(len(valid)), key=lambda index: abs(cumulative[index] - target))
        point = valid[nearest]
        if not sampled or point != sampled[-1]:
            sampled.append(point)
    return sampled


def _haversine_meters(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(value))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _normalize_forecast(payload: dict[str, Any]) -> dict[str, Any]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise WeatherProviderError("Weather provider response has no hourly forecast timeline.")
    times = [_parse_datetime(item) for item in hourly["time"]]
    if not times or any(item is None for item in times):
        raise WeatherProviderError("Weather provider returned an invalid hourly forecast timeline.")
    values: dict[str, list[float | int | None]] = {}
    for variable in HOURLY_VARIABLES:
        raw = hourly.get(variable)
        if raw is None:
            values[variable] = [None] * len(times)
            continue
        if not isinstance(raw, list) or len(raw) != len(times):
            raise WeatherProviderError(
                f"Weather provider returned an invalid {variable} forecast series."
            )
        values[variable] = [
            int(value) if variable == "weather_code" and isinstance(value, (int, float))
            and not isinstance(value, bool) and math.isfinite(value)
            else _number(value)
            for value in raw
        ]

    current = payload.get("current")
    if not isinstance(current, dict):
        current = {}
    current_values = {
        variable: (
            int(current[variable])
            if variable == "weather_code"
            and isinstance(current.get(variable), (int, float))
            and not isinstance(current.get(variable), bool)
            and math.isfinite(current[variable])
            else _number(current.get(variable))
        )
        for variable in CURRENT_VARIABLES
    }
    return {
        "hourly_times": times,
        "hourly_values": values,
        "current_time": _parse_datetime(current.get("time")),
        "current_values": current_values,
        "retrieved_at": datetime.now(timezone.utc),
        "stale": False,
    }


def _fetch_forecast_response(url: str, params: dict[str, Any]) -> requests.Response:
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.Timeout as exc:
            if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise WeatherProviderError("Weather provider request timed out.") from exc
        except requests.ConnectionError as exc:
            if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise WeatherProviderError("Weather provider could not be reached.") from exc
        except requests.RequestException as exc:
            raise WeatherProviderError("Weather provider request failed.") from exc

        if response.status_code in (401, 403):
            raise WeatherProviderError(
                f"Weather provider rejected the request (HTTP {response.status_code}); "
                "the public forecast endpoint does not normally require authentication."
            )
        if response.status_code == 429:
            raise WeatherProviderError("Weather provider rate limit reached (HTTP 429).")
        if response.status_code in (500, 502, 503, 504):
            if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise WeatherProviderError(
                f"Weather provider remained unavailable (HTTP {response.status_code}) "
                "after a bounded retry."
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise WeatherProviderError(
                f"Weather provider returned HTTP {response.status_code}."
            )
        return response

    raise WeatherProviderError("Weather provider request attempts were exhausted.")


def get_forecasts(
    locations: list[tuple[float, float]],
    forecast_days: int = 2,
) -> dict[tuple[float, float], dict[str, Any]]:
    """Fetch uncached coordinates in one Open-Meteo multi-location request."""
    if not 1 <= forecast_days <= 7:
        raise ValueError("forecast_days must be between one and seven.")
    unique_locations = list(dict.fromkeys(_coordinate_key(*location) for location in locations))
    now_monotonic = time.monotonic()
    cache_keys = {
        location: (*location, forecast_days)
        for location in unique_locations
    }
    with _CACHE_LOCK:
        for key, (cached_at, _) in list(_CACHE.items()):
            if now_monotonic - cached_at >= CACHE_STALE_MAX_AGE_SECONDS:
                del _CACHE[key]
        cached = {
            location: {**_CACHE[cache_key][1], "stale": False}
            for location, cache_key in cache_keys.items()
            if cache_key in _CACHE
            and now_monotonic - _CACHE[cache_key][0] < CACHE_TTL_SECONDS
        }
        stale_cached = {
            location: _CACHE[cache_key][1]
            for location, cache_key in cache_keys.items()
            if cache_key in _CACHE
            and now_monotonic - _CACHE[cache_key][0] >= CACHE_TTL_SECONDS
        }
    missing = [location for location in unique_locations if location not in cached]
    if missing:
        params = {
            "latitude": ",".join(str(latitude) for latitude, _ in missing),
            "longitude": ",".join(str(longitude) for _, longitude in missing),
            "current": ",".join(CURRENT_VARIABLES),
            "hourly": ",".join(HOURLY_VARIABLES),
            "forecast_days": forecast_days,
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        }
        url = f"{settings.WEATHER_BASE_URL.rstrip('/')}/forecast"
        try:
            response = _fetch_forecast_response(url, params)
        except WeatherProviderError as exc:
            cached.update({
                location: {**forecast, "stale": True, "fallback_reason": str(exc)}
                for location, forecast in stale_cached.items()
            })
            if all(location in cached for location in unique_locations):
                return {location: cached[location] for location in unique_locations}
            raise
        try:
            body = response.json()
        except ValueError as exc:
            raise WeatherProviderError("Weather provider returned invalid JSON.") from exc
        payloads = body if isinstance(body, list) else [body]
        if len(payloads) != len(missing) or any(not isinstance(item, dict) for item in payloads):
            raise WeatherProviderError("Weather provider returned an unexpected location response.")
        normalized = {
            key: _normalize_forecast(payload)
            for key, payload in zip(missing, payloads)
        }
        with _CACHE_LOCK:
            for key, data in normalized.items():
                _CACHE[cache_keys[key]] = (time.monotonic(), data)
            while len(_CACHE) > CACHE_MAX_ENTRIES:
                oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
                del _CACHE[oldest]
        cached.update(normalized)
    return {key: cached[key] for key in unique_locations}


def _weather_index(
    precipitation: float | None,
    wind_speed: float | None,
    wind_gusts: float | None,
    snowfall: float | None,
) -> float | None:
    factors = (
        (precipitation, 0.40, 5.0),
        (wind_speed, 0.25, 60.0),
        (wind_gusts, 0.25, 80.0),
        (snowfall, 0.10, 2.0),
    )
    if any(value is None for value, _, _ in factors):
        return None
    return round(
        sum(weight * min(max(value, 0.0) / threshold, 1.0) * 100
            for value, weight, threshold in factors if value is not None),
        1,
    )


def assess_route_weather(
    locations: list[tuple[float, float]],
    forecasts: dict[tuple[float, float], dict[str, Any]],
    duration_seconds: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize forecasts over the estimated journey window at sampled points."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    journey_end = current_time + timedelta(seconds=max(0.0, duration_seconds))
    first_forecast_hour = current_time.replace(minute=0, second=0, microsecond=0)
    forecast_end_exclusive = journey_end.replace(minute=0, second=0, microsecond=0)
    if journey_end > forecast_end_exclusive:
        forecast_end_exclusive += timedelta(hours=1)

    location_results: list[dict[str, Any]] = []
    route_hourly_values: list[dict[str, float | int | None]] = []
    missing_variables: set[str] = set()
    retrieved_at_values: list[datetime] = []
    stale_fallback_reasons: set[str] = set()
    has_stale_forecast = False
    for latitude, longitude in locations:
        forecast = forecasts.get(_coordinate_key(latitude, longitude))
        if not forecast:
            missing_variables.update(HOURLY_VARIABLES)
            continue
        if forecast.get("stale"):
            has_stale_forecast = True
            if forecast.get("fallback_reason"):
                stale_fallback_reasons.add(forecast["fallback_reason"])
        retrieved_at_values.append(forecast["retrieved_at"])
        selected_indices = [
            index
            for index, timestamp in enumerate(forecast["hourly_times"])
            if first_forecast_hour <= timestamp < forecast_end_exclusive
        ]
        values = forecast["hourly_values"]
        selected = [
            {variable: values[variable][index] for variable in HOURLY_VARIABLES}
            for index in selected_indices
        ]
        if not selected:
            missing_variables.add("hourly_forecast_for_journey")
        for variable in HOURLY_VARIABLES:
            if not selected or any(item[variable] is None for item in selected):
                missing_variables.add(variable)
        route_hourly_values.extend(selected)

        def available_values(variable: str) -> list[float]:
            return [
                float(item[variable])
                for item in selected
                if item[variable] is not None
            ]

        precipitation = available_values("precipitation")
        temperature = available_values("temperature_2m")
        rain = available_values("rain")
        wind_speed = available_values("wind_speed_10m")
        wind_gusts = available_values("wind_gusts_10m")
        snowfall = available_values("snowfall")
        weather_codes = sorted({
            int(item["weather_code"])
            for item in selected
            if item["weather_code"] is not None
        })
        current_values = forecast["current_values"]
        location_results.append({
            "latitude": latitude,
            "longitude": longitude,
            "forecast_hours": len(selected),
            "current_time": forecast["current_time"],
            "current_temperature_c": current_values["temperature_2m"],
            "current_weather_code": current_values["weather_code"],
            "current_precipitation_mm": current_values["precipitation"],
            "current_rain_mm": current_values["rain"],
            "current_wind_speed_kmh": current_values["wind_speed_10m"],
            "current_wind_gusts_kmh": current_values["wind_gusts_10m"],
            "avg_precipitation_mm_per_hour": (
                sum(precipitation) / len(precipitation) if precipitation else None
            ),
            "avg_temperature_c": (
                sum(temperature) / len(temperature) if temperature else None
            ),
            "avg_rain_mm_per_hour": sum(rain) / len(rain) if rain else None,
            "avg_wind_speed_kmh": (
                sum(wind_speed) / len(wind_speed) if wind_speed else None
            ),
            "max_wind_gusts_kmh": max(wind_gusts) if wind_gusts else None,
            "max_snowfall_mm_per_hour": max(snowfall) if snowfall else None,
            "weather_codes": weather_codes,
        })

    covered_count = sum(item["forecast_hours"] > 0 for item in location_results)
    all_variables_present = (
        bool(locations)
        and len(location_results) == len(locations)
        and covered_count == len(locations)
        and not missing_variables
    )
    route_indices = [
        _weather_index(
            item["avg_precipitation_mm_per_hour"],
            item["avg_wind_speed_kmh"],
            item["max_wind_gusts_kmh"],
            item["max_snowfall_mm_per_hour"],
        )
        for item in location_results
    ]
    exposure_index = (
        round(sum(value for value in route_indices if value is not None) / len(route_indices), 1)
        if (
            all_variables_present
            and not has_stale_forecast
            and route_indices
            and all(value is not None for value in route_indices)
        )
        else None
    )
    status = (
        "available"
        if all_variables_present and exposure_index is not None and not has_stale_forecast
        else "partial"
        if covered_count > 0 or has_stale_forecast
        else "unavailable"
    )
    hourly_precipitation = [
        float(item["precipitation"])
        for item in route_hourly_values
        if item["precipitation"] is not None
    ]
    hourly_temperature = [
        float(item["temperature_2m"])
        for item in route_hourly_values
        if item["temperature_2m"] is not None
    ]
    hourly_rain = [
        float(item["rain"])
        for item in route_hourly_values
        if item["rain"] is not None
    ]
    hourly_wind = [
        float(item["wind_speed_10m"])
        for item in route_hourly_values
        if item["wind_speed_10m"] is not None
    ]
    hourly_gusts = [
        float(item["wind_gusts_10m"])
        for item in route_hourly_values
        if item["wind_gusts_10m"] is not None
    ]
    hourly_snow = [
        float(item["snowfall"])
        for item in route_hourly_values
        if item["snowfall"] is not None
    ]
    reason = (
        "Forecasts cover every sampled location and the estimated travel period. "
        "Weather exposure is a rule-based comparison, not a safety assessment."
        if status == "available"
        else "Weather forecast is incomplete for this route; weather ranking is not applied."
        if status == "partial"
        else "No forecast is available for the estimated journey period."
    )
    if missing_variables:
        reason += f" Missing forecast data: {', '.join(sorted(missing_variables))}."
    if has_stale_forecast:
        reason = (
            "A recent cached forecast is shown, but weather ranking is disabled because "
            "the provider could not refresh it. "
            + reason
        )
        if stale_fallback_reasons:
            reason += f" Provider status: {'; '.join(sorted(stale_fallback_reasons))}."

    return {
        "status": status,
        "provider": PROVIDER,
        "retrieved_at": max(retrieved_at_values) if retrieved_at_values else None,
        "forecast_start": current_time,
        "forecast_end": journey_end,
        "sampled_location_count": len(locations),
        "covered_location_count": covered_count,
        "avg_temperature_c": (
            sum(hourly_temperature) / len(hourly_temperature)
            if hourly_temperature else None
        ),
        "avg_precipitation_mm_per_hour": (
            sum(hourly_precipitation) / len(hourly_precipitation)
            if hourly_precipitation else None
        ),
        "avg_rain_mm_per_hour": sum(hourly_rain) / len(hourly_rain) if hourly_rain else None,
        "avg_wind_speed_kmh": sum(hourly_wind) / len(hourly_wind) if hourly_wind else None,
        "max_wind_gusts_kmh": max(hourly_gusts) if hourly_gusts else None,
        "max_snowfall_mm_per_hour": max(hourly_snow) if hourly_snow else None,
        "weather_exposure_index": exposure_index,
        "stale": has_stale_forecast,
        "locations": location_results,
        "reason": reason,
    }
