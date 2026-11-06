from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.simulation_run import SimulationRun
from app.models.traffic_record import TrafficRecord
from app.models.user import User
from app.schemas.simulations import (
    SimulationCreate,
    SimulationRunCreated,
    SimulationRunDetail,
    SimulationRunSummary,
)
from app.schemas.fuel_impact import FuelImpactEstimate, FuelImpactRequest
from app.services.fuel_impact import estimate_fuel_impact
from app.traffic.simulation import generate_simulation_rows


router = APIRouter(prefix="/api/simulations", tags=["simulations"])

SIMULATION_LIMITATIONS = [
    "Generated observations are synthetic and are not live measurements.",
    "No simulation-native future prediction is produced.",
    "The PEMS08 model is not used for application simulation records.",
]


@router.post("/fuel-impact", response_model=FuelImpactEstimate)
def fuel_impact_estimate(
    payload: FuelImpactRequest,
    current_user: User = Depends(get_current_user),
) -> FuelImpactEstimate:
    """Estimate route energy use from a user distance and supplied provider samples."""
    del current_user
    return estimate_fuel_impact(payload)


def _run_metadata(run: SimulationRun) -> dict:
    snapshot = run.scenario_snapshot or {}
    time_range = snapshot.get("time_range") or {}
    return {
        "id": run.id,
        "name": run.name,
        "scenario_type": run.scenario_type,
        "created_at": run.created_at,
        "duration_minutes": run.duration_minutes,
        "interval_minutes": run.interval_minutes,
        "seed": (run.parameters or {}).get("seed", 42),
        "record_count": snapshot.get("record_count", 0),
        "road_count": snapshot.get("road_count", 0),
        "source": "simulation",
        "status": snapshot.get("status", "completed"),
        "start_time": time_range.get("start"),
        "end_time": time_range.get("end"),
    }


@router.post(
    "",
    response_model=SimulationRunCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_simulation(
    payload: SimulationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SimulationRunCreated:
    start_time = payload.start_time
    if start_time is None:
        start_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    elif start_time.tzinfo is not None:
        start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)

    try:
        generated_rows = generate_simulation_rows(
            start_time=start_time,
            duration_minutes=payload.duration_minutes,
            interval_minutes=payload.interval_minutes,
            seed=payload.seed,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if not generated_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The simulation generator produced no observations.",
        )

    row_keys = [
        (row["road_id"], row["timestamp"])
        for row in generated_rows
    ]
    if len(row_keys) != len(set(row_keys)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The generated simulation contains duplicate road/timestamp observations.",
        )

    road_ids = sorted({row["road_id"] for row in generated_rows})
    timestamps = sorted({row["timestamp"] for row in generated_rows})
    existing_keys = set(
        db.query(TrafficRecord.road_id, TrafficRecord.timestamp)
        .filter(
            TrafficRecord.road_id.in_(road_ids),
            TrafficRecord.timestamp.in_(timestamps),
        )
        .all()
    )
    collisions = existing_keys.intersection(row_keys)
    if collisions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Simulation timestamps overlap existing traffic observations. "
                "Choose a different start time; existing data was not changed."
            ),
        )

    records = [
        TrafficRecord(
            **row,
            day_of_week=row["timestamp"].weekday(),
            hour=row["timestamp"].hour,
            source="simulation",
        )
        for row in generated_rows
    ]

    actual_start = min(row["timestamp"] for row in generated_rows)
    actual_end = max(row["timestamp"] for row in generated_rows)
    road_summaries = []
    for road_id in road_ids:
        road_rows = [row for row in generated_rows if row["road_id"] == road_id]
        road_summaries.append(
            {
                "road_id": road_id,
                "road_name": road_rows[0]["road_name"],
                "record_count": len(road_rows),
                "average_speed_kmh": round(
                    sum(row["average_speed"] for row in road_rows) / len(road_rows),
                    2,
                ),
                "average_vehicle_count": round(
                    sum(row["vehicle_count"] for row in road_rows) / len(road_rows),
                    2,
                ),
            }
        )

    parameters = {
        "seed": payload.seed,
        "start_time": actual_start.isoformat(),
        "duration_minutes": payload.duration_minutes,
        "interval_minutes": payload.interval_minutes,
        "road_ids": road_ids,
    }
    scenario_snapshot = {
        "status": "completed",
        "source": "simulation",
        "record_count": len(records),
        "road_count": len(road_ids),
        "time_range": {
            "start": actual_start.isoformat(),
            "end": actual_end.isoformat(),
        },
        "roads": road_summaries,
        "limitations": SIMULATION_LIMITATIONS,
    }
    run = SimulationRun(
        id=uuid4(),
        name=payload.name,
        scenario_type=payload.scenario_type,
        parameters=parameters,
        road_ids_affected=road_ids,
        baseline_snapshot=None,
        scenario_snapshot=scenario_snapshot,
        comparison=None,
        duration_minutes=payload.duration_minutes,
        interval_minutes=payload.interval_minutes,
        notes="Synthetic baseline simulation; not live traffic or a validated prediction.",
        created_by=current_user.id,
    )

    try:
        db.add_all([*records, run])
        db.flush()
        db.commit()
        db.refresh(run)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The simulation could not be saved because its observations "
                "conflict with existing data. No partial records were retained."
            ),
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The simulation could not be saved. No partial records were retained.",
        ) from exc

    return SimulationRunCreated(**_run_metadata(run))


@router.get("", response_model=list[SimulationRunSummary])
def list_simulations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SimulationRunSummary]:
    del current_user
    runs = (
        db.query(SimulationRun)
        .order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [SimulationRunSummary(**_run_metadata(run)) for run in runs]


@router.get("/{run_id}", response_model=SimulationRunDetail)
def get_simulation(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SimulationRunDetail:
    del current_user
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation run not found.",
        )
    return SimulationRunDetail(
        **_run_metadata(run),
        parameters=run.parameters or {},
        road_ids_affected=run.road_ids_affected or [],
        scenario_snapshot=run.scenario_snapshot or {},
        notes=run.notes or "",
    )
