from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.core.database import SessionLocal
from app.models.traffic_record import TrafficRecord
from app.routing.osrm_client import OSRMError, get_route
from app.routing.schemas import (
    MatchedTrafficRoad,
    RouteRequest,
    RouteResponse,
    RouteSummary,
    TrafficCoverage,
)
from app.routing.traffic_coverage import find_traffic_coverage


router = APIRouter(
    prefix="/api/routing",
    tags=["Routing"],
)


@router.post(
    "/routes",
    response_model=RouteResponse,
)
def calculate_routes(
    request: RouteRequest,
    current_user=Depends(get_current_user),
):
    """
    Calculate real driving routes using OSRM and report whether
    application traffic observations are geographically available
    near the returned route.
    """

    try:
        result = get_route(
            origin_lat=request.origin_lat,
            origin_lon=request.origin_lon,
            destination_lat=request.destination_lat,
            destination_lon=request.destination_lon,
            alternatives=request.alternatives,
        )
    except OSRMError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    db = SessionLocal()

    try:
        traffic_records = (
            db.query(TrafficRecord)
            .filter(TrafficRecord.source == "simulation")
            .all()
        )

        traffic_results = []

        for route in result["routes"]:
            coverage = find_traffic_coverage(
                route_coordinates=route["geometry"]["coordinates"],
                traffic_records=traffic_records,
                max_distance_meters=request.traffic_match_radius_meters,
            )

            traffic_results.append(coverage)

        route_summaries = []

        for route in result["routes"]:
            route_summaries.append(
                RouteSummary(
                      distance_meters=route["distance"],
                      distance_km=route["distance"] / 1000,
                      duration_seconds=route["duration"],
                      duration_minutes=route["duration"] / 60,
                      geometry=route["geometry"],
          )
     )

        matched_roads = {}

        for coverage in traffic_results:
            for road in coverage["matched_roads"]:
                road_id = road["road_id"]
                distance = road["distance_meters"]

                if (
                    road_id not in matched_roads
                    or distance < matched_roads[road_id]["distance_meters"]
                ):
                    matched_roads[road_id] = road

        combined_matched_roads = [
            MatchedTrafficRoad(**road)
            for road in sorted(
                matched_roads.values(),
                key=lambda item: item["distance_meters"],
            )
        ]

        traffic_coverage = TrafficCoverage(
            traffic_coverage=bool(combined_matched_roads),
            matched_roads=combined_matched_roads,
            match_radius_meters=request.traffic_match_radius_meters,
        )

        return RouteResponse(
            provider=result["provider"],
            routes=route_summaries,
            traffic=traffic_coverage,
        )

    finally:
        db.close()