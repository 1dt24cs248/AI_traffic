from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.core.database import SessionLocal
from app.models.traffic_record import TrafficRecord
from app.prediction.service import predict_congestion, predict_speed
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
from app.routing.traffic_feature_builder import build_features_for_road
from app.routing.traffic_scoring import compute_route_score

router = APIRouter(
    prefix="/api/routing",
    tags=["Routing"],
)

# Prefix prepended to every simulation-derived ai_traffic.reason string, so no
# consumer of this API can see a prediction without also seeing this caveat.
SIMULATION_CAVEAT = "Simulation-based AI estimate; not a validated real-world traffic forecast."


def _build_ai_traffic_assessment(
    coverage: dict,
    traffic_records: list[TrafficRecord],
) -> RouteTrafficAssessment:
    """
    Builds a route-level AI traffic assessment.

    For every matched road, the function attempts to build the required
    feature history and run the AI prediction. When multiple roads have
    valid predictions, their predictions are aggregated into one
    route-level assessment.

    No traffic information is invented. Roads without sufficient history
    are reported as unavailable and are not included in the aggregation.
    """

    if not coverage["traffic_coverage"]:
        return RouteTrafficAssessment(
            status="unavailable_no_coverage",
            reason=(
                "AI traffic data unavailable for this route: no application traffic "
                "observations were found within the match radius."
            ),
        )

    road_assessments = []

    for matched_road in coverage["matched_roads"]:
        road_id = matched_road["road_id"]
        distance_meters = matched_road["distance_meters"]

        feature_result = build_features_for_road(
            traffic_records,
            road_id,
        )

        if not feature_result.available:
            road_assessments.append(
                {
                    "road_id": road_id,
                    "distance_meters": distance_meters,
                    "observation_timestamp": feature_result.observation_timestamp,
                    "predicted_speed": None,
                    "congestion_level": None,
                    "congestion_probabilities": None,
                    "route_score": None,
                    "status": "unavailable_insufficient_history",
                    "reason": feature_result.reason,
                }
            )
            continue

        try:
            predicted_speed = predict_speed(feature_result.features)
            congestion_result = predict_congestion(feature_result.features)

            congestion_level = congestion_result["congestion_level"]
            probabilities = congestion_result.get("probabilities") or {}

            score, score_reason = compute_route_score(congestion_level)

            road_assessments.append(
                {
                    "road_id": road_id,
                    "distance_meters": distance_meters,
                    "observation_timestamp": feature_result.observation_timestamp,
                    "predicted_speed": predicted_speed,
                    "congestion_level": congestion_level,
                    "congestion_probabilities": probabilities,
                    "route_score": score,
                    "status": "available",
                    "reason": (
                        f"{score_reason} Derived from simulation observations for "
                        f"road_id '{road_id}'."
                    ),
                }
            )

        except Exception as exc:  # noqa: BLE001
            road_assessments.append(
                {
                    "road_id": road_id,
                    "distance_meters": distance_meters,
                    "observation_timestamp": feature_result.observation_timestamp,
                    "predicted_speed": None,
                    "congestion_level": None,
                    "congestion_probabilities": None,
                    "route_score": None,
                    "status": "unavailable_prediction_error",
                    "reason": f"AI traffic prediction failed for this road: {exc}",
                }
            )

    available_roads = [
        road
        for road in road_assessments
        if road["status"] == "available"
    ]

    # If no road produced a valid prediction, preserve the most useful
    # status from the closest matched road. This keeps prediction errors
    # distinguishable from insufficient history.
    if not available_roads:
        closest = min(
            road_assessments,
            key=lambda road: road["distance_meters"],
        )

        if closest["status"] == "unavailable_prediction_error":
            return RouteTrafficAssessment(
                status="unavailable_prediction_error",
                data_source="simulation",
                road_id=closest["road_id"],
                observation_timestamp=closest["observation_timestamp"],
                roads_assessed=0,
                reason=closest["reason"],
                road_assessments=road_assessments,
            )

        return RouteTrafficAssessment(
            status="unavailable_insufficient_history",
            data_source="simulation",
            road_id=closest["road_id"],
            observation_timestamp=closest["observation_timestamp"],
            roads_assessed=0,
            reason=(
                "Traffic roads were geographically matched to this route, "
                "but none had sufficient complete history for AI prediction."
            ),
            road_assessments=road_assessments,
        )

    # Backward-compatible behavior for a single usable road.
    #
    # This also means a single route matched to one simulation road retains
    # the exact road-level prediction rather than unnecessarily transforming it.
    if len(available_roads) == 1:
        road = available_roads[0]

        return RouteTrafficAssessment(
            status="available",
            data_source="simulation",
            road_id=road["road_id"],
            observation_timestamp=road["observation_timestamp"],
            predicted_speed=road["predicted_speed"],
            congestion_level=road["congestion_level"],
            congestion_probabilities=road["congestion_probabilities"],
            route_score=road["route_score"],
            roads_assessed=1,
            road_assessments=road_assessments,
            reason=(
                f"{SIMULATION_CAVEAT} {road['reason']} "
                f"Features include a flow<-vehicle_count substitution "
                f"(demo only, not a real PEMS08-equivalent flow sensor) "
                f"and an occupancy 0-100->0-1 conversion; speed was NOT "
                f"unit-converted because PEMS08's expected speed unit is "
                f"not established anywhere in this project."
            ),
        )

    # Multiple valid roads: aggregate their predictions.
    predicted_speed = sum(
        road["predicted_speed"]
        for road in available_roads
    ) / len(available_roads)

    route_score = round(
        sum(
            road["route_score"]
            for road in available_roads
        ) / len(available_roads)
    )

    probability_keys = {
        key
        for road in available_roads
        for key in road["congestion_probabilities"]
    }

    congestion_probabilities = {}

    if probability_keys:
        for key in probability_keys:
            congestion_probabilities[key] = (
                sum(
                    road["congestion_probabilities"].get(key, 0.0)
                    for road in available_roads
                )
                / len(available_roads)
            )

        congestion_level = max(
            congestion_probabilities,
            key=congestion_probabilities.get,
        )
    else:
        # If the prediction service supplied no probabilities, use the
        # deterministic route-level congestion class derived from the
        # average route score.
        if route_score >= 85:
            congestion_level = "LOW"
        elif route_score >= 55:
            congestion_level = "MEDIUM"
        elif route_score >= 25:
            congestion_level = "HIGH"
        else:
            congestion_level = "SEVERE"

    representative_road = min(
        available_roads,
        key=lambda road: road["distance_meters"],
    )

    return RouteTrafficAssessment(
        status="available",
        data_source="simulation",
        road_id=representative_road["road_id"],
        observation_timestamp=representative_road["observation_timestamp"],
        predicted_speed=predicted_speed,
        congestion_level=congestion_level,
        congestion_probabilities=congestion_probabilities,
        route_score=route_score,
        roads_assessed=len(available_roads),
        road_assessments=road_assessments,
        reason=(
            f"{SIMULATION_CAVEAT} Route-level AI assessment aggregated from "
            f"{len(available_roads)} matched roads with complete prediction "
            f"history. Predicted speed and congestion probabilities are "
            f"arithmetic means across those road-level predictions. Features "
            f"include a flow<-vehicle_count substitution (demo only, not a "
            f"real PEMS08-equivalent flow sensor) and an occupancy 0-100->0-1 "
            f"conversion; speed was NOT unit-converted because PEMS08's "
            f"expected speed unit is not established anywhere in this project."
        ),
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

    Each route also gets an additive `ai_traffic` assessment: a PEMS08-model
    prediction built ONLY from real, complete simulation traffic history for
    the nearest matched road, or a clearly-reasoned "unavailable" status when
    coverage or history is insufficient, or prediction itself fails. Routing
    success never depends on AI prediction succeeding.
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