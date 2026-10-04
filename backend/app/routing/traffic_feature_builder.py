"""
Builds the PEMS08 model's 20-feature input from the application's simulation
traffic data, for a single road_id, using only observations that genuinely
exist in the database.

THIS MODULE DOES NOT FABRICATE ANYTHING. Every value in the returned feature
dict is either:
  - read directly from a real TrafficRecord row, or
  - a documented, explicit unit/field conversion of one (see below), or
  - derived purely from a timestamp that itself came from a real row.

If any of the five required historical observations (T, T-5m, T-15m, T-30m,
T-1h) is missing for the road, feature building fails with a clear reason
rather than interpolating, carrying forward, or approximating a value.

===========================================================================
DOCUMENTED FIELD/UNIT SUBSTITUTIONS (per approved implementation plan)
===========================================================================

1. flow <- vehicle_count
   The application has no "flow" field. PEMS08's "flow" is a 5-minute vehicle
   count on a freeway loop detector; the application's vehicle_count is a
   5-minute vehicle count on a simulated local/arterial road. These are NOT
   the same instrumentation or traffic regime. This is a demonstration
   substitution, explicitly labeled as such in every response that uses it -
   it is not claimed to be equivalent to a real PEMS08 flow reading.

2. occupancy: application value / 100
   The application stores occupancy as a 0-100 percentage (see
   app/schemas/traffic.py: `occupancy: Optional[float] = Field(ge=0, le=100)`).
   PEMS08's occupancy is a 0-1 ratio (verified range: 0.0 to 0.8955 - see
   docs/DATASETS.md). Dividing by 100 is the only honest conversion here,
   since both represent "fraction of road occupied" - just on different
   scales. This conversion is applied.

3. speed: NOT converted, used as-is
   The PEMS08 model's expected speed unit was never documented anywhere in
   this project's code, docs, or training scripts (confirmed by a direct
   search prior to writing this module - no "mph", "km/h", or unit
   discussion exists anywhere PEMS08 speed is handled). Per the approved
   implementation constraints, unit conversions must NEVER be guessed. The
   application's average_speed (documented km/h, see schemas/traffic.py) is
   therefore passed through completely unconverted. This is a real,
   undocumented unit mismatch risk, and is disclosed in every response that
   uses this feature builder - not silently assumed to be fine.

===========================================================================
Calendar features
===========================================================================
hour / day_of_week / month / is_weekend / is_rush_hour are derived from the
observation's own real `timestamp` - never invented. The rush-hour window
used here (07-09, 16-19) matches app/traffic/simulation.py's own
_rush_hour_multiplier definition, for internal consistency with how this
simulated data was generated. Note this is NOT the same window used in
ml/preprocessing/real_dataset_features.py or pems08_features.py (both use
17-19 for the evening peak) - a pre-existing inconsistency across this
project's modules, not introduced or resolved here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.models.traffic_record import TrafficRecord

# Required lag offsets, in minutes, relative to the most recent observation T.
# Keys match the "_lag_<label>" suffix used in PEMS08's FEATURE_COLUMNS.
REQUIRED_LAG_OFFSETS: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}


@dataclass(frozen=True)
class FeatureBuildResult:
    """Result of attempting to build PEMS08 features for one road."""

    available: bool
    road_id: str
    features: Optional[dict] = None
    observation_timestamp: Optional[datetime] = None
    reason: Optional[str] = None


def _occupancy_ratio(record: TrafficRecord) -> Optional[float]:
    """0-100 (application) -> 0-1 (PEMS08). None if the record has no occupancy."""
    if record.occupancy is None:
        return None
    return record.occupancy / 100.0


def _is_rush_hour(timestamp: datetime) -> bool:
    is_weekend = timestamp.weekday() >= 5  # Monday=0 .. Sunday=6
    if is_weekend:
        return False
    return (7 <= timestamp.hour <= 9) or (16 <= timestamp.hour <= 19)


def build_features_for_road(
    traffic_records: list[TrafficRecord],
    road_id: str,
) -> FeatureBuildResult:
    """
    Attempt to build a complete PEMS08 feature dict for `road_id` from
    `traffic_records` (already fetched from the database, source="simulation").

    `traffic_records` may contain rows for multiple roads - this function
    filters to `road_id` itself, so lag observations can never be sourced
    from a different road.
    """
    records_for_road = [r for r in traffic_records if r.road_id == road_id]

    if not records_for_road:
        return FeatureBuildResult(
            available=False,
            road_id=road_id,
            reason=f"No simulation traffic observations found for road_id '{road_id}'.",
        )

    records_for_road.sort(key=lambda r: r.timestamp, reverse=True)
    latest = records_for_road[0]
    reference_time = latest.timestamp

    by_timestamp: dict[datetime, TrafficRecord] = {r.timestamp: r for r in records_for_road}

    lag_records: dict[str, TrafficRecord] = {}
    for label, minutes in REQUIRED_LAG_OFFSETS.items():
        target_timestamp = reference_time - timedelta(minutes=minutes)
        record = by_timestamp.get(target_timestamp)
        if record is None:
            return FeatureBuildResult(
                available=False,
                road_id=road_id,
                observation_timestamp=reference_time,
                reason=(
                    f"Missing required historical observation for road_id '{road_id}' "
                    f"at T-{label} (expected timestamp {target_timestamp.isoformat()}). "
                    f"Prediction requires exact observations at T, T-5m, T-15m, T-30m and "
                    f"T-1h; none of these are interpolated or approximated."
                ),
            )
        lag_records[label] = record

    current_occupancy = _occupancy_ratio(latest)
    if current_occupancy is None:
        return FeatureBuildResult(
            available=False,
            road_id=road_id,
            observation_timestamp=reference_time,
            reason=f"The current observation for road_id '{road_id}' has no occupancy value recorded.",
        )
    for label, record in lag_records.items():
        if _occupancy_ratio(record) is None:
            return FeatureBuildResult(
                available=False,
                road_id=road_id,
                observation_timestamp=reference_time,
                reason=f"The T-{label} observation for road_id '{road_id}' has no occupancy value recorded.",
            )

    features = {
        "flow": float(latest.vehicle_count),
        "occupancy": current_occupancy,
        "speed": float(latest.average_speed),
        "flow_lag_5m": float(lag_records["5m"].vehicle_count),
        "flow_lag_15m": float(lag_records["15m"].vehicle_count),
        "flow_lag_30m": float(lag_records["30m"].vehicle_count),
        "flow_lag_1h": float(lag_records["1h"].vehicle_count),
        "speed_lag_5m": float(lag_records["5m"].average_speed),
        "speed_lag_15m": float(lag_records["15m"].average_speed),
        "speed_lag_30m": float(lag_records["30m"].average_speed),
        "speed_lag_1h": float(lag_records["1h"].average_speed),
        "occupancy_lag_5m": _occupancy_ratio(lag_records["5m"]),
        "occupancy_lag_15m": _occupancy_ratio(lag_records["15m"]),
        "occupancy_lag_30m": _occupancy_ratio(lag_records["30m"]),
        "occupancy_lag_1h": _occupancy_ratio(lag_records["1h"]),
        "hour": reference_time.hour,
        "day_of_week": reference_time.weekday(),
        "month": reference_time.month,
        "is_weekend": int(reference_time.weekday() >= 5),
        "is_rush_hour": int(_is_rush_hour(reference_time)),
    }

    return FeatureBuildResult(
        available=True,
        road_id=road_id,
        features=features,
        observation_timestamp=reference_time,
    )