from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.traffic_record import TrafficRecord
from app.services import analytics


@pytest.fixture
def analytics_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[TrafficRecord.__table__])
    with Session(engine) as db:
        db.add_all(
            [
                TrafficRecord(
                    road_id="SIM-1",
                    road_name="Simulation road",
                    latitude=13.0,
                    longitude=77.0,
                    timestamp=datetime(2026, 1, 5, 8),
                    vehicle_count=10,
                    average_speed=20.0,
                    hour=8,
                    day_of_week=0,
                    source="simulation",
                ),
                TrafficRecord(
                    road_id="SIM-1",
                    road_name="Simulation road",
                    latitude=13.0,
                    longitude=77.0,
                    timestamp=datetime(2026, 1, 6, 8),
                    vehicle_count=20,
                    average_speed=40.0,
                    hour=8,
                    day_of_week=1,
                    source="simulation",
                ),
                TrafficRecord(
                    road_id="CSV-1",
                    road_name="Uploaded road",
                    latitude=13.1,
                    longitude=77.1,
                    timestamp=datetime(2026, 1, 7, 9),
                    vehicle_count=100,
                    average_speed=60.0,
                    hour=9,
                    day_of_week=2,
                    source="csv_upload",
                ),
            ]
        )
        db.commit()
        yield db
    engine.dispose()


def test_summary_applies_source_and_inclusive_date_range(analytics_db):
    result = analytics.traffic_summary(
        analytics_db,
        source="simulation",
        start_date=datetime(2026, 1, 6).date(),
        end_date=datetime(2026, 1, 6).date(),
    )

    assert result == {
        "avg_speed": 40.0,
        "avg_vehicle_count": 20.0,
        "sample_count": 1,
        "road_count": 1,
        "first_observation": datetime(2026, 1, 6, 8),
        "last_observation": datetime(2026, 1, 6, 8),
    }


def test_all_analytics_use_the_same_source_and_date_filters(analytics_db):
    start = datetime(2026, 1, 5).date()
    end = datetime(2026, 1, 6).date()

    assert analytics.volume_by_hour(
        analytics_db, source="simulation", start_date=start, end_date=end
    ) == [{"hour": 8, "avg_vehicle_count": 15.0, "sample_count": 2}]
    assert analytics.speed_by_hour(
        analytics_db, source="simulation", start_date=start, end_date=end
    ) == [{"hour": 8, "avg_speed": 30.0, "sample_count": 2}]
    assert analytics.road_statistics(
        analytics_db, source="simulation", start_date=start, end_date=end
    )[0]["sample_count"] == 2
    assert analytics.peak_hours(
        analytics_db, source="simulation", start_date=start, end_date=end
    ) == [{"hour": 8, "avg_speed": 30.0}]
    assert analytics.congestion_heatmap(
        analytics_db, source="simulation", start_date=start, end_date=end
    ) == [
        {"day_of_week": 0, "hour": 8, "avg_speed": 20.0, "sample_count": 1},
        {"day_of_week": 1, "hour": 8, "avg_speed": 40.0, "sample_count": 1},
    ]
    comparison = analytics.weekday_vs_weekend(
        analytics_db, source="simulation", start_date=start, end_date=end
    )
    assert comparison["weekday"]["sample_count"] == 2
    assert comparison["weekend"] is None


def test_empty_filtered_summary_is_explicit(analytics_db):
    result = analytics.traffic_summary(analytics_db, source="missing")

    assert result == {
        "avg_speed": None,
        "avg_vehicle_count": None,
        "sample_count": 0,
        "road_count": 0,
        "first_observation": None,
        "last_observation": None,
    }
