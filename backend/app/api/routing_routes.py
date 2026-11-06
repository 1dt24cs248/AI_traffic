"""
Route planning endpoint.

OSRM is used to compute routes. The recommendation engine (rank_routes)
identifies the fastest, shortest, and recommended alternatives using only
OSRM-provided duration and distance values.

ML safety gate
--------------
_build_ai_traffic_assessment() always returns an explicit unavailable status
for simulation-road records. PEMS08 is never called from this endpoint.
That contract is documented and tested separately; do not change it.

Vehicle routing
---------------
Public OSRM supports three profiles: driving, cycling, foot.
Vehicles that map to 'driving' (motorcycle, scooter, truck) receive a
vehicle_profile_note explaining the limitation honestly.
"""
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_

from app.auth.dependencies import get_current_user
from app.core.database import SessionLocal
from app.models.incident import Incident, IncidentStatus
from app.models.traffic_record import TrafficRecord
from app.routing.incident_matching import assess_incidents_for_route
from app.routing.osrm_client import OSRMError, get_route
from app.routing.recommendation import RouteCandidate, rank_routes
from app.routing.schemas import (
    MatchedTrafficRoad,
    OSRM_PROFILE_MAP,
    VEHICLE_PROFILE_NOTES,
    RouteRequest,
    RouteResponse,
    RouteSummary,
    RouteTrafficAssessment,
    TrafficCoverage,
)
from app.routing.traffic_coverage import find_traffic_coverage
from app.routing.weather import (
    PROVIDER as WEATHER_PROVIDER,
    WeatherProviderError,
    assess_route_weather,
    get_forecasts,
    sample_route_locations,
)

router = APIRouter(
    prefix="/api/routing",
    tags=["Routing"],
)


# ---------------------------------------------------------------------------
# ML safety gate — DO NOT MODIFY
# This function is tested by test_routing_traffic_prediction.py and
# test_phase1_foundation.py. Any change that allows PEMS08 to be called
# for simulation-source records is a violation of the safety contract.
# ---------------------------------------------------------------------------
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
@router.post(
    "/routes/refresh",
    response_model=RouteResponse,
)
def calculate_routes(
    request: RouteRequest,
    current_user=Depends(get_current_user),
):
    """
    Calculate routes using OSRM.

    Returns shortest, fastest, and recommended route indices along with
    a plain-English ranking_basis explanation.

    Vehicle routing
    ---------------
    The OSRM profile is chosen from OSRM_PROFILE_MAP based on vehicle_type.
    Vehicles without a dedicated public-OSRM profile receive a
    vehicle_profile_note disclosing the limitation.

    Traffic prediction
    ------------------
    A matched simulation road receives an explicit
    `unavailable_incompatible_input` assessment. PEMS08 is never called.
    Route availability does not depend on traffic assessment.
    """

    # Resolve OSRM profile for the requested vehicle type.
    osrm_profile = OSRM_PROFILE_MAP.get(request.vehicle_type, "driving")
    vehicle_profile_note = VEHICLE_PROFILE_NOTES.get(request.vehicle_type)

    try:
        result = get_route(
            origin_lat=request.origin_lat,
            origin_lon=request.origin_lon,
            destination_lat=request.destination_lat,
            destination_lon=request.destination_lon,
            alternatives=request.alternatives,
            profile=osrm_profile,
        )
    except OSRMError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    db = SessionLocal()

    try:
        # Historical behavior: only simulation rows are used for traffic
        # assessment. Keep that boundary explicit until other sources have a
        # validated route-matching and model contract.
        traffic_records = (
            db.query(TrafficRecord)
            .filter(TrafficRecord.source == "simulation")
            .all()
        )
        incidents_query = db.query(Incident).filter(
            Incident.verified.is_(True),
            Incident.status == IncidentStatus.VERIFIED,
        )
        # Include the current requester's own pending reports as warnings, never
        # as confirmed hazards. Direct unit calls have no resolved dependency user.
        requester_id = getattr(current_user, "id", None)
        if requester_id is not None:
            incidents_query = db.query(Incident).filter(
                or_(
                    and_(
                        Incident.verified.is_(True),
                        Incident.status == IncidentStatus.VERIFIED,
                    ),
                    and_(
                        Incident.status == IncidentStatus.REPORTED,
                        Incident.created_by == requester_id,
                    ),
                )
            )
        incidents = incidents_query.all()
        incidents = [incident for incident in incidents if isinstance(incident, Incident)]

        traffic_results = []

        for route in result["routes"]:
            coverage = find_traffic_coverage(
                route_coordinates=route["geometry"]["coordinates"],
                traffic_records=traffic_records,
                max_distance_meters=request.traffic_match_radius_meters,
            )

            traffic_results.append(coverage)

        route_weather_locations = [
            sample_route_locations(route["geometry"]["coordinates"])
            for route in result["routes"]
        ]
        weather_locations = [
            location
            for route_locations in route_weather_locations
            for location in route_locations
        ]
        weather_error = None
        forecasts = {}
        weather_now = datetime.now(timezone.utc)
        forecast_start = request.departure_datetime or weather_now
        if forecast_start.tzinfo is None:
            forecast_start = forecast_start.replace(tzinfo=timezone.utc)
        forecast_start = forecast_start.astimezone(timezone.utc)
        try:
            longest_route_seconds = max(
                (float(route.get("duration") or 0) for route in result["routes"]),
                default=0,
            )
            forecast_span_seconds = max(
                0.0,
                (forecast_start - weather_now).total_seconds(),
            ) + longest_route_seconds
            forecast_days = min(
                7,
                max(2, ceil(forecast_span_seconds / 86400) + 1),
            )
            forecasts = get_forecasts(weather_locations, forecast_days=forecast_days)
        except WeatherProviderError as exc:
            weather_error = str(exc)
        route_weather = []
        for route, locations in zip(result["routes"], route_weather_locations):
            if weather_error:
                weather_assessment = {
                    "status": "unavailable",
                    "provider": WEATHER_PROVIDER,
                    "sampled_location_count": len(locations),
                    "covered_location_count": 0,
                    "locations": [],
                    "reason": (
                        "Weather-aware ranking is unavailable; ordinary OSRM routing is retained. "
                        f"{weather_error}"
                    ),
                }
            elif not locations:
                weather_assessment = {
                    "status": "unavailable",
                    "provider": WEATHER_PROVIDER,
                    "sampled_location_count": 0,
                    "covered_location_count": 0,
                    "locations": [],
                    "reason": "Route geometry contained no valid coordinates to sample.",
                }
            else:
                weather_assessment = assess_route_weather(
                    locations,
                    forecasts,
                    route["duration"],
                    now=forecast_start,
                )
            route_weather.append(weather_assessment)

        route_summaries = []

        for route, coverage, weather in zip(
            result["routes"],
            traffic_results,
            route_weather,
        ):
            ai_traffic = _build_ai_traffic_assessment(coverage, traffic_records)
            warnings, closure_reasons = assess_incidents_for_route(
                route,
                incidents,
                request.incident_match_radius_meters,
            )
            feasible = not closure_reasons

            route_summaries.append(
                RouteSummary(
                    distance_meters=route["distance"],
                    distance_km=route["distance"] / 1000,
                    duration_seconds=route["duration"],
                    duration_minutes=route["duration"] / 60,
                    geometry=route["geometry"],
                    ai_traffic=ai_traffic,
                    feasible=feasible,
                    infeasibility_reason=(
                        "; ".join(closure_reasons) if closure_reasons else None
                    ),
                    incident_warnings=warnings,
                    vehicle_profile_note=vehicle_profile_note,
                    weather=weather,
                )
            )

        # ------------------------------------------------------------------
        # Route ranking uses OSRM duration/distance and verified closure
        # constraints. It does not estimate incident delays or traffic speeds.
        # ------------------------------------------------------------------
        candidates = [
            RouteCandidate(
                index=i,
                distance_meters=s.distance_meters,
                duration_seconds=s.duration_seconds,
                feasible=s.feasible,
                infeasibility_reason=s.infeasibility_reason or "",
                incident_warnings=[
                    f"{warning.type.replace('_', ' ')} "
                    f"({warning.status}, {warning.source})"
                    for warning in s.incident_warnings
                ],
            )
            for i, s in enumerate(route_summaries)
        ]

        feasible_weather = {
            index: weather["weather_exposure_index"]
            for index, weather in enumerate(route_weather)
            if weather["status"] == "available"
            and weather.get("weather_exposure_index") is not None
        }
        feasible_candidates = [candidate for candidate in candidates if candidate.feasible]
        complete_weather = bool(feasible_candidates) and all(
            candidate.index in feasible_weather
            for candidate in feasible_candidates
        )
        ranking = rank_routes(
            candidates,
            preference=request.route_preference,
            weather_exposure_indexes=feasible_weather if complete_weather else None,
        )
        if feasible_candidates and not complete_weather and ranking.recommended_index is not None:
            weather_reason = next(
                (
                    route_weather[candidate.index]["reason"]
                    for candidate in feasible_candidates
                    if route_weather[candidate.index]["status"] != "available"
                ),
                "Weather exposure data is incomplete for a feasible route.",
            )
            ranking.ranking_basis += (
                f" Weather-aware ranking unavailable; ordinary OSRM ranking is retained. "
                f"{weather_reason}"
            )
        for index, route_summary in enumerate(route_summaries):
            route_summary.comparison_score = (
                ranking.comparison_scores.get(index)
                if ranking.comparison_scores
                else None
            )
        change_reason = None
        if request.previous_recommended_index != ranking.recommended_index:
            previous = request.previous_recommended_index
            if previous is not None:
                old_label = f"Route {previous + 1}"
                new_label = (
                    f"Route {ranking.recommended_index + 1}"
                    if ranking.recommended_index is not None
                    else "no feasible route"
                )
                change_reason = (
                    f"Recommendation changed from {old_label} to {new_label}. "
                    f"{ranking.ranking_basis}"
                )

        # ------------------------------------------------------------------
        # Build combined traffic coverage (unchanged from original behavior)
        # ------------------------------------------------------------------
        matched_roads: dict[str, dict] = {}

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
            recommended_index=ranking.recommended_index,
            fastest_index=ranking.fastest_index,
            shortest_index=ranking.shortest_index,
            ranking_basis=ranking.ranking_basis,
            recommendation_change_reason=change_reason,
            vehicle_type=request.vehicle_type,
            osrm_profile=osrm_profile,
            comparison_method=(
                "Rule-based comparison: 70% normalized OSRM duration/distance and "
                "30% forecast weather-exposure index; verified closures are hard constraints."
                if ranking.comparison_scores
                else "OSRM duration/distance and verified-closure feasibility; "
                "weather ranking unavailable or forecast incomplete."
            ),
        )

    finally:
        db.close()
