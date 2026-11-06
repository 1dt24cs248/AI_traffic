"""Conservative geographic matching of incidents to OSRM route alternatives."""

from __future__ import annotations

import re
from math import cos, radians, sqrt
from typing import Iterable

from app.models.incident import (
    Incident,
    IncidentSource,
    IncidentStatus,
    IncidentType,
)

# Without a road identifier, only a report essentially on the route geometry is
# associated with that road. The wider request radius is only used when an
# explicit road reference can be matched to an OSRM step name/reference.
GEOMETRY_MATCH_METERS = 15.0


def _normalized_reference(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _route_references(route: dict) -> set[str]:
    references: set[str] = set()
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            for field in ("name", "ref"):
                value = step.get(field)
                if isinstance(value, str) and value.strip():
                    references.add(_normalized_reference(value))
    return references


def nearest_route_distance_meters(
    coordinates: Iterable[list[float]],
    latitude: float,
    longitude: float,
) -> float:
    """Measure distance to route segments, not just sampled route vertices."""
    points = list(coordinates)
    if not points:
        return float("inf")
    if len(points) == 1:
        lon, lat = points[0]
        return _local_distance_meters(longitude, latitude, lon, lat)

    minimum = float("inf")
    latitude_scale = 110_540.0
    longitude_scale = 111_320.0 * cos(radians(latitude))
    for start, end in zip(points, points[1:]):
        start_x = (start[0] - longitude) * longitude_scale
        start_y = (start[1] - latitude) * latitude_scale
        end_x = (end[0] - longitude) * longitude_scale
        end_y = (end[1] - latitude) * latitude_scale
        dx = end_x - start_x
        dy = end_y - start_y
        denominator = dx * dx + dy * dy
        fraction = 0.0 if denominator == 0 else max(
            0.0,
            min(1.0, -(start_x * dx + start_y * dy) / denominator),
        )
        distance = sqrt(
            (start_x + fraction * dx) ** 2
            + (start_y + fraction * dy) ** 2
        )
        minimum = min(minimum, distance)
    return minimum


def _local_distance_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    x = (lon2 - lon1) * 111_320.0 * cos(radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 110_540.0
    return sqrt(x * x + y * y)


def assess_incidents_for_route(
    route: dict,
    incidents: Iterable[Incident],
    match_radius_meters: float,
) -> tuple[list[dict], list[str]]:
    """
    Return relevant warnings and verified full closures that block this route.

    A report with a road reference must match an OSRM step name/reference as
    well as the configured geographic radius. Reports without one are only
    associated when the reported point lies within 15 m of the route line.
    Partial obstructions and unverified closures never make a route infeasible.
    """
    coordinates = route.get("geometry", {}).get("coordinates", [])
    route_references = _route_references(route)
    warnings: list[dict] = []
    closure_reasons: list[str] = []

    for incident in incidents:
        if incident.status == IncidentStatus.RESOLVED or incident.ended_at is not None:
            continue

        distance = nearest_route_distance_meters(
            coordinates,
            incident.latitude,
            incident.longitude,
        )
        if incident.road_reference:
            reference = _normalized_reference(incident.road_reference)
            if not reference or reference not in route_references:
                continue
            if distance > match_radius_meters:
                continue
            match_basis = "matched road reference and route proximity"
        else:
            if distance > GEOMETRY_MATCH_METERS:
                continue
            match_basis = "incident point lies on the route geometry"

        warnings.append(
            {
                "incident_id": str(incident.id),
                "type": incident.type.value,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "source": incident.source.value,
                "verified": incident.verified,
                "distance_meters": round(distance, 1),
                "description": incident.description,
                "road_reference": incident.road_reference,
                "match_basis": match_basis,
            }
        )

        if (
            incident.type == IncidentType.ROAD_CLOSURE
            and incident.status == IncidentStatus.VERIFIED
            and incident.verified
            and incident.source not in (IncidentSource.SIMULATION, IncidentSource.DEMO)
        ):
            label = incident.road_reference or incident.description or str(incident.id)
            closure_reasons.append(f"Verified road closure: {label}")

    return warnings, closure_reasons
