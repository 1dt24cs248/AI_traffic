"""Response models for the geocoding API."""

from pydantic import BaseModel


class GeocodingResult(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    type: str | None = None
    category: str | None = None


class GeocodingSearchResponse(BaseModel):
    query: str
    results: list[GeocodingResult]
    attribution: str = (
        "Search results © OpenStreetMap contributors, provided via Nominatim"
    )