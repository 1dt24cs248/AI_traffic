from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Vehicle types supported by OSRM profiles.
# 'car' and 'motorcycle' and 'scooter' use the OSRM driving profile.
# 'bicycle' uses the OSRM cycling profile.
# 'truck' requires a self-hosted OSRM with the truck profile; not available
# on the public service — the endpoint will return an honest warning.
# ---------------------------------------------------------------------------
VehicleType = Literal["car", "motorcycle", "scooter", "bicycle", "truck"]

OSRM_PROFILE_MAP: dict[str, str] = {
    "car": "driving",
    "motorcycle": "driving",   # public OSRM has no separate motorcycle profile
    "scooter": "driving",      # same as above
    "bicycle": "cycling",
    "truck": "driving",        # truck profile requires self-hosted OSRM
}

VEHICLE_PROFILE_NOTES: dict[str, Optional[str]] = {
    "car": None,
    "motorcycle": (
        "Motorcycle routed using the OSRM 'driving' profile. "
        "Motorcycle-specific access restrictions are not evaluated on the public routing service."
    ),
    "scooter": (
        "Scooter routed using the OSRM 'driving' profile. "
        "Scooter-specific restrictions are not evaluated on the public routing service."
    ),
    "bicycle": None,
    "truck": (
        "Truck routing requires a self-hosted OSRM instance with the 'truck' profile. "
        "This route was calculated using the standard driving profile and may not reflect "
        "height, weight, or hazardous-goods restrictions."
    ),
}


class IncidentWarning(BaseModel):
    """A non-blocking incident near this route."""
    incident_id: str
    type: str
    severity: str
    status: str
    source: str
    verified: bool
    distance_meters: float
    description: Optional[str] = None
    road_reference: Optional[str] = None
    match_basis: str


class RouteRequest(BaseModel):
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lon: float = Field(..., ge=-180, le=180)
    alternatives: bool = True
    traffic_match_radius_meters: float = Field(default=500, gt=0, le=5000)
    vehicle_type: VehicleType = "car"
    route_preference: Literal["fastest", "shortest"] = "fastest"
    # Forecast window anchor. OSRM route duration remains a baseline estimate,
    # but weather can be summarized for the selected departure time.
    departure_datetime: Optional[datetime] = None
    # Radius within which an incident is considered to affect this route
    incident_match_radius_meters: float = Field(default=50, gt=0, le=100)
    # Set by an explicit refresh so recommendation changes can be explained.
    previous_recommended_index: Optional[int] = Field(default=None, ge=0)


class RouteTrafficRoadAssessment(BaseModel):
    road_id: str
    distance_meters: float
    observation_timestamp: Optional[datetime] = None
    predicted_speed: Optional[float] = None
    congestion_level: Optional[str] = None
    congestion_probabilities: Optional[dict[str, float]] = None
    route_score: Optional[int] = None
    status: str
    reason: str


class RouteTrafficAssessment(BaseModel):
    """
    Route-level traffic availability and prediction status.

    Matched simulation records currently produce an unavailable status because
    there is no validated model/input contract for those records.
    """
    status: str
    data_source: Optional[str] = None
    road_id: Optional[str] = None
    observation_timestamp: Optional[datetime] = None
    predicted_speed: Optional[float] = None
    congestion_level: Optional[str] = None
    congestion_probabilities: Optional[dict[str, float]] = None
    route_score: Optional[int] = None
    roads_assessed: int = 0
    road_assessments: list[RouteTrafficRoadAssessment] = Field(default_factory=list)
    reason: str


class WeatherLocationAssessment(BaseModel):
    latitude: float
    longitude: float
    forecast_hours: int
    current_time: Optional[datetime] = None
    current_temperature_c: Optional[float] = None
    current_weather_code: Optional[int] = None
    current_precipitation_mm: Optional[float] = None
    current_rain_mm: Optional[float] = None
    current_wind_speed_kmh: Optional[float] = None
    current_wind_gusts_kmh: Optional[float] = None
    avg_precipitation_mm_per_hour: Optional[float] = None
    avg_rain_mm_per_hour: Optional[float] = None
    avg_wind_speed_kmh: Optional[float] = None
    max_wind_gusts_kmh: Optional[float] = None
    max_snowfall_mm_per_hour: Optional[float] = None
    weather_codes: list[int] = Field(default_factory=list)
    missing_variables: list[str] = Field(default_factory=list)


class RouteWeatherAssessment(BaseModel):
    status: Literal["available", "partial", "unavailable"]
    provider: str = "Open-Meteo"
    stale: bool = False
    retrieved_at: Optional[datetime] = None
    forecast_start: Optional[datetime] = None
    forecast_end: Optional[datetime] = None
    sampled_location_count: int = 0
    covered_location_count: int = 0
    avg_temperature_c: Optional[float] = None
    avg_precipitation_mm_per_hour: Optional[float] = None
    avg_rain_mm_per_hour: Optional[float] = None
    avg_wind_speed_kmh: Optional[float] = None
    max_wind_gusts_kmh: Optional[float] = None
    max_snowfall_mm_per_hour: Optional[float] = None
    weather_exposure_index: Optional[float] = None
    locations: list[WeatherLocationAssessment] = Field(default_factory=list)
    reason: str


class RouteSummary(BaseModel):
    distance_meters: float
    distance_km: float
    duration_seconds: float
    duration_minutes: float
    geometry: dict
    ai_traffic: Optional[RouteTrafficAssessment] = None
    # Feasibility — False when a confirmed road_closure blocks this route
    feasible: bool = True
    infeasibility_reason: Optional[str] = None
    # Non-blocking incident warnings near this route
    incident_warnings: list[IncidentWarning] = Field(default_factory=list)
    # Vehicle profile note (non-null when routing profile is approximate)
    vehicle_profile_note: Optional[str] = None
    weather: Optional[RouteWeatherAssessment] = None
    comparison_score: Optional[float] = None


class MatchedTrafficRoad(BaseModel):
    road_id: str
    distance_meters: float


class TrafficCoverage(BaseModel):
    traffic_coverage: bool
    matched_roads: list[MatchedTrafficRoad]
    match_radius_meters: float


class RouteResponse(BaseModel):
    provider: str
    routes: list[RouteSummary]
    traffic: TrafficCoverage
    # Recommendation indices (0-based into routes list; null if no feasible route)
    recommended_index: Optional[int] = None
    fastest_index: int = 0
    shortest_index: int = 0
    ranking_basis: str = ""
    recommendation_change_reason: Optional[str] = None
    vehicle_type: str = "car"
    osrm_profile: str = "driving"
    comparison_method: str = "OSRM duration/distance and verified-closure feasibility"
