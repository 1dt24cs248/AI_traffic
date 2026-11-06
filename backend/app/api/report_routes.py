from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.incident import Incident, IncidentStatus
from app.models.simulation_run import SimulationRun
from app.models.user import User
from app.services import analytics


router = APIRouter(prefix="/api/reports", tags=["reports"])


def _apply_date_range(query, column, start_date: date | None, end_date: date | None):
    if start_date:
        query = query.filter(column >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(column < datetime.combine(end_date + timedelta(days=1), time.min))
    return query


@router.get("")
def get_report(
    source: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    run_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )

    traffic_summary = analytics.traffic_summary(db, source, start_date, end_date)
    road_statistics = analytics.road_statistics(db, source, start_date, end_date)
    daily_trend = analytics.daily_trend(db, source, start_date, end_date)
    volume_by_hour = analytics.volume_by_hour(db, None, source, start_date, end_date)
    speed_by_hour = analytics.speed_by_hour(db, None, source, start_date, end_date)

    incident_status_query = _apply_date_range(
        db.query(Incident.status, func.count(Incident.id)),
        Incident.created_at,
        start_date,
        end_date,
    )
    incident_status_counts = {
        incident_status.value: count
        for incident_status, count in incident_status_query.group_by(Incident.status).all()
    }
    incident_severity_query = _apply_date_range(
        db.query(Incident.severity, func.count(Incident.id)),
        Incident.created_at,
        start_date,
        end_date,
    )
    incident_severity_counts = {
        severity.value: count
        for severity, count in incident_severity_query.group_by(Incident.severity).all()
    }
    incident_count_query = _apply_date_range(
        db.query(func.count(Incident.id)),
        Incident.created_at,
        start_date,
        end_date,
    )
    incident_total = incident_count_query.scalar() or 0
    incident_reports_query = _apply_date_range(
        db.query(Incident),
        Incident.created_at,
        start_date,
        end_date,
    )
    # Pending and rejected report details are private to their submitter and moderators.
    incident_reports_query = incident_reports_query.filter(
        Incident.status.in_([IncidentStatus.VERIFIED, IncidentStatus.RESOLVED])
    )
    incident_reports = (
        incident_reports_query
        .order_by(Incident.created_at.desc(), Incident.id.desc())
        .limit(200)
        .all()
    )
    active_alert_query = _apply_date_range(
        db.query(func.count(Incident.id)).filter(
            Incident.verified.is_(True),
            Incident.status == IncidentStatus.VERIFIED,
        ),
        Incident.created_at,
        start_date,
        end_date,
    )
    active_verified_alert_count = active_alert_query.scalar() or 0

    run_query = _apply_date_range(
        db.query(SimulationRun),
        SimulationRun.created_at,
        start_date,
        end_date,
    )
    runs = (
        run_query
        .order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc())
        .limit(run_limit)
        .all()
    )
    run_items = [
        {
            "id": run.id,
            "name": run.name,
            "scenario_type": run.scenario_type,
            "created_at": run.created_at,
            "duration_minutes": run.duration_minutes,
            "record_count": (run.scenario_snapshot or {}).get("record_count", 0),
            "source": "simulation",
        }
        for run in runs
    ]

    run_count_query = _apply_date_range(
        db.query(func.count(SimulationRun.id)),
        SimulationRun.created_at,
        start_date,
        end_date,
    )
    run_count = run_count_query.scalar() or 0

    return {
        "filters": {
            "source": source,
            "start_date": start_date,
            "end_date": end_date,
            "source_applies_to": "traffic_observations",
            "date_range_applies_to": [
                "traffic_observations",
                "incident_reports",
                "simulation_runs_created",
            ],
        },
        "traffic": {
            "summary": traffic_summary,
            "road_statistics": road_statistics,
            "volume_by_hour": volume_by_hour,
            "speed_by_hour": speed_by_hour,
            "daily_trend": daily_trend,
        },
        "incidents": {
            "total": incident_total,
            "by_status": incident_status_counts,
            "by_severity": incident_severity_counts,
            "active_verified_alert_count": active_verified_alert_count,
            "reports": [
                {
                    "id": str(incident.id),
                    "type": incident.type.value,
                    "latitude": incident.latitude,
                    "longitude": incident.longitude,
                    "road_id": incident.road_id,
                    "road_reference": incident.road_reference,
                    "severity": incident.severity.value,
                    "status": incident.status.value,
                    "source": incident.source.value,
                    "verified": incident.verified,
                    "description": incident.description,
                    "created_at": incident.created_at,
                    "verified_at": incident.verified_at,
                    "ended_at": incident.ended_at,
                }
                for incident in incident_reports
            ],
            "displayed_reports": len(incident_reports),
        },
        "simulation_runs": {
            "total": run_count,
            "displayed": len(run_items),
            "records_generated_in_displayed_runs": sum(
                item["record_count"] for item in run_items
            ),
            "runs": run_items,
        },
        "prediction_history": {
            "available": False,
            "reason": "Prediction history is not persisted by the current application.",
        },
    }
