# Project Status

Audit date: 2026-10-18 (Asia/Calcutta)

## Repository baseline

- Git root: this directory (`traffic-flow-predictor/`), branch `main`, commit `0c61455c7db8885562abc1db0fa90fb7c6e3c0c8`.
- At audit start, `backend/app/routing/traffic_feature_builder.py` was modified and three audit ZIP files were untracked. These are pre-existing user changes and are preserved.
- The supplied workspace is a parent directory containing this Git repository plus separate, untracked outer-level ML files/artifacts. The PEMS08 pipeline and joblib artifacts are in the outer-level `ml/`, not in this repository. The backend prediction service resolves its model root to that outer directory.

## Feature status

| Feature | Status | Evidence / limitation |
|---|---|---|
| React + TypeScript frontend | Implemented and verified | `frontend/package.json`, `frontend/src/App.tsx`; `npm run build` succeeds. |
| MapLibre route visualization | Implemented but not verified end to end | `frontend/src/components/MapView.tsx`, `frontend/src/pages/MapRouting.tsx`; external tiles and browser runtime not exercised. |
| Location search | Implemented but not verified end to end | Frontend `services/geocoding.ts`; backend Nominatim client and geocoding routes. External Nominatim access not exercised. |
| OSRM routes and alternatives | Implemented but not verified end to end | `backend/app/routing/osrm_client.py`, `/api/routing/routes`; public OSRM call not exercised. |
| PostgreSQL traffic storage / upload | Implemented but not verified in this audit | `backend/app/models/traffic_record.py`, `traffic/ingestion.py`, `api/traffic_routes.py`; no DB-backed integration run. |
| Observed traffic matching / coverage | Partially implemented | `routing/traffic_coverage.py` and `traffic_matcher.py`; nearest route vertices only, in-memory scan, no segment snapping or freshness filtering. |
| PEMS08 pipeline (separate) | Implemented but not verified from this repository | Outer workspace `../ml/preprocessing/pems08_features.py`, `../ml/training/train_pems08_models.py`, tests and artifacts. It is outside Git root, so not portable as checked out. |
| Metro Interstate ML pipeline | Implemented and verified at test level | `ml/preprocessing/real_dataset_features.py`, `ml/training/train_models.py`; 8 tests pass. Dataset and joblib models are present in repository tree. |
| Application prediction on simulation rows | Blocked by missing compatible model | Route assessment deliberately returns `unavailable_incompatible_input`; the PEMS08 model is not invoked from the route endpoint. |
| Simulation | Implemented but not verified end to end | `backend/app/traffic/simulation.py`; deterministic seeded generator; no simulator API/replay endpoint found in registered routes. |
| Traffic analytics | Implemented but not verified in this audit | SQL aggregates in `backend/app/services/analytics.py`, API routes, and dashboard charts. Claims of earlier DB tests exist in stale `docs/CURRENT_STATUS.md`, but were not reproduced here. |
| Route scoring / recommendation | Partially implemented | `routing/traffic_scoring.py` fixed class-to-score helper remains, but the route endpoint does not assign scores or rank/recommend alternatives. |
| Authentication | Implemented but not verified in this audit | Auth API, JWT and password hashing files exist; live database/auth flow was not run. |
| Health / startup / deployment | Partially implemented | `/api/health` is static; `main.py` creates tables at import; Docker Compose exists but was not run. |
| Automated backend routing tests | Implemented and verified with environment override | 49 tests pass with `DATABASE_URL=postgresql+psycopg2://...`, including mocked endpoint flows; ambient URL selects missing `psycopg`, so clean setup still needs dependency/config alignment. |
| Frontend tests | Not implemented | No frontend test script or test files in `frontend/package.json`/tree. |

## Baseline verification

- `python -m pytest -q` from Git root: collection error, `ModuleNotFoundError: No module named 'app'` because backend package root is not on import path.
- `python -m pytest -q tests` from `backend/` with the ambient database URL: collection error, `ModuleNotFoundError: No module named 'psycopg'` while SQLAlchemy creates the engine.
- `python -m pytest -q tests` from `ml/`: **8 passed**.
- After overriding the ambient `DATABASE_URL` to the driver available in this environment (`postgresql+psycopg2://...`), `python -m pytest -q tests` from `backend/`: **19 passed** after the incompatible route inference was disabled and the tests were updated to assert unavailable behavior. The backend requirements and ambient environment still need alignment for a fresh install.
- `npm run build` from `frontend/`: **passed** (TypeScript and Vite production build). Vite warns that the main JS chunk is about 1.67 MB uncompressed.
- Docker, database-backed API integration, external routing/geocoding, and browser runtime were not run.

## Critical findings

1. Historical route code sent simulated/local-road values to PEMS08 after substituting `vehicle_count` for sensor flow. That route inference path is now disabled; the model's speed unit is not established and the app schema says km/h.
2. PEMS08 inference artifacts, training pipeline, tests, and metadata are outside the Git repository. A clean clone cannot reproduce the standalone PEMS08 endpoints. Route assessment does not load that model.
3. Historical behavior (removed): the former route assessment averaged predictions equally across available roads, regardless of route length or coverage. The current endpoint does not aggregate predictions or assign route scores; route scoring is not a recommendation comparison and base OSRM duration is not adjusted.
4. `backend/app/main.py` makes a database connection at import and runs `create_all` at startup; static health does not check database/model/provider availability. No Alembic migration directory is present in this repo tree.
5. The current browser experience includes routes and route cards, but not all requested integration: routing requires auth, source selection is current location or manual coordinates (place search is for destination only), and observed traffic is not drawn as route-segment overlay.

## Implementation progress after the audit

- Route-level PEMS08 inference from application simulation rows is now disabled. Matched records return `unavailable_incompatible_input`, with null predictions/scores and a reason explaining the incompatible source and unverified speed units. Standalone PEMS08 prediction endpoints remain available for inputs that satisfy their explicit 20-feature request schema.
- Frontend route status types now include the new unavailable state and use a typed matched-road shape.
- README status/endpoint claims were corrected to reflect the actual repository.
- Backend suite: 49 passed using explicit psycopg2 URL, including mocked `calculate_routes` endpoint tests for OSRM success/error, coverage, unavailable prediction values, forbidden model/scorer calls, and DB close paths. ML suite: 32 passed, including application/Metro rush-hour calendar boundaries and weekend behavior plus simulator volume-profile boundaries. These are mocked/unit tests; no live DB/provider route integration has been verified.

## Compatibility findings

- Metro: one Minneapolis I-94 westbound hourly station; target is next-hour volume-quantile congestion; no speed/sensor-level road identity. Ten historical/calendar features; weather removed from input. See `ml/preprocessing/real_dataset_features.py` and `docs/DATASETS.md`.
- PEMS08: outer-level NPZ shape `(17856, 170, 3)`, 5-minute observations, 170 sensors, 3 channels flow/occupancy/speed, 1-hour target (12 steps). The separate pipeline has sensor-specific lags and chronological timestamp-aligned splits. The project docs available within Git do not document this pipeline; outer source has comments and model metadata.
- Simulation: `vehicle_count` generated every 5 minutes for three synthetic Bengaluru roads, average speed stored in km/h, occupancy 0–100. No demonstrated equivalence to PEMS08 sensor flow regime or PEMS08 speed unit. Occupancy scale division by 100 is numeric normalization only and does not demonstrate sensor/road comparability.
- Rush-hour conventions are documented and regression-tested by purpose: application and routing calendar features use weekday 07–09/17–19 and exclude weekends; simulator volume generation uses 07–09/16–19 on all days; Metro retains its separate 07–09/16–18 dataset feature window. These are distinct definitions, not a shared feature contract.
