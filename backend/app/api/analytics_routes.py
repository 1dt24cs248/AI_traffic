"""
Module 4 API endpoints.

All endpoints are backed by real aggregation queries in
app/services/analytics.py.

Optional source filtering is supported so dashboards can
separate simulation data from uploaded/live data.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import analytics


router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
)


@router.get("/volume-by-hour")
def get_volume_by_hour(
    road_id: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.volume_by_hour(
        db,
        road_id,
        source,
    )


@router.get("/speed-by-hour")
def get_speed_by_hour(
    road_id: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.speed_by_hour(
        db,
        road_id,
        source,
    )


@router.get("/weekday-vs-weekend")
def get_weekday_vs_weekend(
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.weekday_vs_weekend(
        db,
        source,
    )


@router.get("/road-statistics")
def get_road_statistics(
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.road_statistics(
        db,
        source,
    )


@router.get("/peak-hours")
def get_peak_hours(
    top_n: int = Query(
        default=3,
        ge=1,
        le=24,
    ),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.peak_hours(
        db,
        top_n,
        source,
    )


@router.get("/congestion-heatmap")
def get_congestion_heatmap(
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics.congestion_heatmap(
        db,
        source,
    )