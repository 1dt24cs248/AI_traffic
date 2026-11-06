# AI Traffic Flow Predictor

Spatio-temporal traffic congestion prediction and dynamic route recommendation system — BCA final-year project.

## Current status

This repository already includes a React/TypeScript MapLibre frontend, FastAPI
backend, PostgreSQL models, OSRM routing, geocoding, traffic ingestion, analytics,
simulation, and separate Metro ML work. Route prediction integration is currently
disabled for simulated roads because the available PEMS08 model's sensor inputs
and units have not been demonstrated compatible with the application schema. The
route API returns an explicit unavailable reason instead of a synthetic-to-real
prediction claim.

See `docs/PROJECT_STATUS.md` for the inspected baseline, `docs/KNOWN_ISSUES.md`
for limitations, `docs/ARCHITECTURE.md` for system boundaries, and
`docs/IMPLEMENTATION_ROADMAP.md` for the remaining dependency order. The Metro
and PEMS08 datasets and models are distinct pipelines; do not combine their
features or metrics.

## Module 5 — Train the real model yourself

```bash
pip install -r ml/requirements.txt --break-system-packages
python -m ml.preprocessing.real_dataset_features   # inspect the cleaned/featured data
python -m ml.training.train_models                  # trains + evaluates, ~1-2 min
python -m ml.training.write_model_version            # writes ml/models/model_versions.json
```

Output: `ml/models/*.joblib` (trained models — not included in this zip, see below),
`reports/model_evaluation/model_comparison.json` + per-model classification reports.

Model binaries are not included in the zip (the Random Forest file alone is ~30MB)
since they're fully reproducible by the commands above.

## Setup

```bash
cp .env.example .env        # then edit values — never commit the real .env
docker compose up --build   # starts Postgres + FastAPI backend
```

API docs (Swagger UI): http://localhost:8000/docs

## Manual local run (without Docker)

```bash
cd backend
pip install -r requirements.txt --break-system-packages
# make sure Postgres is running and DATABASE_URL in ../.env points to it
uvicorn app.main:app --reload
```

## Main endpoints

```
GET  /api/health

POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me

POST /api/traffic/upload      (multipart CSV, requires login)
GET  /api/traffic             (filter by road_id, start, end)
GET  /api/traffic/{road_id}
GET  /api/traffic/summary
GET  /api/geocoding/search
POST /api/routing/routes
POST /api/routing/routes/refresh
POST /api/simulations
GET  /api/simulations
GET  /api/simulations/{run_id}
POST /api/simulations/fuel-impact (authenticated, non-persisting estimate)
GET  /api/incidents
GET  /api/incidents/mine      (only the signed-in user's reports)
POST /api/incidents
GET  /api/incidents/{incident_id}
PATCH /api/incidents/{incident_id}
POST /api/incidents/{incident_id}/verify   (admin)
POST /api/incidents/{incident_id}/reject   (admin)
POST /api/incidents/{incident_id}/resolve
GET  /api/alerts              (verified incident alerts; status/severity/date filters)
GET  /api/analytics/*
GET  /api/reports             (filtered traffic, incident and simulation summaries)
GET  /api/predictions/pems08/status
POST /api/predictions/pems08/speed
POST /api/predictions/pems08/congestion
```

Route calculations require authentication. OSRM distance and duration are base
routing estimates; they are not live traffic-adjusted travel times. The current
route traffic assessment reports why the PEMS08 model cannot safely evaluate
application simulation observations.

Incident reports are authenticated and begin pending (`reported`). Users may
track only their own pending, verified, rejected, and resolved reports. Pending
and rejected report details are private to the submitter and moderators; public
route warnings and Reports detail lists contain verified/resolved reports.
Administrators can verify or reject pending reports and manage any incident.
Only verified, unresolved incidents appear in active Alerts. The route API only associates an incident with geometry
within 15 m when no road reference is supplied; when a reference is supplied,
it must match an OSRM route-step name/reference and fall within 100 m at most.
Only verified, non-simulated full-road closures exclude a route; unverified
closures and partial obstructions remain warnings. Route plans are refreshed
only on demand; no background monitoring is active.

The Dashboard and Reports pages filter traffic analytics by source and inclusive
date range. The Dashboard's summary statistics and charts query the same selected
traffic records; leaving source blank includes all stored sources. Alerts are
derived only from verified incidents and show the incident's persisted active or
resolved state. They are not real-time notifications and do not have a separate
acknowledgement state. Reports use actual traffic, incident, and simulation-run
records; prediction history is not persisted.

Apply additive schema migrations from `backend/` with
`alembic -c alembic.ini upgrade head`. Existing tables and incident records are
preserved; migrations create missing Phase 1 tables and add missing incident
columns without resetting data. Downgrades intentionally refuse destructive
deletion.

The **Simulations** page is the Stop-and-Go Fuel & Energy Impact Estimator. It reuses a selected SmartCommute route and its already retrieved traffic/weather data, or accepts a user-entered distance; it never starts a duplicate route search. Its formulas, units, heuristic assumptions, missing-data behavior, and limits are documented in [FUEL_ENERGY_ESTIMATOR.md](docs/FUEL_ENERGY_ESTIMATOR.md). The authenticated estimate API does not persist observations. Historical synthetic simulation APIs and their records remain available.

Authenticated users can create and inspect reproducible baseline simulations
through the existing API. Generated traffic observations and run metadata
are persisted atomically; conflicting road/timestamp values return `409` without
changing existing records. Simulation output is synthetic, is labelled with
`source="simulation"`, and is not a live observation or validated prediction.
The existing PEMS08 route compatibility gate remains in effect.

The **Predictions** page calls the standalone PEMS08 endpoints using the model's
20-feature input contract and a manually supplied sensor ID, timestamp, and
same-sensor history. It does not use application traffic records. The speed
response identifies its value as PEMS08 dataset units because the physical
speed unit is not independently verified; prediction history is not saved.
Missing model artifacts are reported as unavailable rather than replaced with
fabricated predictions.

## Initial administrator bootstrap

From `backend/`, run `python -m app.cli.bootstrap_admin` in an interactive
terminal after the database is configured and its `users` table exists. The
CLI prompts with hidden password input, requires matching password entries and
explicit `CREATE ADMIN` confirmation, and refuses if any administrator already
exists. It uses the application's bcrypt password hashing; there is no public
administrator registration endpoint. Do not pass credentials as command-line
arguments or run this bootstrap against production without an approved operator.

The standalone PEMS08 prediction endpoints are separate from route assessment.
Their training source, data and model artifacts are outside this Git repository,
although their runtime dependencies are listed in `backend/requirements.txt`.
A clean clone therefore has no PEMS08 artifacts; the status endpoint reports
artifact availability, and API tests do not load or execute those model files.

## Sample data

`ml/data/sample_traffic_data.csv` — 10 rows including one exact duplicate and two
intentionally invalid rows (impossible speed, out-of-range latitude), used to prove
the validation/duplicate-detection pipeline actually works. Try it:

```bash
curl -X POST http://localhost:8000/api/traffic/upload \
  -H "Authorization: Bearer <your_token>" \
  -F "file=@ml/data/sample_traffic_data.csv"
```

Expected result: `rows_inserted: 7, rows_duplicate: 1, rows_invalid: 2`.

## Module 3 — Preprocessing pipeline

```bash
pip install -r ml/requirements.txt --break-system-packages
python -m ml.preprocessing.run_preprocessing
```

Reads every row from `traffic_records` (real ingested data), cleans it, engineers
features, and writes `ml/data/processed/{train,val,test}.csv` plus
`ml/preprocessing/preprocessing_config.json` documenting exactly what was done —
including the congestion-label thresholds and why the split is chronological, not
random (see docstrings in `ml/preprocessing/split.py` and `features.py`).

`ml/data/synthetic_test_dataset.csv` (576 rows, 2 days, 3 roads) is **synthetic data
generated to exercise the pipeline** — not a real dataset and not used for real
model-accuracy claims. The separate Metro training pipeline uses the public hourly
dataset documented in `docs/DATASETS.md`; neither dataset is interchangeable with
the application simulator data.

## Remaining work

Analytics, geocoding, and the map UI already exist. Hazard-aware route
recommendation now excludes applicable verified closures and can be refreshed
explicitly; it does not provide continuous monitoring. Traffic overlays,
weather integration, simulation studio workflows, explainability, admin tools,
and PDF reporting remain incomplete. See `docs/IMPLEMENTATION_ROADMAP.md`.
The route endpoint still reports incompatible simulation inputs as unavailable
and does not run PEMS08 inference for those records.
