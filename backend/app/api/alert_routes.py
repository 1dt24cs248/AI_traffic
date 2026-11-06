from datetime import date, datetime, time, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.incident import Incident, IncidentSeverity, IncidentStatus, IncidentType
from app.models.user import User
from app.schemas.alerts import IncidentAlert


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[IncidentAlert])
def list_alerts(
    status_filter: Literal["active", "resolved", "all"] = "active",
    severity: Optional[IncidentSeverity] = None,
    incident_type: Optional[IncidentType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )

    query = db.query(Incident).filter(
        Incident.verified.is_(True),
        Incident.status.in_([IncidentStatus.VERIFIED, IncidentStatus.RESOLVED]),
    )
    if status_filter == "active":
        query = query.filter(Incident.status == IncidentStatus.VERIFIED)
    elif status_filter == "resolved":
        query = query.filter(Incident.status == IncidentStatus.RESOLVED)
    else:
        query = query.filter(
            Incident.status.in_([IncidentStatus.VERIFIED, IncidentStatus.RESOLVED])
        )
    if severity:
        query = query.filter(Incident.severity == severity)
    if incident_type:
        query = query.filter(Incident.type == incident_type)
    if start_date:
        query = query.filter(
            Incident.created_at >= datetime.combine(start_date, time.min)
        )
    if end_date:
        query = query.filter(
            Incident.created_at
            < datetime.combine(end_date + timedelta(days=1), time.min)
        )

    rows = query.order_by(Incident.updated_at.desc(), Incident.created_at.desc()).all()
    return [
        IncidentAlert(
            id=incident.id,
            incident_id=incident.id,
            type=incident.type,
            severity=incident.severity,
            status=(
                "resolved"
                if incident.status == IncidentStatus.RESOLVED
                else "active"
            ),
            latitude=incident.latitude,
            longitude=incident.longitude,
            road_id=incident.road_id,
            road_reference=incident.road_reference,
            description=incident.description,
            source=incident.source,
            created_at=incident.created_at,
            verified_at=incident.verified_at,
            ended_at=incident.ended_at,
        )
        for incident in rows
    ]
