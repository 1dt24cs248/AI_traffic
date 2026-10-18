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
GET  /api/analytics/*
POST /api/predictions/pems08/speed
POST /api/predictions/pems08/congestion
```

Route calculations require authentication. OSRM distance and duration are base
routing estimates; they are not live traffic-adjusted travel times. The current
route traffic assessment reports why the PEMS08 model cannot safely evaluate
application simulation observations.

The standalone PEMS08 prediction endpoints are separate from route assessment.
Their model files are outside this Git repository, and `backend/requirements.txt`
does not currently include their `joblib`/pandas runtime dependencies; they are
not verified for a clean installation.

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

Analytics, routing, geocoding, and the map UI already exist. Route recommendation,
traffic overlays, alerts, explainability, admin tools, and PDF reporting remain
incomplete. See `docs/IMPLEMENTATION_ROADMAP.md`; the route endpoint reports
incompatible simulation inputs as unavailable and does not run PEMS08 inference
for those records.
