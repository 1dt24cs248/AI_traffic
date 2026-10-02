"""
Module 2 API endpoints:
POST /api/traffic/upload   — CSV upload, requires login
GET  /api/traffic          — list/filter stored records
GET  /api/traffic/{road_id} — records for one road
GET  /api/traffic/summary  — quick counts, used to sanity-check ingestion
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.traffic_record import TrafficRecord
from app.models.user import User
from app.schemas.traffic import TrafficRecordOut, IngestionSummary
from app.traffic.ingestion import ingest_rows, parse_csv_bytes

router = APIRouter(prefix="/api/traffic", tags=["traffic"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — Section 22: maximum upload size


@router.post("/upload", response_model=IngestionSummary, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported in this endpoint")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10MB upload limit")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        rows = parse_csv_bytes(file_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse file as CSV")

    if not rows:
        raise HTTPException(status_code=400, detail="CSV contained no data rows")

    return ingest_rows(db, rows, source="csv_upload")


@router.get("", response_model=list[TrafficRecordOut])
def list_traffic(
    road_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(TrafficRecord)
    if road_id:
        query = query.filter(TrafficRecord.road_id == road_id)
    if start:
        query = query.filter(TrafficRecord.timestamp >= start)
    if end:
        query = query.filter(TrafficRecord.timestamp <= end)
    return query.order_by(TrafficRecord.timestamp.desc()).limit(limit).all()


@router.get("/summary")
def traffic_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total = db.query(func.count(TrafficRecord.id)).scalar()
    distinct_roads = db.query(func.count(func.distinct(TrafficRecord.road_id))).scalar()
    earliest = db.query(func.min(TrafficRecord.timestamp)).scalar()
    latest = db.query(func.max(TrafficRecord.timestamp)).scalar()
    return {
        "total_records": total,
        "distinct_roads": distinct_roads,
        "earliest_timestamp": earliest,
        "latest_timestamp": latest,
    }


@router.get("/{road_id}", response_model=list[TrafficRecordOut])
def get_road_traffic(
    road_id: str,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(TrafficRecord)
        .filter(TrafficRecord.road_id == road_id)
        .order_by(TrafficRecord.timestamp.desc())
        .limit(limit)
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail=f"No traffic records found for road_id '{road_id}'")
    return records
