"""
Spatial matching between OSRM route geometry and application
traffic observations.

This module does NOT invent traffic data. It only reports
traffic observations that are geographically close to a route.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Iterable


EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate the great-circle distance between two coordinates.
    """

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(delta_lon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_METERS * asin(sqrt(a))


def nearest_traffic_distance_meters(
    route_coordinates: Iterable[list[float]],
    traffic_lat: float,
    traffic_lon: float,
) -> float:
    """
    Find the minimum distance from one traffic observation
    to any coordinate in the OSRM route geometry.

    OSRM coordinates are [longitude, latitude].
    """

    minimum_distance = float("inf")

    for coordinate in route_coordinates:
        route_lon, route_lat = coordinate

        distance = haversine_distance_meters(
            route_lat,
            route_lon,
            traffic_lat,
            traffic_lon,
        )

        if distance < minimum_distance:
            minimum_distance = distance

    return minimum_distance