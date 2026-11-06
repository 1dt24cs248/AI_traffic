"""
Application entrypoint.
Run with: uvicorn app.main:app --reload   (from inside backend/)
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.database import Base, engine
from app.core.cors import configure_cors
from app.core.validation import request_validation_error_handler
from app.core.config import settings
from app.traffic.collector import (
    collector_loop,
    release_collector_lock,
    try_acquire_collector_lock,
)
from app.api import (
    auth_routes,
    traffic_routes,
    analytics_routes,
    prediction_routes,
    routing_routes,
    incident_routes,
    simulation_routes,
    alert_routes,
    report_routes,
)
from app.api.geocoding_routes import router as geocoding_router
# Import all models here so Base.metadata knows about them before create_all
from app.models import user, traffic_record, incident, simulation_run, journey  # noqa: F401
@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    collector_task = None
    collector_connection = None

    if settings.TOMTOM_COLLECTOR_ENABLED and settings.TOMTOM_API_KEY:
        collector_connection = try_acquire_collector_lock()
        if collector_connection is not None:
            collector_task = asyncio.create_task(collector_loop(stop_event))

    try:
        yield
    finally:
        try:
            if collector_task is not None:
                stop_event.set()
                await collector_task
        finally:
            if collector_connection is not None:
                release_collector_lock(collector_connection)
app = FastAPI(
    title="AI Traffic Flow Predictor API",
    description="Spatio-temporal traffic congestion prediction and route recommendation system",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_exception_handler(
    RequestValidationError,
    request_validation_error_handler,
)

configure_cors(app)

# Dev convenience: create any missing tables on startup.
# For production schema changes, use Alembic migrations (database/migrations/).
Base.metadata.create_all(bind=engine)

app.include_router(auth_routes.router)
app.include_router(traffic_routes.router)
app.include_router(geocoding_router)
app.include_router(analytics_routes.router)
app.include_router(prediction_routes.router)
app.include_router(routing_routes.router)
app.include_router(incident_routes.router)
app.include_router(simulation_routes.router)
app.include_router(alert_routes.router)
app.include_router(report_routes.router)


@app.get("/api/health", tags=["system"])
def health_check():
    return {"status": "ok", "service": "ai-traffic-flow-predictor"}
