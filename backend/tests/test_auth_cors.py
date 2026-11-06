from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth_routes
from app.core.cors import configure_cors
from app.core.database import get_db
from app.models.user import UserRole


@pytest.fixture
def auth_client():
    app = FastAPI()
    configure_cors(app)
    app.include_router(auth_routes.router)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=uuid4(),
        role=UserRole.USER,
        is_active=True,
        hashed_password="stored-hash",
    )
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
def test_auth_token_preflight_allows_frontend_origins(auth_client, origin):
    client, _ = auth_client
    response = client.options(
        "/api/auth/token",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert response.headers["access-control-allow-credentials"] == "true"


def test_auth_token_preflight_rejects_unconfigured_origin(auth_client):
    client, _ = auth_client
    response = client.options(
        "/api/auth/token",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400


def test_auth_token_accepts_oauth2_form_encoded_login(
    auth_client, monkeypatch
):
    client, db = auth_client
    verify_password = MagicMock(return_value=True)
    create_access_token = MagicMock(return_value="test-access-token")
    monkeypatch.setattr(auth_routes, "verify_password", verify_password)
    monkeypatch.setattr(auth_routes, "create_access_token", create_access_token)

    response = client.post(
        "/api/auth/token",
        data={"username": "commuter@example.test", "password": "test-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "test-access-token",
        "token_type": "bearer",
    }
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    verify_password.assert_called_once_with("test-password", "stored-hash")
    create_access_token.assert_called_once()
    assert db.query.called
