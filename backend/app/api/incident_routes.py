from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.core.database import get_db
from app.models.incident import Incident, IncidentStatus
from app.models.user import User, UserRole
from app.schemas.incidents import IncidentCreate, IncidentOut, IncidentUpdate

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Incident changes could not be saved.",
        ) from exc


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN and payload.source.value != "user_report":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators may create simulated or system incidents.",
        )

    incident = Incident(
        **payload.model_dump(exclude={"source"}),
        source=payload.source,
        started_at=datetime.utcnow(),
        status=IncidentStatus.REPORTED,
        verified=False,
        created_by=current_user.id,
    )
    db.add(incident)
    _commit(db)
    db.refresh(incident)
    return incident


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    status_filter: Optional[IncidentStatus] = Query(default=None, alias="status"),
    include_resolved: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Incident)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(
            or_(
                Incident.status.in_([IncidentStatus.VERIFIED, IncidentStatus.RESOLVED]),
                Incident.created_by == current_user.id,
            )
        )
    if status_filter is not None:
        query = query.filter(Incident.status == status_filter)
    elif not include_resolved:
        query = query.filter(
            Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.REJECTED])
        )
    return (
        query.order_by(Incident.updated_at.desc(), Incident.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/mine", response_model=list[IncidentOut])
def list_my_incidents(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return only the authenticated user's reports and their moderation status."""
    return (
        db.query(Incident)
        .filter(Incident.created_by == current_user.id)
        .order_by(Incident.created_at.desc(), Incident.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None or (
        current_user.role != UserRole.ADMIN
        and incident.created_by != current_user.id
        and incident.status not in (IncidentStatus.VERIFIED, IncidentStatus.RESOLVED)
    ):
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if (
        current_user.role != UserRole.ADMIN
        and incident.created_by != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Not authorized to update this incident.")
    if incident.status != IncidentStatus.REPORTED and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators may update a verified or resolved incident.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    required_fields = {"type", "latitude", "longitude", "severity"}
    if any(field in required_fields and value is None for field, value in changes.items()):
        raise HTTPException(
            status_code=422,
            detail="Type, location, and severity cannot be cleared.",
        )
    for field, value in changes.items():
        setattr(incident, field, value)
    incident.updated_at = datetime.utcnow()
    _commit(db)
    db.refresh(incident)
    return incident


@router.post("/{incident_id}/verify", response_model=IncidentOut)
def verify_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if incident.status != IncidentStatus.REPORTED:
        raise HTTPException(status_code=409, detail="Only pending reports can be verified.")
    incident.status = IncidentStatus.VERIFIED
    incident.verified = True
    incident.verified_at = datetime.utcnow()
    incident.verified_by = admin.id
    incident.updated_at = datetime.utcnow()
    _commit(db)
    db.refresh(incident)
    return incident


@router.post("/{incident_id}/reject", response_model=IncidentOut)
def reject_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reject a pending report. Rejected incidents cannot become active alerts."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if incident.status != IncidentStatus.REPORTED:
        raise HTTPException(status_code=409, detail="Only pending reports can be rejected.")
    incident.status = IncidentStatus.REJECTED
    incident.verified = False
    incident.verified_at = None
    incident.verified_by = None
    incident.updated_at = datetime.utcnow()
    _commit(db)
    db.refresh(incident)
    return incident


@router.post("/{incident_id}/resolve", response_model=IncidentOut)
def resolve_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if current_user.role != UserRole.ADMIN and incident.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this incident.")
    if incident.status == IncidentStatus.RESOLVED:
        return incident
    if (
        current_user.role != UserRole.ADMIN
        and (
            incident.status != IncidentStatus.REPORTED
            or incident.verified
        )
    ):
        raise HTTPException(status_code=403, detail="Not authorized to resolve this incident.")
    now = datetime.utcnow()
    incident.status = IncidentStatus.RESOLVED
    incident.ended_at = now
    incident.updated_at = now
    _commit(db)
    db.refresh(incident)
    return incident
