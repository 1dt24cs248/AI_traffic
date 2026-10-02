"""Nominatim client for OpenStreetMap place search."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

import requests


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"

DEFAULT_USER_AGENT = (
    "AI-Traffic-Flow-Predictor/1.0 "
    "(college student project; set GEOCODING_USER_AGENT with your contact)"
)

CACHE_TTL_SECONDS = 600
CACHE_MAX_SIZE = 256
MIN_REQUEST_INTERVAL_SECONDS = 1.1
MAX_QUEUE_WAIT_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 8.0
RESULT_LIMIT = 5


@dataclass(frozen=True)
class GeocodingPlace:
    display_name: str
    latitude: float
    longitude: float
    type: str | None
    category: str | None


class NominatimError(Exception):
    """Base exception for Nominatim failures."""


class NominatimBusyError(NominatimError):
    """Raised when the rate-limit wait would be too long."""


class NominatimTimeoutError(NominatimError):
    """Raised when Nominatim does not respond in time."""


class NominatimUpstreamError(NominatimError):
    """Raised when Nominatim returns an invalid or unsuccessful response."""


class _TTLCache:
    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, list[GeocodingPlace]]] = (
            OrderedDict()
        )
        self._lock = Lock()

    def get(self, key: str) -> list[GeocodingPlace] | None:
        now = time.monotonic()

        with self._lock:
            item = self._items.get(key)

            if item is None:
                return None

            created_at, value = item

            if now - created_at > self.ttl_seconds:
                del self._items[key]
                return None

            self._items.move_to_end(key)
            return list(value)

    def set(self, key: str, value: list[GeocodingPlace]) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), list(value))
            self._items.move_to_end(key)

            while len(self._items) > self.max_size:
                self._items.popitem(last=False)


_cache = _TTLCache(
    max_size=CACHE_MAX_SIZE,
    ttl_seconds=CACHE_TTL_SECONDS,
)

_rate_lock = Lock()
_last_request_time = 0.0


def _wait_for_rate_limit() -> None:
    global _last_request_time

    with _rate_lock:
        now = time.monotonic()

        elapsed = now - _last_request_time
        wait_seconds = MIN_REQUEST_INTERVAL_SECONDS - elapsed

        if wait_seconds <= 0:
            _last_request_time = now
            return

        if wait_seconds > MAX_QUEUE_WAIT_SECONDS:
            raise NominatimBusyError(
                "Place search is temporarily busy. Please try again shortly."
            )

        time.sleep(wait_seconds)
        _last_request_time = time.monotonic()


def _parse_results(payload: object) -> list[GeocodingPlace]:
    if not isinstance(payload, list):
        raise NominatimUpstreamError(
            "Nominatim returned an unexpected response."
        )

    results: list[GeocodingPlace] = []

    for item in payload[:RESULT_LIMIT]:
        if not isinstance(item, dict):
            continue

        display_name = item.get("display_name")
        lat = item.get("lat")
        lon = item.get("lon")

        if not isinstance(display_name, str):
            continue

        try:
            latitude = float(lat)
            longitude = float(lon)
        except (TypeError, ValueError):
            continue

        results.append(
            GeocodingPlace(
                display_name=display_name,
                latitude=latitude,
                longitude=longitude,
                type=item.get("type"),
                category=item.get("class"),
            )
        )

    return results


def search_places(
    query: str,
    *,
    user_agent: str | None = None,
) -> list[GeocodingPlace]:
    """Search Indian places using OpenStreetMap Nominatim."""

    normalized_query = " ".join(query.strip().split())

    if len(normalized_query) < 2:
        raise ValueError("Search query must contain at least 2 characters.")

    cache_key = normalized_query.casefold()

    cached = _cache.get(cache_key)

    if cached is not None:
        return cached

    _wait_for_rate_limit()

    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept": "application/json",
    }

    params = {
        "q": normalized_query,
        "format": "jsonv2",
        "limit": RESULT_LIMIT,
        "countrycodes": "in",
        "addressdetails": 0,
    }

    try:
        response = requests.get(
            NOMINATIM_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise NominatimTimeoutError(
            "Place search timed out. Please try again."
        ) from exc
    except requests.RequestException as exc:
        raise NominatimUpstreamError(
            "Could not connect to the place-search service."
        ) from exc

    if response.status_code != 200:
        raise NominatimUpstreamError(
            f"Nominatim returned HTTP {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise NominatimUpstreamError(
            "Nominatim returned invalid JSON."
        ) from exc

    results = _parse_results(payload)

    _cache.set(cache_key, results)

    return results