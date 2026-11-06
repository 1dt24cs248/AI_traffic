# Known Issues

Audit date: 2026-10-18. Severity reflects user-facing impact.

## Current implementation update — 2026-10-19

The Dashboard, incident moderation, PEMS08 Predictions, verified-incident Alerts,
and data-backed Reports pages are now connected to their backend endpoints.
Alerts are not real-time and have no separate acknowledgement state. Prediction
history is not saved. These additions do not enable simulation-to-PEMS08 route
inference or change the route safety gate.

Successful uncached TomTom responses from the current-flow and route-flow
endpoints now attempt insert-only persistence in a separate database session.
Persistence failures are logged without provider details and do not fail the live
traffic response. No scheduled collection is active. The provider client does not
return a validated stable segment reference; saved records are provisional and
not eligible for forecasting. TomTom retention/training permissions remain
unverified, so no ML training or forecast use is enabled.

## Critical

- **PEMS08 and simulation are not demonstrated compatible.** The historical feature builder mapped `vehicle_count` to PEMS08 `flow`; app speed is km/h while the PEMS08 unit is not evidenced. The current route endpoint does not call that builder or PEMS08 inference; it returns `unavailable_incompatible_input`. The standalone speed API now reports the PEMS08 dataset value without claiming a physical unit. A simulation-specific model or validated live-data integration is still needed for route predictions.
- **PEMS08 dependencies/artifacts are outside Git.** The service in `backend/app/prediction/service.py` resolves `PROJECT_ROOT` to the workspace parent and looks for `../ml/models/pems08/*.joblib`. The source, tests, NPZ and model metadata were found at the workspace parent, not beneath the Git root. Fresh clones lack them.
- **Standalone PEMS08 artifacts are not portable with this repository.** `joblib`, pandas, NumPy, and scikit-learn are declared in `backend/requirements.txt`, but the training source, dataset, and model artifacts are outside this Git root. API tests mock inference and do not validate loading or running those external artifacts.
- **Backend test setup is environment-sensitive.** Under the ambient database URL, test collection fails because SQLAlchemy's selected dialect imports missing `psycopg`; declared `psycopg2-binary` is installed. Setting `DATABASE_URL=postgresql+psycopg2://...` lets the backend suite run. From repository root, backend imports fail because `backend/` is not added to Python import path.

## High

- **Recommendation is not implemented as route comparison.** `compute_route_score` remains a helper mapping congestion class to 100/70/40/10, but the endpoint does not assign scores or select a route. A compatible route prediction source is required first.
- **Traffic matching can overstate coverage.** `find_traffic_coverage` matches any record for a road to the nearest route vertex, without observation age or segment association. `calculate_routes` loads every simulation record before matching.
- **Static health check.** `/api/health` always returns `ok`; it does not check DB, routing service, or artifact readiness.
- **App startup couples import to database.** `backend/app/main.py` runs `Base.metadata.create_all(bind=engine)` at import/startup; this prevents many tests/tools from importing app modules without the configured driver and reachable DB.
- **Startup schema handling remains mixed.** Alembic configuration and migration revisions exist, but `backend/app/main.py` still calls `Base.metadata.create_all()` at import/startup. Keep migrations as the schema-change mechanism and verify startup behavior against the intended deployment database.

## Medium

- **Outdated status documentation.** `docs/CURRENT_STATUS.md` still claims routing/frontend are absent, despite implementation existing. The current README describes those features accurately. Dataset docs describe Metro but not the PEMS08 pipeline located outside Git.
- **Frontend contract weaknesses.** The API client uses `import.meta as any`; routing types do not include a recommendation field because none exists.
- **Frontend behavior gaps.** Map planner searches only destination locations, origin is GPS or manual coordinates, observed traffic is not rendered, and navigation controls only perform approximate point-to-route deviation checks.
- **Analytics presentation uses observed speed as a congestion proxy.** It is real SQL data, but not a model prediction or calibrated traffic index. Dashboard filters now include source and date range; the underlying observations still vary in provenance and measurement semantics.
- **Alert scope is deliberately limited.** The Alerts page lists verified incidents and their persisted resolved/active status; it does not infer threshold-based traffic alerts, provide separate acknowledgement, or send real-time notifications.
- **Prediction history is not persisted.** The Predictions page runs standalone PEMS08 speed/congestion inference only when its feature schema and artifacts are available; results are not retained for Reports.
- **Vite bundle warning.** Production JS bundle is ~1.67 MB before gzip; build passes but warns above 500 kB.
- **Rush-hour conventions differ by purpose.** Application/routing calendar features flag weekdays 07–09 and 17–19; the simulator generation multiplier uses 07–09 and 16–19 on all days; Metro keeps 07–09 and 16–18. Boundary tests cover each convention; weekend-exclusion tests cover the application/routing feature only, not Metro. `docs/DATASETS.md` also contains numbered items out of sequence.

## Baseline-only / not verified

- Docker Compose and PostgreSQL startup have not been verified in this audit.
- External OSRM, Nominatim, MapLibre tiles, and route flows were not exercised.
- Prior claims of database-backed tests in `docs/CURRENT_STATUS.md` were not repeated; they are historical documentation, not baseline results.
