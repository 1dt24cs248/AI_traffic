from datetime import datetime
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import alert_routes, incident_routes, routing_routes
from app.auth.dependencies import get_current_user
from app.core.database import Base, get_db
from app.models.incident import (
    Incident,
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
    IncidentType,
)
from app.models.traffic_record import TrafficRecord
from app.models.user import User, UserRole
from app.routing.incident_matching import (
    GEOMETRY_MATCH_METERS,
    assess_incidents_for_route,
    nearest_route_distance_meters,
)
from app.routing.schemas import IncidentWarning
from app.schemas.incidents import IncidentCreate


@pytest.fixture
def incident_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, Incident.__table__, TrafficRecord.__table__],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    acting = {
        "user": User(
            id=uuid4(),
            email="reporter@example.test",
            full_name="Reporter",
            hashed_password="not-used",
            role=UserRole.USER,
            is_active=True,
        )
    }
    app = FastAPI()
    app.include_router(incident_routes.router)
    app.include_router(alert_routes.router)
    app.include_router(routing_routes.router)

    def db_session():
        session = session_factory()
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


def _incident(
    *,
    incident_type=IncidentType.ACCIDENT,
    latitude=13.0,
    longitude=77.0,
    status=IncidentStatus.REPORTED,
    verified=False,
    source=IncidentSource.USER_REPORT,
    road_reference=None,
    description="Hazard",
    ended_at=None,
):
    now = datetime.utcnow()
    return Incident(
        id=uuid4(),
        type=incident_type,
        latitude=latitude,
        longitude=longitude,
        severity=IncidentSeverity.HIGH,
        status=status,
        source=source,
        verified=verified,
        confidence=None,
        started_at=now,
        ended_at=ended_at,
        description=description,
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        road_reference=road_reference,
    )


def _route(coordinates, names=None):
    steps = [{"name": name, "ref": ""} for name in (names or [])]
    return {
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "legs": [{"steps": steps}],
    }


def _report_payload(**overrides):
    payload = {
        "type": "accident",
        "latitude": 13.0,
        "longitude": 77.0,
        "severity": "high",
        "description": "Vehicle blocking a lane",
    }
    payload.update(overrides)
    return payload


def test_incident_schema_validates_coordinates_and_supported_types():
    report = IncidentCreate(**_report_payload(type="partial_obstruction"))
    assert report.type == IncidentType.PARTIAL_OBSTRUCTION

    with pytest.raises(ValueError):
        IncidentCreate(**_report_payload(latitude=91))
    with pytest.raises(ValueError):
        IncidentCreate(**_report_payload(longitude=181))


def test_incident_api_requires_auth_and_keeps_user_reports_unverified(incident_api):
    client, acting, _, _ = incident_api
    app = client.app
    app.dependency_overrides.pop(get_current_user)

    response = client.post("/api/incidents", json=_report_payload())
    assert response.status_code == 401

    app.dependency_overrides[get_current_user] = lambda: acting["user"]
    response = client.post("/api/incidents", json=_report_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "user_report"
    assert body["status"] == "reported"
    assert body["verified"] is False
    assert body["verified_at"] is None


def test_incident_api_lists_retrieves_updates_and_resolves_owned_reports(incident_api):
    client, _, _, _ = incident_api
    created = client.post("/api/incidents", json=_report_payload()).json()
    incident_id = created["id"]

    assert client.get("/api/incidents").json()[0]["id"] == incident_id
    assert client.get(f"/api/incidents/{incident_id}").status_code == 200
    assert client.patch(
        f"/api/incidents/{incident_id}",
        json={"description": "Updated description"},
    ).json()["description"] == "Updated description"

    resolved = client.post(f"/api/incidents/{incident_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert client.get("/api/incidents").json() == []
    assert client.get("/api/incidents?include_resolved=true").json()[0]["id"] == incident_id
    assert client.post(f"/api/incidents/{incident_id}/resolve").status_code == 200


def test_incident_api_enforces_owner_admin_and_verification_rules(incident_api):
    client, acting, _, _ = incident_api
    reporter = acting["user"]
    reporter = acting["user"]
    incident_id = client.post("/api/incidents", json=_report_payload()).json()["id"]

    other_user = User(
        id=uuid4(),
        email="other@example.test",
        full_name="Other",
        hashed_password="not-used",
        role=UserRole.USER,
        is_active=True,
    )
    acting["user"] = other_user
    assert client.patch(
        f"/api/incidents/{incident_id}",
        json={"description": "unauthorized"},
    ).status_code == 403
    assert client.post(f"/api/incidents/{incident_id}/resolve").status_code == 403
    assert client.post(f"/api/incidents/{incident_id}/verify").status_code == 403

    acting["user"] = User(
        id=uuid4(),
        email="admin@example.test",
        full_name="Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
        is_active=True,
    )
    verified = client.post(f"/api/incidents/{incident_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["status"] == "verified"
    assert verified.json()["verified_by"] == str(acting["user"].id)
    acting["user"] = reporter
    assert client.post(f"/api/incidents/{incident_id}/resolve").status_code == 403
    acting["user"] = User(
        id=uuid4(),
        email="admin@example.test",
        full_name="Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
        is_active=True,
    )
    assert client.patch(
        f"/api/incidents/{incident_id}",
        json={"description": "Administrator update"},
    ).json()["description"] == "Administrator update"
    acting["user"] = reporter
    assert client.post(f"/api/incidents/{incident_id}/resolve").status_code == 403
    acting["user"] = User(
        id=uuid4(),
        email="admin@example.test",
        full_name="Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
        is_active=True,
    )
    assert client.post(f"/api/incidents/{incident_id}/resolve").json()["status"] == "resolved"
    assert client.post(f"/api/incidents/{incident_id}/verify").status_code == 409


def test_own_report_tracking_is_private_and_rejection_never_creates_an_alert(incident_api):
    client, acting, _, _ = incident_api
    reporter = acting["user"]
    own = client.post("/api/incidents", json=_report_payload()).json()
    other_user = User(
        id=uuid4(), email="another@example.test", full_name="Another",
        hashed_password="not-used", role=UserRole.USER, is_active=True,
    )
    acting["user"] = other_user
    other = client.post("/api/incidents", json=_report_payload(description="Private report")).json()
    assert [item["id"] for item in client.get("/api/incidents/mine").json()] == [other["id"]]
    assert client.get(f"/api/incidents/{own['id']}").status_code == 404
    assert own["id"] not in {item["id"] for item in client.get("/api/incidents").json()}
    assert client.post(f"/api/incidents/{own['id']}/reject").status_code == 403

    acting["user"] = User(
        id=uuid4(), email="admin@example.test", full_name="Admin",
        hashed_password="not-used", role=UserRole.ADMIN, is_active=True,
    )
    rejected = client.post(f"/api/incidents/{own['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["verified"] is False
    assert own["id"] not in {item["id"] for item in client.get("/api/alerts?status_filter=all").json()}
    assert own["id"] not in {item["id"] for item in client.get("/api/incidents").json()}

    acting["user"] = reporter
    assert client.get("/api/incidents/mine").json()[0]["status"] == "rejected"


def test_regular_user_cannot_create_simulated_incident(incident_api):
    client, _, _, _ = incident_api
    response = client.post(
        "/api/incidents",
        json=_report_payload(source="simulation"),
    )
    assert response.status_code == 403


def test_incident_api_rejects_invalid_and_empty_updates(incident_api):
    client, _, _, _ = incident_api
    response = client.post("/api/incidents", json=_report_payload(latitude=91))
    assert response.status_code == 422
    incident_id = client.post("/api/incidents", json=_report_payload()).json()["id"]
    assert client.patch(f"/api/incidents/{incident_id}", json={}).status_code == 422
    assert (
        client.patch(
            f"/api/incidents/{incident_id}",
            json={"description": "text", "status": "verified"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/incidents/{incident_id}",
            json={"latitude": None},
        ).status_code
        == 422
    )
    assert client.get(f"/api/incidents/{uuid4()}").status_code == 404
    assert client.get("/api/incidents?limit=0").status_code == 422


def test_incident_api_returns_explicit_database_failure_and_rolls_back(incident_api):
    class FailingSession:
        rolled_back = False

        def add(self, _instance):
            pass

        def commit(self):
            raise OperationalError("INSERT", {}, RuntimeError("database unavailable"))

        def rollback(self):
            self.rolled_back = True

    db = FailingSession()
    client, _, _, _ = incident_api

    def failing_db():
        yield db

    client.app.dependency_overrides[get_db] = failing_db
    response = client.post("/api/incidents", json=_report_payload())
    assert response.status_code == 500
    assert response.json()["detail"] == "Incident changes could not be saved."
    assert db.rolled_back is True


def test_route_distance_uses_segment_projection_and_handles_missing_geometry():
    route = _route([[77.0, 13.0], [77.01, 13.0]])
    midpoint_distance = nearest_route_distance_meters(
        route["geometry"]["coordinates"],
        13.0,
        77.005,
    )
    offset_distance = nearest_route_distance_meters(
        route["geometry"]["coordinates"],
        13.001,
        77.005,
    )
    assert midpoint_distance < 0.1
    assert offset_distance == pytest.approx(110.54, rel=0.02)
    assert nearest_route_distance_meters([], 13.0, 77.0) == float("inf")


def test_incident_match_requires_route_proximity_or_matching_road_reference():
    route = _route([[77.0, 13.0], [77.01, 13.0]], ["Main Street"])
    nearby_other_road = _incident(latitude=13.001, longitude=77.005)
    unreferenced_on_route = _incident(latitude=13.0, longitude=77.005)
    mismatched_reference = _incident(
        latitude=13.001,
        longitude=77.005,
        road_reference="Other Street",
    )
    warnings, closures = assess_incidents_for_route(
        route,
        [nearby_other_road, unreferenced_on_route, mismatched_reference],
        200,
    )
    assert [warning["incident_id"] for warning in warnings] == [
        str(unreferenced_on_route.id)
    ]
    assert warnings[0]["match_basis"] == "incident point lies on the route geometry"
    assert closures == []
    assert GEOMETRY_MATCH_METERS < 200


def test_only_verified_real_full_closure_blocks_and_partial_obstruction_does_not():
    route = _route([[77.0, 13.0], [77.01, 13.0]])
    unverified_closure = _incident(
        incident_type=IncidentType.ROAD_CLOSURE,
        latitude=13.0,
        longitude=77.005,
    )
    partial = _incident(
        incident_type=IncidentType.PARTIAL_OBSTRUCTION,
        latitude=13.0,
        longitude=77.005,
        status=IncidentStatus.VERIFIED,
        verified=True,
    )
    simulated_closure = _incident(
        incident_type=IncidentType.ROAD_CLOSURE,
        latitude=13.0,
        longitude=77.005,
        status=IncidentStatus.VERIFIED,
        verified=True,
        source=IncidentSource.SIMULATION,
    )
    warnings, closures = assess_incidents_for_route(
        route,
        [unverified_closure, partial, simulated_closure],
        200,
    )
    assert len(warnings) == 3
    assert closures == []

    verified_closure = _incident(
        incident_type=IncidentType.ROAD_CLOSURE,
        latitude=13.0,
        longitude=77.005,
        status=IncidentStatus.VERIFIED,
        verified=True,
    )
    warnings, closures = assess_incidents_for_route(
        route,
        [verified_closure],
        200,
    )
    assert warnings[0]["verified"] is True
    assert closures == ["Verified road closure: Hazard"]


def test_resolved_and_ended_incidents_are_ignored():
    route = _route([[77.0, 13.0], [77.01, 13.0]])
    ended = _incident(
        latitude=13.0,
        longitude=77.005,
        ended_at=datetime.utcnow(),
    )
    resolved = _incident(
        latitude=13.0,
        longitude=77.005,
        status=IncidentStatus.RESOLVED,
    )
    warnings, closures = assess_incidents_for_route(route, [ended, resolved], 200)
    assert warnings == []
    assert closures == []


def test_incident_warning_contract_includes_provenance_and_match_basis():
    incident = _incident(latitude=13.0, longitude=77.005)
    warnings, _ = assess_incidents_for_route(
        _route([[77.0, 13.0], [77.01, 13.0]]),
        [incident],
        200,
    )
    warning = IncidentWarning(**warnings[0])
    assert warning.status == "reported"
    assert warning.source == "user_report"
    assert warning.verified is False


def test_route_refresh_excludes_confirmed_closure_and_reports_change(
    incident_api,
    monkeypatch,
):
    client, _, session_factory, _ = incident_api
    db = session_factory()
    closure = _incident(
        incident_type=IncidentType.ROAD_CLOSURE,
        latitude=13.0,
        longitude=77.005,
        status=IncidentStatus.VERIFIED,
        verified=True,
    )
    db.add(closure)
    db.commit()
    db.close()

    routes = [
        {
            "distance": 1000,
            "duration": 100,
            "geometry": {"type": "LineString", "coordinates": [[77.0, 13.0], [77.01, 13.0]]},
            "legs": [{"steps": [{"name": "Main Street", "ref": ""}]}],
        },
        {
            "distance": 1500,
            "duration": 200,
            "geometry": {"type": "LineString", "coordinates": [[77.0, 13.01], [77.01, 13.01]]},
            "legs": [{"steps": [{"name": "Second Street", "ref": ""}]}],
        },
    ]
    monkeypatch.setattr(
        routing_routes,
        "get_route",
        lambda **_kwargs: {"provider": "OSRM", "routes": routes},
    )
    monkeypatch.setattr(routing_routes, "SessionLocal", session_factory)

    request = {
        "origin_lat": 13.0,
        "origin_lon": 77.0,
        "destination_lat": 13.02,
        "destination_lon": 77.01,
        "previous_recommended_index": 0,
    }
    response = client.post("/api/routing/routes/refresh", json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["routes"][0]["feasible"] is False
    assert body["routes"][0]["incident_warnings"][0]["verified"] is True
    assert body["routes"][1]["feasible"] is True
    assert body["recommended_index"] == 1
    assert "changed from Route 1 to Route 2" in body["recommendation_change_reason"]


def test_end_to_end_report_admin_verification_and_explicit_route_refresh(
    incident_api,
    monkeypatch,
):
    client, acting, session_factory, _ = incident_api
    routes = [
        {
            "distance": 1000,
            "duration": 100,
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.0, 13.0], [77.01, 13.0]],
            },
            "legs": [],
        },
        {
            "distance": 1500,
            "duration": 200,
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.0, 13.01], [77.01, 13.01]],
            },
            "legs": [],
        },
    ]
    monkeypatch.setattr(
        routing_routes,
        "get_route",
        lambda **_kwargs: {"provider": "OSRM", "routes": routes},
    )
    monkeypatch.setattr(routing_routes, "SessionLocal", session_factory)

    report_response = client.post(
        "/api/incidents",
        json=_report_payload(
            type="road_closure",
            latitude=13.0,
            longitude=77.005,
            description="Closure reported on route",
        ),
    )
    assert report_response.status_code == 201
    report_id = report_response.json()["id"]
    assert report_response.json()["status"] == "reported"
    assert report_response.json()["verified"] is False

    displayed = client.get("/api/incidents")
    assert displayed.status_code == 200
    assert any(incident["id"] == report_id for incident in displayed.json())

    request = {
        "origin_lat": 13.0,
        "origin_lon": 77.0,
        "destination_lat": 13.02,
        "destination_lon": 77.01,
    }
    before_verification = client.post("/api/routing/routes", json=request)
    assert before_verification.status_code == 200
    unverified_route = before_verification.json()["routes"][0]
    assert unverified_route["feasible"] is True
    assert unverified_route["incident_warnings"][0]["status"] == "reported"
    assert before_verification.json()["recommended_index"] == 0

    acting["user"] = User(
        id=uuid4(),
        email="admin@example.test",
        full_name="Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
        is_active=True,
    )
    verification = client.post(f"/api/incidents/{report_id}/verify")
    assert verification.status_code == 200
    assert verification.json()["status"] == "verified"
    assert verification.json()["verified"] is True

    refreshed = client.post(
        "/api/routing/routes/refresh",
        json={**request, "previous_recommended_index": 0},
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["routes"][0]["feasible"] is False
    assert body["routes"][0]["incident_warnings"][0]["status"] == "verified"
    assert body["recommended_index"] == 1
    assert body["routes"][1]["feasible"] is True
    assert "Recommendation changed from Route 1 to Route 2" in body[
        "recommendation_change_reason"
    ]


def test_route_without_incident_data_remains_feasible_and_osrm_failure_is_reported(
    incident_api,
    monkeypatch,
):
    client, _, session_factory, _ = incident_api
    monkeypatch.setattr(
        routing_routes,
        "get_route",
        lambda **_kwargs: {
            "provider": "OSRM",
            "routes": [
                {
                    "distance": 1000,
                    "duration": 100,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[77.0, 13.0], [77.01, 13.0]],
                    },
                    "legs": [],
                }
            ],
        },
    )
    monkeypatch.setattr(routing_routes, "SessionLocal", session_factory)
    request = {
        "origin_lat": 13.0,
        "origin_lon": 77.0,
        "destination_lat": 13.0,
        "destination_lon": 77.01,
    }
    response = client.post("/api/routing/routes", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["routes"][0]["feasible"] is True
    assert response.json()["routes"][0]["incident_warnings"] == []
    assert response.json()["recommended_index"] == 0

    from app.routing.osrm_client import OSRMError

    def unavailable_osrm(**_kwargs):
        raise OSRMError("OSRM unavailable")

    monkeypatch.setattr(routing_routes, "get_route", unavailable_osrm)
    failure = client.post("/api/routing/routes", json=request)
    assert failure.status_code == 502
    assert failure.json()["detail"] == "OSRM unavailable"


def test_all_route_alternatives_can_be_infeasible(incident_api, monkeypatch):
    client, _, session_factory, _ = incident_api
    db = session_factory()
    db.add(
        _incident(
            incident_type=IncidentType.ROAD_CLOSURE,
            latitude=13.0,
            longitude=77.005,
            status=IncidentStatus.VERIFIED,
            verified=True,
        )
    )
    db.commit()
    db.close()
    monkeypatch.setattr(
        routing_routes,
        "get_route",
        lambda **_kwargs: {
            "provider": "OSRM",
            "routes": [
                {
                    "distance": 1000,
                    "duration": 100,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[77.0, 13.0], [77.01, 13.0]],
                    },
                    "legs": [],
                }
            ],
        },
    )
    monkeypatch.setattr(routing_routes, "SessionLocal", session_factory)

    response = client.post(
        "/api/routing/routes",
        json={
            "origin_lat": 13.0,
            "origin_lon": 77.0,
            "destination_lat": 13.0,
            "destination_lon": 77.01,
            "previous_recommended_index": 0,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommended_index"] is None
    assert body["routes"][0]["feasible"] is False
    assert "No feasible route available" in body["ranking_basis"]
    assert "changed from Route 1 to no feasible route" in body["recommendation_change_reason"]


def test_incident_migration_creates_schema_additively_on_empty_database():
    migration_path = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "versions"
        / "20261019_01_incident_management.py"
    )
    spec = importlib.util.spec_from_file_location(
        "incident_management_migration",
        migration_path,
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        inspector = inspect(connection)
        assert inspector.has_table("incidents")
        assert {
            "road_reference",
            "verified_at",
            "verified_by",
            "updated_at",
        }.issubset(
            {column["name"] for column in inspector.get_columns("incidents")}
        )
        assert len(inspector.get_indexes("incidents")) >= 5
    engine.dispose()


def test_foundation_migration_creates_phase_one_tables_without_dropping_data():
    from sqlalchemy import inspect

    migration_path = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "versions"
        / "20261019_00_foundation_tables.py"
    )
    spec = importlib.util.spec_from_file_location(
        "foundation_tables_migration",
        migration_path,
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        inspector = inspect(connection)
        assert inspector.has_table("simulation_runs")
        assert inspector.has_table("journeys")
        assert "parameters" in {
            column["name"] for column in inspector.get_columns("simulation_runs")
        }
        assert "incidents_snapshot" in {
            column["name"] for column in inspector.get_columns("journeys")
        }
    engine.dispose()
