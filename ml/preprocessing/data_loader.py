"""
Module 3 — Step 0: reproducible data loading.

Loads traffic_records directly from the same Postgres database the backend writes to,
so the ML pipeline is always working from the current state of real ingested data —
never a hand-copied snapshot that can drift out of sync.

Run standalone: python -m ml.preprocessing.data_loader
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load ../../.env relative to this file so this script works regardless of cwd
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_ENV_PATH)


def load_traffic_records(database_url: str | None = None) -> pd.DataFrame:
    """Load the full traffic_records table as a DataFrame, sorted by road then time."""
    url = database_url or os.environ["DATABASE_URL"]
    engine = create_engine(url)

    query = text("""
        SELECT road_id, road_name, latitude, longitude, timestamp,
               vehicle_count, average_speed, road_capacity, occupancy,
               weather_condition, temperature, rainfall,
               day_of_week, hour, event_indicator, source
        FROM traffic_records
        ORDER BY road_id, timestamp
    """)
    with engine.connect() as conn:
        result = conn.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
    engine.dispose()
    return df


if __name__ == "__main__":
    df = load_traffic_records()
    print(f"Loaded {len(df)} rows across {df['road_id'].nunique()} roads")
    print(df.head())
