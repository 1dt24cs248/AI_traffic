from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import alert_routes, incident_routes, report_routes
from app.auth.dependencies import get_current_user
from app.core.database import Base, get_db
from app.models.incident import (
    Incident,
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
    IncidentType,
)
from app.models.simulation_run import SimulationRun
from app.models.traffic_record import TrafficRecord
from app.models.user import User, UserRole


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def reports_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            TrafficRecord.__table__,
            Incident.__table__,
            SimulationRun.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    acting_user = User(
        id=uuid4(),
        email="reader@example.test",
        full_name="Reader",
        hashed_password="not-used",
        role=UserRole.USER,
        is_active=True,
    )
    app = FastAPI()
    app.include_router(alert_routes.router)
    app.include_router(incident_routes.router)
    app.include_router(report_routes.router)

    def db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[get_current_user] = lambda: acting_user
    with TestClient(app) as client:
        with session_factory() as db:
            db.add_all(
                [
                    TrafficRecord(
                        road_id="SIM-1",
                        road_name="Simulation road",
                        latitude=13,
                        longitude=77,
                        timestamp=datetime(2026, 1, 5, 8),
                        vehicle_count=12,
                        average_speed=24.0,
                        hour=8,
                        day_of_week=0,
                        source="simulation",
                    ),
                    TrafficRecord(
                        road_id="CSV-1",
                        road_name="Uploaded road",
                        latitude=13.1,
                        longitude=77.1,
                        timestamp=datetime(2026, 1, 6, 9),
                        vehicle_count=40,
                        average_speed=30.0,
                        hour=9,
                        day_of_week=1,
                        source="csv_upload",
                    ),
                    Incident(
                        id=uuid4(),
                        type=IncidentType.ROAD_CLOSURE,
                        latitude=13,
                        longitude=77,
                        severity=IncidentSeverity.HIGH,
                        status=IncidentStatus.VERIFIED,
                        source=IncidentSource.USER_REPORT,
                        verified=True,
                        started_at=datetime(2026, 1, 5, 8),
                        created_at=datetime(2026, 1, 5, 8),
                        updated_at=datetime(2026, 1, 5, 8),
                    ),
                    Incident(
                        id=uuid4(),
                        type=IncidentType.ACCIDENT,
                        latitude=13,
                        longitude=77,
                        severity=IncidentSeverity.MEDIUM,
                        status=IncidentStatus.REPORTED,
                        source=IncidentSource.USER_REPORT,
                        verified=False,
                        started_at=datetime(2026, 1, 5, 9),
                        created_at=datetime(2026, 1, 5, 9),
                        updated_at=datetime(2026, 1, 5, 9),
                    ),
                    Incident(
                        id=uuid4(),
                        type=IncidentType.ACCIDENT,
                        latitude=13,
                        longitude=77,
                        severity=IncidentSeverity.MEDIUM,
                        status=IncidentStatus.RESOLVED,
                        source=IncidentSource.USER_REPORT,
                        verified=True,
                        started_at=datetime(2026, 1, 4, 8),
                        ended_at=datetime(2026, 1, 5, 10),
                        created_at=datetime(2026, 1, 4, 8),
                        updated_at=datetime(2026, 1, 5, 10),
                    ),
                    SimulationRun(
                        id=uuid4(),
                        name="Recorded run",
                        scenario_type="baseline",
                        parameters={"seed": 7},
                        road_ids_affected=["SIM-1"],
                        scenario_snapshot={"record_count": 6},
                        duration_minutes=10,
                        interval_minutes=5,
                        created_at=datetime(2026, 1, 5, 7),
                    ),
                ]
            )
            db.commit()
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_alerts_only_include_verified_incidents_and_filter_status(reports_api):
    active = reports_api.get("/api/alerts")
    all_alerts = reports_api.get("/api/alerts?status_filter=all")

    assert active.status_code == 200
    assert len(active.json()) == 1
    assert active.json()[0]["status"] == "active"
    assert len(all_alerts.json()) == 2
    assert {alert["status"] for alert in all_alerts.json()} == {"active", "resolved"}


def test_alert_and_report_endpoints_require_authentication(reports_api):
    reports_api.app.dependency_overrides.pop(get_current_user)

    assert reports_api.get("/api/alerts").status_code == 401
    assert reports_api.get("/api/reports").status_code == 401


def test_reports_use_actual_source_and_date_filters(reports_api):
    response = reports_api.get(
        "/api/reports",
        params={
            "source": "simulation",
            "start_date": "2026-01-05",
            "end_date": "2026-01-05",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["traffic"]["summary"]["sample_count"] == 1
    assert result["traffic"]["summary"]["avg_speed"] == 24.0
    assert result["traffic"]["daily_trend"] == [
        {
            "date": "2026-01-05",
            "avg_speed": 24.0,
            "avg_vehicle_count": 12.0,
            "sample_count": 1,
        }
    ]
    assert result["traffic"]["speed_by_hour"] == [
        {"hour": 8, "avg_speed": 24.0, "sample_count": 1}
    ]
    assert result["incidents"]["total"] == 2
    assert result["incidents"]["active_verified_alert_count"] == 1
    assert {item["status"] for item in result["incidents"]["reports"]} == {"verified"}
    assert result["incidents"]["displayed_reports"] == 1
    assert result["simulation_runs"]["total"] == 1
    assert result["simulation_runs"]["runs"][0]["record_count"] == 6
    assert result["prediction_history"]["available"] is False


def test_new_report_is_persisted_and_private_to_its_reporter_until_verified(
    reports_api,
):
    created = reports_api.post(
        "/api/incidents",
        json={
            "type": "waterlogging",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "severity": "medium",
            "road_reference": "Test junction",
            "description": "Isolated test report",
        },
    )

    assert created.status_code == 201
    incident_id = created.json()["id"]
    assert created.json()["status"] == "reported"
    assert created.json()["verified"] is False

    persisted = reports_api.get(f"/api/incidents/{incident_id}")
    assert persisted.status_code == 200
    assert persisted.json()["description"] == "Isolated test report"

    report = reports_api.get("/api/reports")
    assert report.status_code == 200
    assert all(item["id"] != incident_id for item in report.json()["incidents"]["reports"])
    mine = reports_api.get("/api/incidents/mine")
    assert mine.status_code == 200
    assert any(item["id"] == incident_id and item["status"] == "reported" for item in mine.json())
    assert report.json()["incidents"]["by_status"]["reported"] == 2

    alerts = reports_api.get("/api/alerts?status_filter=all")
    assert alerts.status_code == 200
    assert incident_id not in {item["id"] for item in alerts.json()}


@pytest.mark.parametrize(
    "endpoint",
    ["/api/alerts?start_date=2026-01-02&end_date=2026-01-01",
     "/api/reports?start_date=2026-01-02&end_date=2026-01-01"],
)
def test_alerts_and_reports_reject_inverted_date_ranges(reports_api, endpoint):
    assert reports_api.get(endpoint).status_code == 422
