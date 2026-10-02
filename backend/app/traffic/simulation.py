"""
Traffic simulation service.

Generates synthetic traffic time-series data for development,
testing, and research experiments.

IMPORTANT:
Generated records are explicitly stored with source="simulation".
They must not be presented as real-world traffic observations.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.schemas.traffic import TrafficRecordIn


@dataclass(frozen=True)
class SimulationRoad:
    road_id: str
    road_name: str
    latitude: float
    longitude: float
    road_capacity: int
    baseline_volume: float
    baseline_speed: float


DEFAULT_ROADS = [
    SimulationRoad(
        road_id="SIM-NH48-01",
        road_name="Simulation Road 1",
        latitude=13.0098,
        longitude=77.5510,
        road_capacity=150,
        baseline_volume=70,
        baseline_speed=48,
    ),
    SimulationRoad(
        road_id="SIM-NH48-02",
        road_name="Simulation Road 2",
        latitude=13.0150,
        longitude=77.5600,
        road_capacity=120,
        baseline_volume=55,
        baseline_speed=45,
    ),
    SimulationRoad(
        road_id="SIM-NH48-03",
        road_name="Simulation Road 3",
        latitude=13.0200,
        longitude=77.5700,
        road_capacity=180,
        baseline_volume=85,
        baseline_speed=50,
    ),
]


def _rush_hour_multiplier(hour: int) -> float:
    """
    Return a deterministic traffic multiplier based on time of day.

    Morning peak: 07:00-10:00
    Evening peak: 16:00-20:00
    """

    if 7 <= hour <= 9:
        return 1.55

    if 16 <= hour <= 19:
        return 1.65

    if 10 <= hour <= 15:
        return 1.05

    if 20 <= hour <= 22:
        return 0.90

    return 0.65


def _weather_for_timestamp(
    timestamp: datetime,
    rng: random.Random,
) -> tuple[str, float, float]:
    """
    Generate deterministic-but-variable weather conditions.
    """

    bucket = (timestamp.hour + timestamp.day) % 10

    if bucket in (7, 8):
        weather = "RAIN"
        rainfall = round(rng.uniform(1.0, 8.0), 2)
        temperature = round(rng.uniform(22.0, 26.0), 1)

    elif bucket in (5, 6):
        weather = "CLOUDY"
        rainfall = 0.0
        temperature = round(rng.uniform(24.0, 29.0), 1)

    else:
        weather = "CLEAR"
        rainfall = 0.0
        temperature = round(rng.uniform(25.0, 31.0), 1)

    return weather, temperature, rainfall


def _target_volume(
    road: SimulationRoad,
    timestamp: datetime,
    rng: random.Random,
) -> float:
    """
    Calculate the desired traffic volume for the current timestamp.

    This represents the external factors affecting traffic:
    time of day, daily variation, and small random variation.
    """

    multiplier = _rush_hour_multiplier(timestamp.hour)

    daily_wave = 1.0 + 0.08 * math.sin(
        (timestamp.hour + timestamp.minute / 60.0)
        / 24.0
        * 2.0
        * math.pi
    )

    noise = rng.uniform(0.97, 1.03)

    return (
        road.baseline_volume
        * multiplier
        * daily_wave
        * noise
    )


def _generate_record(
    road: SimulationRoad,
    timestamp: datetime,
    rng: random.Random,
    previous_volume: float | None,
) -> tuple[dict, float]:
    """
    Generate one traffic observation.

    The current traffic volume has temporal continuity:
    part of the current value comes from the previous
    five-minute observation.

    Returns
    -------
    tuple[dict, float]
        Validated traffic record and the raw volume state.
    """

    target_volume = _target_volume(
        road=road,
        timestamp=timestamp,
        rng=rng,
    )

    if previous_volume is None:
        raw_volume = target_volume
    else:
        # 70% of the current state is inherited from the
        # previous observation and 30% responds to current
        # time-of-day/environmental conditions.
        raw_volume = (
            0.70 * previous_volume
            + 0.30 * target_volume
        )

    # Small process noise prevents a perfectly smooth series.
    raw_volume *= rng.uniform(0.985, 1.015)

    vehicle_count = max(
        0,
        int(round(raw_volume)),
    )

    utilization = vehicle_count / road.road_capacity

    weather, temperature, rainfall = _weather_for_timestamp(
        timestamp,
        rng,
    )

    # Congestion reduces average speed.
    congestion_factor = min(
        0.70,
        max(0.0, utilization - 0.45) * 0.90,
    )

    if weather == "RAIN":
        congestion_factor += 0.08

    average_speed = road.baseline_speed * (
        1.0 - congestion_factor
    )

    # Small speed variation.
    average_speed *= rng.uniform(0.985, 1.015)

    average_speed = max(
        5.0,
        min(average_speed, 80.0),
    )

    occupancy = min(
        100.0,
        max(
            0.0,
            utilization * 100.0 * rng.uniform(0.96, 1.04),
        ),
    )

    event_indicator = None

    row = {
        "road_id": road.road_id,
        "road_name": road.road_name,
        "latitude": road.latitude,
        "longitude": road.longitude,
        "timestamp": timestamp,
        "vehicle_count": vehicle_count,
        "average_speed": round(average_speed, 2),
        "road_capacity": road.road_capacity,
        "occupancy": round(occupancy, 2),
        "weather_condition": weather,
        "temperature": temperature,
        "rainfall": rainfall,
        "event_indicator": event_indicator,
    }

    # Run the same Pydantic validation used by CSV ingestion.
    validated = TrafficRecordIn(**row)

    return validated.model_dump(), raw_volume


def generate_simulation_rows(
    start_time: datetime,
    duration_minutes: int = 120,
    interval_minutes: int = 5,
    roads: list[SimulationRoad] | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate synthetic traffic observations.

    Parameters
    ----------
    start_time:
        Beginning of the simulation.

    duration_minutes:
        Total simulated duration.

    interval_minutes:
        Time between observations.

    roads:
        Roads to simulate. DEFAULT_ROADS is used when omitted.

    seed:
        Random seed for reproducible results.
    """

    if duration_minutes <= 0:
        raise ValueError(
            "duration_minutes must be greater than zero"
        )

    if interval_minutes <= 0:
        raise ValueError(
            "interval_minutes must be greater than zero"
        )

    if duration_minutes % interval_minutes != 0:
        raise ValueError(
            "duration_minutes must be divisible by interval_minutes"
        )

    selected_roads = roads or DEFAULT_ROADS

    if not selected_roads:
        raise ValueError(
            "At least one simulation road is required"
        )

    rng = random.Random(seed)

    rows: list[dict] = []

    number_of_steps = duration_minutes // interval_minutes

    # Maintain a separate traffic state for every road.
    previous_volumes: dict[str, float] = {}

    for step in range(number_of_steps):
        timestamp = start_time + timedelta(
            minutes=step * interval_minutes
        )

        for road in selected_roads:
            row, raw_volume = _generate_record(
                road=road,
                timestamp=timestamp,
                rng=rng,
                previous_volume=previous_volumes.get(
                    road.road_id
                ),
            )

            previous_volumes[road.road_id] = raw_volume
            rows.append(row)

    return rows