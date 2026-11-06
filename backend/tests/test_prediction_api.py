from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.api import prediction_routes
from app.auth.dependencies import get_current_user
from app.core.validation import request_validation_error_handler
from app.models.user import User, UserRole


@pytest.fixture
def prediction_client():
    user = User(
        id=uuid4(),
        email="predictor@example.test",
        full_name="Predictor",
        hashed_password="not-used",
        role=UserRole.USER,
        is_active=True,
    )
    app = FastAPI()
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )
    app.include_router(prediction_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _features():
    return {
        "flow": 1.0,
        "occupancy": 1.0,
        "speed": 1.0,
        "flow_lag_5m": 1.0,
        "flow_lag_15m": 1.0,
        "flow_lag_30m": 1.0,
        "flow_lag_1h": 1.0,
        "speed_lag_5m": 1.0,
        "speed_lag_15m": 1.0,
        "speed_lag_30m": 1.0,
        "speed_lag_1h": 1.0,
        "occupancy_lag_5m": 1.0,
        "occupancy_lag_15m": 1.0,
        "occupancy_lag_30m": 1.0,
        "occupancy_lag_1h": 1.0,
        "hour": 8,
        "day_of_week": 0,
        "month": 1,
        "is_weekend": 0,
        "is_rush_hour": 1,
    }


def test_prediction_status_exposes_artifact_availability_without_paths(
    prediction_client, monkeypatch
):
    monkeypatch.setattr(
        prediction_routes,
        "get_model_status",
        lambda: {
            "speed_model_exists": True,
            "congestion_model_exists": False,
            "speed_model_path": "private/path",
            "congestion_model_path": "private/path",
        },
    )

    response = prediction_client.get("/api/predictions/pems08/status")

    assert response.status_code == 200
    assert response.json()["speed_model_available"] is True
    assert response.json()["congestion_model_available"] is False
    assert response.json()["feature_count"] == 20
    assert "private/path" not in response.text


def test_speed_endpoint_reports_dataset_units_without_claiming_kmh(
    prediction_client, monkeypatch
):
    captured = {}

    def predict(features):
        captured.update(features)
        return 42.5

    monkeypatch.setattr(prediction_routes, "predict_speed", predict)
    response = prediction_client.post(
        "/api/predictions/pems08/speed",
        json=_features(),
    )

    assert response.status_code == 200
    assert response.json()["predicted_speed"] == 42.5
    assert "not independently verified" in response.json()["speed_unit_note"]
    assert "predicted_speed_kmh" not in response.json()
    assert captured["flow_lag_1h"] == 1.0


def test_congestion_probabilities_are_disclosed_as_uncalibrated(
    prediction_client, monkeypatch
):
    monkeypatch.setattr(
        prediction_routes,
        "predict_congestion",
        lambda _features: {
            "congestion_level": "LOW",
            "probabilities": {"LOW": 0.8, "MEDIUM": 0.1, "HIGH": 0.1},
        },
    )

    response = prediction_client.post(
        "/api/predictions/pems08/congestion",
        json=_features(),
    )

    assert response.status_code == 200
    assert response.json()["probability_note"] == (
        "Random-forest vote proportions; these are not calibrated confidence "
        "estimates and are not validated for Bengaluru roads."
    )


def test_missing_model_artifact_is_reported_as_unavailable(prediction_client, monkeypatch):
    def unavailable(_features):
        raise FileNotFoundError("internal model path")

    monkeypatch.setattr(prediction_routes, "predict_speed", unavailable)
    response = prediction_client.post(
        "/api/predictions/pems08/speed",
        json=_features(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "The PEMS08 speed model artifact is unavailable."


def test_prediction_endpoint_validates_required_model_features(prediction_client):
    response = prediction_client.post("/api/predictions/pems08/speed", json={"speed": 20})

    assert response.status_code == 422


@pytest.mark.parametrize("invalid_value", [-1, float("nan"), float("inf")])
def test_prediction_endpoint_rejects_invalid_measurements(
    prediction_client, invalid_value
):
    payload = _features()
    payload["flow"] = invalid_value

    response = prediction_client.post("/api/predictions/pems08/speed", json=payload)

    assert response.status_code == 422


def test_prediction_api_requires_authentication(prediction_client):
    prediction_client.app.dependency_overrides.pop(get_current_user)

    assert prediction_client.get("/api/predictions/pems08/status").status_code == 401
    assert prediction_client.post(
        "/api/predictions/pems08/speed",
        json=_features(),
    ).status_code == 401
