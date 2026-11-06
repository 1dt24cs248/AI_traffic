"""Backend-only client for TomTom's current Flow Segment Data API."""

from datetime import datetime, timezone
import math
from typing import Any

import requests

from app.core.config import settings
from app.schemas.tomtom import CurrentTrafficFlow

ENDPOINT = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
REQUEST_TIMEOUT_SECONDS = 5


class TomTomError(Exception):
    """A safe, user-displayable traffic provider failure."""


class TomTomRateLimitError(TomTomError):
    pass


class TomTomUnavailableError(TomTomError):
    pass


class TomTomUpstreamError(TomTomError):
    pass


def _number(value: Any, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TomTomUpstreamError(f"TomTom returned an invalid {field} value.")
    if not math.isfinite(value) or value < 0:
        raise TomTomUpstreamError(f"TomTom returned an invalid {field} value.")
    return value


def get_current_flow(latitude: float, longitude: float) -> CurrentTrafficFlow:
    """Fetch current flow for one coordinate; never substitutes local/simulated data."""
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Latitude or longitude is outside the valid coordinate range.")

    api_key = settings.TOMTOM_API_KEY
    if not api_key or not api_key.strip():
        raise TomTomUnavailableError("Current traffic data is not configured.")

    try:
        response = requests.get(
            ENDPOINT,
            params={"point": f"{latitude},{longitude}", "unit": "kmph", "key": api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise TomTomUpstreamError("TomTom traffic lookup timed out.") from exc
    except requests.RequestException as exc:
        raise TomTomUpstreamError("TomTom traffic service could not be reached.") from exc

    if response.status_code == 429:
        raise TomTomRateLimitError("TomTom traffic request limit reached. Try again later.")
    if response.status_code in (400, 404):
        raise TomTomUnavailableError("TomTom has no traffic-flow segment for this location.")
    if response.status_code != 200:
        raise TomTomUpstreamError(f"TomTom traffic service returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TomTomUpstreamError("TomTom returned an unreadable traffic response.") from exc
    if not isinstance(payload, dict):
        raise TomTomUpstreamError("TomTom returned an invalid traffic response.")
    flow = payload.get("flowSegmentData")
    if flow is None:
        raise TomTomUnavailableError("TomTom has no traffic-flow segment for this location.")
    if not isinstance(flow, dict):
        raise TomTomUpstreamError("TomTom returned an invalid flow-segment response.")

    speed = _number(flow.get("currentSpeed"), "current speed")
    free_speed = _number(flow.get("freeFlowSpeed"), "free-flow speed")
    travel_time = _number(flow.get("currentTravelTime"), "current travel time")
    confidence = _number(flow.get("confidence"), "confidence")
    if confidence is not None and confidence > 1:
        raise TomTomUpstreamError("TomTom returned an invalid confidence value.")
    closure = flow.get("roadClosure")
    if closure is not None and not isinstance(closure, bool):
        raise TomTomUpstreamError("TomTom returned an invalid road-closure value.")
    if all(value is None for value in (speed, free_speed, travel_time, confidence, closure)):
        raise TomTomUnavailableError("TomTom returned no usable flow data for this location.")

    observation_time = flow.get("dateTime")
    if observation_time is not None:
        if not isinstance(observation_time, str):
            raise TomTomUpstreamError("TomTom returned an invalid observation time.")
        try:
            observation_time = datetime.fromisoformat(observation_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TomTomUpstreamError("TomTom returned an invalid observation time.") from exc

    return CurrentTrafficFlow(
        latitude=latitude,
        longitude=longitude,
        current_speed=speed,
        free_flow_speed=free_speed,
        current_travel_time_seconds=int(travel_time) if travel_time is not None else None,
        confidence=confidence,
        road_closure=closure,
        observation_time=observation_time,
        retrieved_at=datetime.now(timezone.utc),
    )
