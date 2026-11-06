from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import simulation_routes
from app.auth.dependencies import get_current_user
from app.core.database import Base, get_db
from app.models.simulation_run import SimulationRun
from app.models.traffic_record import TrafficRecord
from app.models.user import User, UserRole


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def simulation_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, TrafficRecord.__table__, SimulationRun.__table__],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    acting = {
        "user": User(
            id=uuid4(),
            email="simulator@example.test",
            full_name="Simulation User",
            hashed_password="not-used",
            role=UserRole.USER,
            is_active=True,
        ),
        "fail_flush": False,
    }
    app = FastAPI()
    app.include_router(simulation_routes.router)

    def db_session():
        session = session_factory()
        if acting["fail_flush"]:
            def fail_before_flush(_session, _flush_context, _instances):
                raise SQLAlchemyError("Injected persistence failure")

            event.listen(session, "before_flush", fail_before_flush, once=True)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[get_current_user] = lambda: acting["user"]
    with TestClient(app) as client:
        yield client, acting, session_factory, engine
    app.dependency_overrides.clear()
    engine.dispose()


def _payload(**overrides):
    payload = {
        "name": "Reproducible demo",
        "duration_minutes": 10,
        "interval_minutes": 5,
        "seed": 42,
        "start_time": "2026-01-05T09:00:00",
    }
    payload.update(overrides)
    return payload


def test_authenticated_fuel_impact_endpoint_returns_typed_estimate_without_persistence(simulation_api):
    client, acting, session_factory, _engine = simulation_api
    payload = {
        "vehicle": "petrol-car",
        "distance_km": 10,
        "efficiency": 10,
        "price_per_unit": 100,
        "max_extra_consumption_percent": 15,
        "traffic": {
            "status": "available",
            "sampled_point_count": 1,
            "checked_point_count": 1,
            "points": [{
                "status": "available",
                "flow": {
                    "latitude": 12.9,
                    "longitude": 77.6,
                    "current_speed": 25,
                    "free_flow_speed": 50,
                    "retrieved_at": "2026-10-20T10:00:00Z",
                },
            }],
        },
    }
    response = client.post("/api/simulations/fuel-impact", json=payload)
    assert response.status_code == 200
    assert response.json()["baseline"] == 1
    assert response.json()["additional"] == pytest.approx(0.075)
    assert response.json()["additional_cost"] == pytest.approx(7.5)
    with session_factory() as db:
        assert db.query(TrafficRecord).count() == 0
        assert db.query(SimulationRun).count() == 0

    client.app.dependency_overrides.pop(get_current_user)
    assert client.post("/api/simulations/fuel-impact", json=payload).status_code == 401


def test_simulation_rejects_invalid_duration_and_interval(simulation_api):
    client, _acting, _session_factory, _engine = simulation_api

    assert client.post("/api/simulations", json=_payload(duration_minutes=0)).status_code == 422
    assert client.post(
        "/api/simulations",
        json=_payload(duration_minutes=10, interval_minutes=3),
    ).status_code == 422
    assert client.post(
        "/api/simulations",
        json=_payload(duration_minutes=1445),
    ).status_code == 422


def test_create_persists_synthetic_records_and_run_metadata(simulation_api):
    client, acting, session_factory, _engine = simulation_api

    response = client.post("/api/simulations", json=_payload())

    assert response.status_code == 201
    result = response.json()
    assert result["record_count"] == 6
    assert result["road_count"] == 3
    assert result["source"] == "simulation"
    assert result["status"] == "completed"
    assert result["seed"] == 42
    assert result["start_time"].startswith("2026-01-05T09:00:00")
    assert result["end_time"].startswith("2026-01-05T09:05:00")

    with session_factory() as db:
        records = db.query(TrafficRecord).order_by(
            TrafficRecord.road_id,
            TrafficRecord.timestamp,
        ).all()
        run = db.query(SimulationRun).one()
        assert len(records) == 6
        assert {record.source for record in records} == {"simulation"}
        assert all(record.created_at is not None for record in records)
        assert all(record.hour == record.timestamp.hour for record in records)
        assert all(record.day_of_week == record.timestamp.weekday() for record in records)
        assert run is not None
        assert run.created_by == acting["user"].id
        assert run.parameters["seed"] == 42
        assert run.road_ids_affected == ["SIM-NH48-01", "SIM-NH48-02", "SIM-NH48-03"]
        assert run.scenario_snapshot["record_count"] == len(records)
        assert run.scenario_snapshot["source"] == "simulation"
        assert run.baseline_snapshot is None
        assert run.comparison is None
        assert any("synthetic" in item.lower() for item in run.scenario_snapshot["limitations"])


def test_list_and_get_simulation_run_metadata(simulation_api):
    client, _acting, _session_factory, _engine = simulation_api
    created = client.post("/api/simulations", json=_payload()).json()

    listed = client.get("/api/simulations")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == created["id"]

    detail = client.get(f"/api/simulations/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["parameters"]["seed"] == 42
    assert detail.json()["scenario_snapshot"]["record_count"] == 6
    assert len(detail.json()["road_ids_affected"]) == 3


def test_simulation_list_is_empty_when_no_runs_exist(simulation_api):
    client, _acting, _session_factory, _engine = simulation_api

    response = client.get("/api/simulations")

    assert response.status_code == 200
    assert response.json() == []


def test_missing_simulation_run_returns_404(simulation_api):
    client, _acting, _session_factory, _engine = simulation_api

    response = client.get(f"/api/simulations/{uuid4()}")

    assert response.status_code == 404


def test_simulation_endpoints_require_authentication(simulation_api):
    client, _acting, _session_factory, _engine = simulation_api
    client.app.dependency_overrides.pop(get_current_user)

    response = client.get("/api/simulations")

    assert response.status_code == 401


def test_duplicate_road_timestamp_is_rejected_without_overwriting_data(simulation_api):
    client, _acting, session_factory, _engine = simulation_api
    first = client.post("/api/simulations", json=_payload())
    assert first.status_code == 201

    duplicate = client.post("/api/simulations", json=_payload(name="Collision"))

    assert duplicate.status_code == 409
    with session_factory() as db:
        assert db.query(TrafficRecord).count() == 6
        assert db.query(SimulationRun).count() == 1


def test_duplicate_rows_from_generator_are_rejected(simulation_api, monkeypatch):
    client, _acting, session_factory, _engine = simulation_api
    one_record = {
        "road_id": "SIM-DUPLICATE",
        "road_name": "Duplicate",
        "latitude": 13.0,
        "longitude": 77.0,
        "timestamp": datetime(2026, 1, 5, 9, 0),
        "vehicle_count": 10,
        "average_speed": 30.0,
        "road_capacity": 50,
        "occupancy": 20.0,
        "weather_condition": "CLEAR",
        "temperature": 25.0,
        "rainfall": 0.0,
        "event_indicator": None,
    }
    monkeypatch.setattr(
        simulation_routes,
        "generate_simulation_rows",
        lambda **_kwargs: [one_record, one_record.copy()],
    )

    response = client.post("/api/simulations", json=_payload())

    assert response.status_code == 409
    with session_factory() as db:
        assert db.query(TrafficRecord).count() == 0
        assert db.query(SimulationRun).count() == 0


def test_persistence_failure_rolls_back_records_and_run(simulation_api):
    client, acting, session_factory, _engine = simulation_api
    acting["fail_flush"] = True

    response = client.post("/api/simulations", json=_payload())

    assert response.status_code == 500
    assert "No partial records" in response.json()["detail"]
    acting["fail_flush"] = False
    with session_factory() as db:
        assert db.query(TrafficRecord).count() == 0
        assert db.query(SimulationRun).count() == 0
