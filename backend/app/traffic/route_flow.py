"""Bounded, cached TomTom sampling for route geometries."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import asin, cos, radians, sin, sqrt
from threading import Lock
from time import monotonic

from app.core.config import settings
from app.schemas.tomtom import CurrentTrafficFlow, RouteTrafficPoint, RouteTrafficResult
from app.traffic.observation_store import persist_tomtom_observation_best_effort
from app.traffic.tomtom import TomTomError, TomTomRateLimitError, get_current_flow

MAX_ROUTE_COORDINATES = 5000
MAX_SAMPLED_POINTS = 6
DEFAULT_SAMPLED_POINTS = settings.TOMTOM_ROUTE_SAMPLE_COUNT
MAX_CONCURRENCY = 3
CACHE_TTL_SECONDS = 60
MAX_CACHE_ENTRIES = 2048
_CACHE: dict[tuple[float, float], tuple[float, CurrentTrafficFlow]] = {}
_CACHE_LOCK = Lock()


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(h))


def sample_route_coordinates(coordinates: list[list[float]], count: int) -> list[tuple[float, float]]:
    """Sample evenly by travelled distance and return (latitude, longitude)."""
    if not 2 <= len(coordinates) <= MAX_ROUTE_COORDINATES:
        raise ValueError(f"Route geometry must contain between 2 and {MAX_ROUTE_COORDINATES} coordinates.")
    points: list[tuple[float, float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            raise ValueError("Route geometry contains an invalid coordinate.")
        lon, lat = coordinate[0], coordinate[1]
        if (isinstance(lon, bool) or isinstance(lat, bool) or
            not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)) or
            not -180 <= lon <= 180 or not -90 <= lat <= 90):
            raise ValueError("Route geometry contains an invalid coordinate.")
        points.append((float(lon), float(lat)))
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance_m(a, b))
    total = cumulative[-1]
    if total == 0:
        return [(points[0][1], points[0][0])]
    actual_count = count
    targets = [total * i / (actual_count - 1) for i in range(actual_count)]
    samples = []
    segment = 1
    for target in targets:
        while segment < len(cumulative) - 1 and cumulative[segment] < target:
            segment += 1
        start, end = cumulative[segment - 1], cumulative[segment]
        ratio = 0 if end == start else (target - start) / (end - start)
        lon1, lat1 = points[segment - 1]
        lon2, lat2 = points[segment]
        samples.append((lat1 + (lat2 - lat1) * ratio, lon1 + (lon2 - lon1) * ratio))
    return samples


def _cached_flow(latitude: float, longitude: float) -> CurrentTrafficFlow:
    key = (round(latitude, 5), round(longitude, 5))
    now = monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and now - entry[0] < CACHE_TTL_SECONDS:
            return entry[1]
        _CACHE.pop(key, None)
    value = get_current_flow(latitude, longitude)
    persist_tomtom_observation_best_effort(value)
    with _CACHE_LOCK:
        now = monotonic()
        expired = [cached_key for cached_key, (created, _) in _CACHE.items() if now - created >= CACHE_TTL_SECONDS]
        for cached_key in expired:
            _CACHE.pop(cached_key, None)
        if len(_CACHE) >= MAX_CACHE_ENTRIES:
            oldest = min(_CACHE, key=lambda cached_key: _CACHE[cached_key][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (now, value)
    return value


def get_route_flow(coordinates: list[list[float]], requested_count: int = DEFAULT_SAMPLED_POINTS) -> RouteTrafficResult:
    if isinstance(requested_count, bool) or not 2 <= requested_count <= MAX_SAMPLED_POINTS:
        raise ValueError(f"Sample count must be between 2 and {MAX_SAMPLED_POINTS}.")
    samples = sample_route_coordinates(coordinates, requested_count)
    results: dict[int, RouteTrafficPoint] = {}
    # The pool is deliberately small and never scales with untrusted input.
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENCY, len(samples))) as pool:
        pending = {pool.submit(_cached_flow, lat, lon): (i, lat, lon) for i, (lat, lon) in enumerate(samples)}
        rate_limited = False
        for future in as_completed(pending):
            i, lat, lon = pending[future]
            try:
                flow = future.result()
                results[i] = RouteTrafficPoint(status="available", flow=flow)
            except TomTomRateLimitError:
                rate_limited = True
                results[i] = RouteTrafficPoint(status="unavailable", latitude=lat, longitude=lon, reason="TomTom request quota reached.")
            except TomTomError as exc:
                results[i] = RouteTrafficPoint(status="unavailable", latitude=lat, longitude=lon, reason=str(exc))
            except Exception:
                results[i] = RouteTrafficPoint(status="unavailable", latitude=lat, longitude=lon, reason="Traffic lookup failed for this sampled point.")
    points = [results[i] for i in range(len(samples))]
    checked = sum(point.status == "available" for point in points)
    status = "available" if checked == len(points) else "partial" if checked else "unavailable"
    reason = "TomTom quota was reached; some sampled points may not have been checked." if rate_limited else None
    return RouteTrafficResult(status=status, sampled_point_count=len(points), checked_point_count=checked, points=points, reason=reason)
