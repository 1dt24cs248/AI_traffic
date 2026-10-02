"""
Generates a SYNTHETIC dataset for testing the preprocessing pipeline mechanics
(lag features, rolling windows, chronological split) — NOT a real traffic dataset
and NOT used for any real model training claims. Clearly labeled everywhere.

Why this exists: Module 2's 7-row sample proves ingestion works, but is too small
to meaningfully test a rolling window or a 70/15/15 time split. This produces enough
rows per road, with a repeatable daily rush-hour pattern, purely so the Module 3
pipeline code can be exercised and verified end-to-end.

Real model training (Module 5) will use an actual public traffic dataset per
Section 19 of the project spec — this script is not a substitute for that.

Run: python ml/data/generate_test_dataset.py
"""
import csv
import math
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible

ROADS = [
    {"road_id": "RD001", "road_name": "MG Road", "lat": 12.9756, "lng": 77.6068, "capacity": 2000, "base_speed": 45},
    {"road_id": "RD002", "road_name": "Hosur Road", "lat": 12.9200, "lng": 77.6300, "capacity": 2500, "base_speed": 55},
    {"road_id": "RD003", "road_name": "Outer Ring Road", "lat": 12.9350, "lng": 77.6950, "capacity": 3000, "base_speed": 65},
]

START = datetime(2026, 9, 1, 0, 0, 0)
INTERVAL_MINUTES = 15
HOURS = 48  # 2 days -> enough rows for a meaningful chronological split
STEPS = int(HOURS * 60 / INTERVAL_MINUTES)


def congestion_factor(hour: float) -> float:
    """Two rush-hour bumps (~8am, ~6pm) using a smooth curve, plus a small random wobble."""
    morning = math.exp(-((hour - 8.5) ** 2) / 3)
    evening = math.exp(-((hour - 18.5) ** 2) / 3)
    return min(1.0, morning + evening)


def main():
    rows = []
    for step in range(STEPS):
        ts = START + timedelta(minutes=INTERVAL_MINUTES * step)
        hour_float = ts.hour + ts.minute / 60

        for road in ROADS:
            cf = congestion_factor(hour_float)  # 0 (free flow) .. 1 (peak congestion)
            noise = random.uniform(-0.05, 0.05)
            cf = max(0.0, min(1.0, cf + noise))

            speed = road["base_speed"] * (1 - 0.75 * cf)  # up to 75% speed reduction at peak
            speed = max(3.0, speed + random.uniform(-1.5, 1.5))

            vehicle_count = int(road["capacity"] * (0.15 + 0.6 * cf) + random.uniform(-15, 15))
            vehicle_count = max(5, vehicle_count)

            occupancy = round(min(100, 20 + 70 * cf), 1)

            rows.append({
                "road_id": road["road_id"],
                "road_name": road["road_name"],
                "latitude": road["lat"],
                "longitude": road["lng"],
                "timestamp": ts.isoformat(),
                "vehicle_count": vehicle_count,
                "average_speed": round(speed, 1),
                "road_capacity": road["capacity"],
                "occupancy": occupancy,
                "weather_condition": "Clear",
                "temperature": round(25 + 3 * math.sin(hour_float / 24 * 2 * math.pi), 1),
                "rainfall": 0,
                "event_indicator": "",
            })

    out_path = "ml/data/synthetic_test_dataset.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} SYNTHETIC rows ({len(ROADS)} roads x {STEPS} timesteps) to {out_path}")


if __name__ == "__main__":
    main()
