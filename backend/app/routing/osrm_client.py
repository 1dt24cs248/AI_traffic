"""
OSRM routing client.

This module communicates with the public OSRM routing service
and returns real road-network route information.

OSRM uses coordinates in:
longitude,latitude
order.
"""

from typing import Any

import requests

from app.core.config import settings


OSRM_BASE_URL = settings.OSRM_BASE_URL


class OSRMError(Exception):
    """Raised when the OSRM routing service returns an error."""


def get_route(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    alternatives: bool = True,
    profile: str = "driving",
) -> dict[str, Any]:
    """
    Request a route from OSRM.

    Parameters
    ----------
    origin_lat, origin_lon:
        Origin coordinates.

    destination_lat, destination_lon:
        Destination coordinates.

    alternatives:
        Ask OSRM to return alternative routes when available.

    profile:
        OSRM routing profile. The public OSRM service supports
        'driving', 'cycling', and 'foot'. Defaults to 'driving'.

    Returns
    -------
    dict
        Structured route information from OSRM.
    """

    coordinates = (
        f"{origin_lon},{origin_lat};"
        f"{destination_lon},{destination_lat}"
    )

    url = f"{OSRM_BASE_URL}/route/v1/{profile}/{coordinates}"

    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "true" if alternatives else "false",
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise OSRMError(
            f"Unable to connect to OSRM: {exc}"
        ) from exc

    if response.status_code != 200:
        raise OSRMError(
            f"OSRM returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise OSRMError("OSRM returned invalid JSON.") from exc

    if data.get("code") != "Ok":
        raise OSRMError(
            f"OSRM routing failed: {data.get('code', 'Unknown error')}"
        )

    routes = data.get("routes", [])

    if not routes:
        raise OSRMError("OSRM returned no routes.")

    return {
        "provider": "OSRM",
        "routes": routes,
        "waypoints": data.get("waypoints", []),
    }