"""
Traffic coverage analysis for OSRM routes.

This module checks whether real traffic observations from the
application database are geographically close enough to an OSRM
route to support traffic-aware routing.

It does not invent traffic information.
"""

from __future__ import annotations

from typing import Iterable

from app.routing.traffic_matcher import nearest_traffic_distance_meters


DEFAULT_MATCH_RADIUS_METERS = 500


def find_traffic_coverage(
    route_coordinates: Iterable[list[float]],
    traffic_records: Iterable[object],
    max_distance_meters: float = DEFAULT_MATCH_RADIUS_METERS,
) -> dict:
    """
    Determine whether traffic observations are available near a route.

    OSRM route coordinates use [longitude, latitude].

    Each traffic record is expected to provide:
        - road_id
        - latitude
        - longitude
    """

    matched_roads = []
    nearest_distances = {}

    for record in traffic_records:
        distance = nearest_traffic_distance_meters(
            route_coordinates,
            record.latitude,
            record.longitude,
        )

        road_id = record.road_id

        if road_id not in nearest_distances:
            nearest_distances[road_id] = distance
        else:
            nearest_distances[road_id] = min(
                nearest_distances[road_id],
                distance,
            )

    for road_id, distance in nearest_distances.items():
        if distance <= max_distance_meters:
            matched_roads.append(
                {
                    "road_id": road_id,
                    "distance_meters": round(distance, 1),
                }
            )

    matched_roads.sort(key=lambda item: item["distance_meters"])

    return {
        "traffic_coverage": bool(matched_roads),
        "matched_roads": matched_roads,
        "match_radius_meters": max_distance_meters,
    }