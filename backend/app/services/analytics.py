"""
Module 4 — Traffic Analytics.

Every function here runs an actual aggregation query against
traffic_records.

Analytics can optionally be filtered by data source, for example:
    source="simulation"
    source="csv_upload"

If source is omitted, all available sources are included.
"""

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.traffic_record import TrafficRecord


def volume_by_hour(
    db: Session,
    road_id: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Average vehicle_count grouped by hour-of-day."""

    query = db.query(
        TrafficRecord.hour.label("hour"),
        func.avg(TrafficRecord.vehicle_count).label("avg_vehicle_count"),
        func.count(TrafficRecord.id).label("sample_count"),
    )

    if road_id:
        query = query.filter(TrafficRecord.road_id == road_id)

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = (
        query
        .group_by(TrafficRecord.hour)
        .order_by(TrafficRecord.hour)
        .all()
    )

    return [
        {
            "hour": r.hour,
            "avg_vehicle_count": round(r.avg_vehicle_count, 1),
            "sample_count": r.sample_count,
        }
        for r in rows
    ]


def speed_by_hour(
    db: Session,
    road_id: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Average speed grouped by hour-of-day."""

    query = db.query(
        TrafficRecord.hour.label("hour"),
        func.avg(TrafficRecord.average_speed).label("avg_speed"),
        func.count(TrafficRecord.id).label("sample_count"),
    )

    if road_id:
        query = query.filter(TrafficRecord.road_id == road_id)

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = (
        query
        .group_by(TrafficRecord.hour)
        .order_by(TrafficRecord.hour)
        .all()
    )

    return [
        {
            "hour": r.hour,
            "avg_speed": round(r.avg_speed, 1),
            "sample_count": r.sample_count,
        }
        for r in rows
    ]


def weekday_vs_weekend(
    db: Session,
    source: str | None = None,
) -> dict:
    """Compare weekday and weekend traffic."""

    is_weekend = case(
        (TrafficRecord.day_of_week.in_([5, 6]), True),
        else_=False,
    )

    query = db.query(
        is_weekend.label("is_weekend"),
        func.avg(TrafficRecord.average_speed).label("avg_speed"),
        func.avg(TrafficRecord.vehicle_count).label("avg_vehicle_count"),
        func.count(TrafficRecord.id).label("sample_count"),
    )

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = query.group_by(is_weekend).all()

    result = {
        "weekday": None,
        "weekend": None,
    }

    for r in rows:
        key = "weekend" if r.is_weekend else "weekday"

        result[key] = {
            "avg_speed": round(r.avg_speed, 1),
            "avg_vehicle_count": round(r.avg_vehicle_count, 1),
            "sample_count": r.sample_count,
        }

    return result


def road_statistics(
    db: Session,
    source: str | None = None,
) -> list[dict]:
    """Per-road traffic summary."""

    query = db.query(
        TrafficRecord.road_id,
        TrafficRecord.road_name,
        func.avg(TrafficRecord.average_speed).label("avg_speed"),
        func.min(TrafficRecord.average_speed).label("min_speed"),
        func.avg(TrafficRecord.vehicle_count).label("avg_vehicle_count"),
        func.count(TrafficRecord.id).label("sample_count"),
    )

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = (
        query
        .group_by(
            TrafficRecord.road_id,
            TrafficRecord.road_name,
        )
        .order_by(func.avg(TrafficRecord.average_speed))
        .all()
    )

    return [
        {
            "road_id": r.road_id,
            "road_name": r.road_name,
            "avg_speed": round(r.avg_speed, 1),
            "min_speed": round(r.min_speed, 1),
            "avg_vehicle_count": round(r.avg_vehicle_count, 1),
            "sample_count": r.sample_count,
        }
        for r in rows
    ]


def peak_hours(
    db: Session,
    top_n: int = 3,
    source: str | None = None,
) -> list[dict]:
    """Return hours with the lowest average speed."""

    query = db.query(
        TrafficRecord.hour,
        func.avg(TrafficRecord.average_speed).label("avg_speed"),
    )

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = (
        query
        .group_by(TrafficRecord.hour)
        .order_by(func.avg(TrafficRecord.average_speed))
        .limit(top_n)
        .all()
    )

    return [
        {
            "hour": r.hour,
            "avg_speed": round(r.avg_speed, 1),
        }
        for r in rows
    ]


def congestion_heatmap(
    db: Session,
    source: str | None = None,
) -> list[dict]:
    """Return day_of_week × hour average-speed data."""

    query = db.query(
        TrafficRecord.day_of_week,
        TrafficRecord.hour,
        func.avg(TrafficRecord.average_speed).label("avg_speed"),
        func.count(TrafficRecord.id).label("sample_count"),
    )

    if source:
        query = query.filter(TrafficRecord.source == source)

    rows = (
        query
        .group_by(
            TrafficRecord.day_of_week,
            TrafficRecord.hour,
        )
        .order_by(
            TrafficRecord.day_of_week,
            TrafficRecord.hour,
        )
        .all()
    )

    return [
        {
            "day_of_week": r.day_of_week,
            "hour": r.hour,
            "avg_speed": round(r.avg_speed, 1),
            "sample_count": r.sample_count,
        }
        for r in rows
    ]