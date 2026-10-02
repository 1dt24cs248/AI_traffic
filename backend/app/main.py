"""
Application entrypoint.
Run with: uvicorn app.main:app --reload   (from inside backend/)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.api import auth_routes, traffic_routes, analytics_routes, prediction_routes, routing_routes
from app.api.geocoding_routes import router as geocoding_router
# Import all models here so Base.metadata knows about them before create_all
from app.models import user, traffic_record  # noqa: F401

app = FastAPI(
    title="AI Traffic Flow Predictor API",
    description="Spatio-temporal traffic congestion prediction and route recommendation system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 1: creates tables directly for dev convenience.
# From Phase 3 onward, switch to Alembic migrations (database/migrations/) instead.
Base.metadata.create_all(bind=engine)

app.include_router(auth_routes.router)
app.include_router(traffic_routes.router)
app.include_router(geocoding_router)
app.include_router(analytics_routes.router)
app.include_router(prediction_routes.router)
app.include_router(routing_routes.router)


@app.get("/api/health", tags=["system"])
def health_check():
    return {"status": "ok", "service": "ai-traffic-flow-predictor"}
