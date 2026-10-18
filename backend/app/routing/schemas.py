from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lon: float = Field(..., ge=-180, le=180)
    alternatives: bool = True
    traffic_match_radius_meters: float = Field(
        default=500,
        gt=0,
        le=5000,
    )


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

    # Optional fields retained for response compatibility.
    road_id: Optional[str] = None
    observation_timestamp: Optional[datetime] = None

    # Prediction fields remain null when no compatible model is available.
    predicted_speed: Optional[float] = None
    congestion_level: Optional[str] = None
    congestion_probabilities: Optional[dict[str, float]] = None
    route_score: Optional[int] = None

    # Number of roads actually evaluated by a compatible model.
    roads_assessed: int = 0

    # Per-road availability assessments.
    road_assessments: list[RouteTrafficRoadAssessment] = Field(default_factory=list)

    reason: str

class RouteSummary(BaseModel):
    distance_meters: float
    distance_km: float
    duration_seconds: float
    duration_minutes: float
    geometry: dict
    ai_traffic: Optional[RouteTrafficAssessment] = None


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
