# Architecture

## Current system

```text
React + TypeScript + Vite
  ├─ MapLibre map / OpenFreeMap style
  ├─ Axios API client (JWT from localStorage)
  ├─ Nominatim destination search
  └─ route cards + analytics dashboard
          │ HTTP
          ▼
FastAPI backend
  ├─ auth, geocoding, traffic ingestion/retrieval, analytics
  ├─ OSRM route client and nearest-route-vertex traffic matching
  ├─ route coverage -> application traffic records -> explicit incompatible-input status
  └─ static health endpoint; SQLAlchemy create_all at startup
          │
          ├─ PostgreSQL traffic_records / users
          ├─ public OSRM routing service
          └─ public Nominatim geocoding service

Separate ML pipelines:
  ├─ Metro Interstate hourly single-station volume forecast pipeline (inside Git)
  ├─ PEMS08 5-minute 170-sensor pipeline (outside Git at audit time)
  └─ application simulator (synthetic 5-minute road records)
```

## Data and model boundaries

### Application records and simulator

`backend/app/models/traffic_record.py` stores road id, coordinates, timestamp, vehicle count, average speed (km/h), capacity, occupancy (0–100), weather, and source. `backend/app/traffic/simulation.py` creates seeded synthetic records for three simulated Bengaluru roads. Its `vehicle_count` is a 5-minute count; it is not established as PEMS08 detector flow.

### Metro Interstate

`ml/data/real/metro_interstate_traffic_volume.csv` is the hourly Minneapolis I-94 dataset. `ml/preprocessing/real_dataset_features.py` builds calendar and historical traffic features and an exact T+1h volume target. Weather is excluded from predictors. `ml/training/train_models.py` trains classifiers with chronological train/validation/test splits. This dataset is separate from the application's multi-road schema.

### PEMS08

At audit time, PEMS08 source/artifacts were found outside this Git root: `../ml/preprocessing/pems08_features.py`, `../ml/training/train_pems08_models.py`, `../ml/data/real/PEMS08.npz`, and `../ml/models/pems08/`. Its array is documented by source as 17,856 five-minute timestamps × 170 sensors × flow/occupancy/speed; target horizon is 1 hour. The route service expects a 20-feature schema. No verified geographic coordinates are supplied for PEMS08 sensors.

Historical behavior: the route feature builder assembled those 20 fields from application simulation records, scaled occupancy, substituted vehicle count for flow, and passed application km/h speed unchanged. That builder is no longer called by the route endpoint. The endpoint now reports `unavailable_incompatible_input` for matched simulation roads and leaves prediction and route-score fields null. The PEMS08 API schema labels speed as km/h, but training/source metadata inspected does not establish that unit; route inference remains disabled until compatibility is demonstrated.

## Rush-hour feature conventions

The application calendar feature `is_rush_hour` follows `ml/preprocessing/features.py`: weekdays 07:00–09:59 and 17:00–19:59 are true; weekends are false. The routing feature builder follows the same convention. The simulator's volume multiplier is a separate generation curve, using hours 07–09 and 16–19 on every day; it is not the `is_rush_hour` calendar feature. Metro has its own dataset-specific window (07:00–09:59 and 16:00–18:59). These separate definitions are preserved and tested rather than silently unified.

## Main request flows

1. Frontend requests destination geocoding from FastAPI, which proxies Nominatim.
2. Frontend sends coordinates to authenticated `POST /api/routing/routes`.
3. Backend calls public OSRM, loads all `source="simulation"` traffic rows, and matches roads by minimum distance to route vertices.
4. Backend emits base OSRM distance/duration plus route traffic availability. For matched simulation records, it reports `unavailable_incompatible_input`; it does not invoke PEMS08. Current route response has no explicit recommendation object or forecast timestamp/horizon at route level.
5. Dashboard calls authenticated SQL aggregation endpoints and displays observed traffic analytics.

## Deployment boundary

The repository includes `docker-compose.yml`, `backend/Dockerfile`, and `.env.example`. Compose starts PostgreSQL and FastAPI, but does not include frontend, migrations, or PEMS08 files/artifacts. `backend/app/core/config.py` reads `../.env`; database URL format must match installed driver. CORS allows localhost development origins only. Deployment has not been verified.
