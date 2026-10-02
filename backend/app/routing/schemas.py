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


class RouteSummary(BaseModel):
    distance_meters: float
    distance_km: float
    duration_seconds: float
    duration_minutes: float
    geometry: dict


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