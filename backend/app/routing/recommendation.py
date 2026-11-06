"""
Route recommendation service.

Ranks OSRM route alternatives and identifies:
  - fastest_index : the route with the lowest OSRM-estimated duration
  - shortest_index: the route with the lowest distance
  - recommended_index: the best route after applying hard constraints
    (incidents, vehicle incompatibility) and soft preferences

Ranking logic
-------------
1. Hard constraints remove infeasible routes (confirmed closures that
   block the route). If all routes are infeasible, return None for
   recommended_index and explain why.
2. Among feasible routes, the recommended route is the fastest.
   If the user preference is 'shortest', it is the shortest.
3. ranking_basis is a plain-English explanation of the selection.

This module does NOT invent traffic predictions or delay estimates.
It works with OSRM duration (seconds) and distance (meters) only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteCandidate:
    index: int
    distance_meters: float
    duration_seconds: float
    feasible: bool                  # False if a confirmed hard constraint blocks it
    infeasibility_reason: str = ""  # non-empty when feasible=False
    incident_warnings: list[str] = None  # non-blocking warnings

    def __post_init__(self):
        if self.incident_warnings is None:
            self.incident_warnings = []


@dataclass
class RankingResult:
    fastest_index: int
    shortest_index: int
    recommended_index: Optional[int]
    ranking_basis: str
    all_infeasible: bool = False
    comparison_scores: dict[int, float] | None = None


def rank_routes(
    candidates: list[RouteCandidate],
    preference: str = "fastest",
    weather_exposure_indexes: dict[int, float] | None = None,
) -> RankingResult:
    """
    Rank route candidates and return index selections.

    Parameters
    ----------
    candidates:
        List of RouteCandidate objects, one per OSRM route alternative.
        Must be non-empty.

    preference:
        'fastest'  — recommend lowest duration (default)
        'shortest' — recommend lowest distance

    Returns
    -------
    RankingResult with indices and explanation.
    """
    if not candidates:
        raise ValueError("rank_routes requires at least one candidate")

    # Fastest and shortest are always computed from all routes (feasible or not)
    # so the user can see the best theoretical options even if blocked.
    fastest_index = min(candidates, key=lambda c: c.duration_seconds).index
    shortest_index = min(candidates, key=lambda c: c.distance_meters).index

    feasible = [c for c in candidates if c.feasible]

    if not feasible:
        reasons = "; ".join(
            f"Route {c.index + 1}: {c.infeasibility_reason}"
            for c in candidates
            if not c.feasible
        )
        return RankingResult(
            fastest_index=fastest_index,
            shortest_index=shortest_index,
            recommended_index=None,
            ranking_basis=f"No feasible route available. {reasons}",
            all_infeasible=True,
            comparison_scores={},
        )

    if weather_exposure_indexes is not None and all(
        candidate.index in weather_exposure_indexes
        for candidate in feasible
    ):
        route_measure = (
            (lambda candidate: candidate.distance_meters)
            if preference == "shortest"
            else (lambda candidate: candidate.duration_seconds)
        )
        measures = [route_measure(candidate) for candidate in feasible]
        minimum = min(measures)
        scores: dict[int, float] = {}
        for candidate in feasible:
            travel_cost = (
                min(100.0, max(0.0, (route_measure(candidate) / minimum - 1.0) * 100))
                if minimum > 0
                else 0.0
            )
            weather_cost = weather_exposure_indexes[candidate.index]
            total_cost = 0.70 * travel_cost + 0.30 * weather_cost
            scores[candidate.index] = round(100.0 - total_cost, 1)
        best = max(feasible, key=lambda candidate: scores[candidate.index])
        measure_label = "OSRM distance" if preference == "shortest" else "OSRM duration"
        basis = (
            f"Route {best.index + 1} recommended by a rule-based comparison: "
            f"70% normalized {measure_label} penalty relative to the fastest/shortest feasible "
            f"route (capped at 100) and 30% forecast weather-exposure index "
            f"(score {scores[best.index]:.1f}/100; higher is preferred). "
            "The weather index is not a trained AI prediction or a road-safety assessment."
        )
        blocked = len(candidates) - len(feasible)
        if blocked:
            basis += f" {blocked} route(s) excluded due to confirmed road closures."
        return RankingResult(
            fastest_index=fastest_index,
            shortest_index=shortest_index,
            recommended_index=best.index,
            ranking_basis=basis,
            comparison_scores=scores,
        )

    if preference == "shortest":
        best = min(feasible, key=lambda c: c.distance_meters)
        basis_label = "shortest distance"
    else:
        # Default: fastest
        best = min(feasible, key=lambda c: c.duration_seconds)
        basis_label = "fastest estimated travel time"

    # Build explanation
    if len(feasible) == 1:
        basis = (
            f"Route {best.index + 1} is the only feasible option "
            f"(selected by {basis_label})."
        )
    elif len(candidates) > len(feasible):
        blocked = len(candidates) - len(feasible)
        basis = (
            f"Route {best.index + 1} recommended by {basis_label}. "
            f"{blocked} route(s) excluded due to confirmed road closures or "
            f"vehicle access restrictions."
        )
    else:
        basis = (
            f"Route {best.index + 1} recommended by {basis_label} "
            f"among {len(feasible)} feasible alternative(s)."
        )

    if best.incident_warnings:
        basis += f" Note: {'; '.join(best.incident_warnings)}."

    return RankingResult(
        fastest_index=fastest_index,
        shortest_index=shortest_index,
        recommended_index=best.index,
        ranking_basis=basis,
        comparison_scores={},
    )
