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
    RouteTrafficAssessment,
    TrafficCoverage,
)
from app.routing.traffic_coverage import find_traffic_coverage

router = APIRouter(
    prefix="/api/routing",
    tags=["Routing"],
)


def _build_ai_traffic_assessment(
    coverage: dict,
    traffic_records: list[TrafficRecord],
) -> RouteTrafficAssessment:
    """
    Return an explicit unavailable state until application traffic records
    have a model trained and validated for their own measurement contract.

    PEMS08 sensor inputs are not interchangeable with these simulated-road
    records: in particular, the application does not establish equivalence
    between vehicle_count and detector flow, nor does the PEMS08 speed unit
    have a verified mapping to application km/h. History completeness alone
    cannot make those inputs compatible.
    """

    if not coverage["traffic_coverage"]:
        return RouteTrafficAssessment(
            status="unavailable_no_coverage",
            reason=(
                "Traffic data unavailable for this route: no simulation observations "
                "were found within the match radius."
            ),
        )

    reason = (
        "A prediction is unavailable: the matched observations are simulated "
        "application-road data, while the available model was trained on "
        "PEMS08 loop-sensor data. Vehicle counts are not validated as PEMS08 "
        "flow, and the PEMS08 speed unit has no verified mapping to application "
        "km/h. No model was run and no route score was assigned."
    )
    road_assessments = [
        {
            "road_id": road["road_id"],
            "distance_meters": road["distance_meters"],
            "predicted_speed": None,
            "congestion_level": None,
            "congestion_probabilities": None,
            "route_score": None,
            "status": "unavailable_incompatible_input",
            "reason": reason,
        }
        for road in coverage["matched_roads"]
    ]
    return RouteTrafficAssessment(
        status="unavailable_incompatible_input",
        data_source="simulation",
        roads_assessed=0,
        road_assessments=road_assessments,
        reason=reason,
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
    Calculate routes using OSRM and report nearby simulation-data coverage.

    A matched simulation road receives an explicit
    `unavailable_incompatible_input` assessment. The current endpoint does
    not invoke PEMS08 or assign prediction/route-score values from simulation
    records. Route availability does not depend on traffic assessment.
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
        # Historical behavior used only simulation rows for the route
        # assessment. Keep that boundary explicit until other sources have a
        # validated route-matching and model contract.
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

        for route, coverage in zip(result["routes"], traffic_results):
            ai_traffic = _build_ai_traffic_assessment(coverage, traffic_records)

            route_summaries.append(
                RouteSummary(
                    distance_meters=route["distance"],
                    distance_km=route["distance"] / 1000,
                    duration_seconds=route["duration"],
                    duration_minutes=route["duration"] / 60,
                    geometry=route["geometry"],
                    ai_traffic=ai_traffic,
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
