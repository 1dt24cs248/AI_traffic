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
    Route-level AI traffic assessment built from all matched
    application traffic roads associated with the route.

    The route-level result is an aggregation of the individual
    road-level predictions. It does not invent traffic data.
    """

    status: str
    data_source: Optional[str] = None

    # Backward-compatible primary/representative road.
    road_id: Optional[str] = None
    observation_timestamp: Optional[datetime] = None

    # Aggregated route-level prediction.
    predicted_speed: Optional[float] = None
    congestion_level: Optional[str] = None
    congestion_probabilities: Optional[dict[str, float]] = None
    route_score: Optional[int] = None

    # Number of roads actually evaluated for this route.
    roads_assessed: int = 0

    # Individual road-level assessments used to build the route result.
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