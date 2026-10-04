"""
Deterministic route scoring from a PEMS08 congestion prediction.

===========================================================================
SCORING FORMULA (exact, documented, reproducible)
===========================================================================
route_score = CONGESTION_SCORE_MAP[predicted_congestion_level]

where:
    LOW      -> 100
    MEDIUM   -> 70
    HIGH     -> 40
    SEVERE   -> 10

This is a fixed lookup table, not a statistical or learned function: the
same congestion_level input always produces the same score output, with no
randomness and no hidden state. Higher score = less predicted congestion.

WHY THIS FORMULA AND NOT A SPEED-BASED ONE: a speed-based score would need a
reliable "free-flow speed" baseline for the matched simulation road to
compute a meaningful ratio. No such baseline is available to this module
(SimulationRoad.baseline_speed lives in app/traffic/simulation.py and is not
persisted per-record on TrafficRecord), and inventing one would violate the
no-fabrication requirement. The classification output (congestion_level) is
self-contained and requires no external baseline, so it is used instead.

THIS SCORE IS NOT:
  - a real-world traffic benchmark
  - a probability
  - validated against real-world outcomes for the application's simulated
    roads (see traffic_feature_builder.py's module docstring for why)
It is a deterministic, explainable demonstration score derived from the
PEMS08 model's own classification output.
"""
from __future__ import annotations

CONGESTION_SCORE_MAP: dict[str, int] = {
    "LOW": 100,
    "MEDIUM": 70,
    "HIGH": 40,
    "SEVERE": 10,
}


def compute_route_score(congestion_level: str) -> tuple[int, str]:
    """
    Returns (score, reason). Raises ValueError for an unrecognized
    congestion_level rather than silently defaulting to a score.
    """
    if congestion_level not in CONGESTION_SCORE_MAP:
        raise ValueError(
            f"Unrecognized congestion_level '{congestion_level}' - expected one of "
            f"{sorted(CONGESTION_SCORE_MAP)}."
        )

    score = CONGESTION_SCORE_MAP[congestion_level]
    reason = (
        f"Route score {score}/100, derived deterministically from the predicted "
        f"congestion level '{congestion_level}' using the fixed mapping "
        f"LOW=100, MEDIUM=70, HIGH=40, SEVERE=10. This is a demonstration score "
        f"from simulation-based input, not a validated real-world traffic benchmark."
    )
    return score, reason