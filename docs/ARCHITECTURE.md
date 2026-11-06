# Architecture

## Current system

```text
React + TypeScript + Vite
  ├─ MapLibre map / OpenFreeMap style
  ├─ Axios API client (JWT from localStorage)
  ├─ Nominatim destination search
  ├─ route cards + source/date-filtered analytics dashboard
  ├─ simulation, incident moderation, and standalone PEMS08 prediction pages
  └─ verified-incident alerts + data-backed reports
          │ HTTP
          ▼
FastAPI backend
  ├─ auth, geocoding, traffic ingestion/retrieval, analytics and reports
  ├─ authenticated simulation, incident moderation, and incident-derived alerts
  ├─ standalone PEMS08 prediction endpoints (independent of application records)
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

Historical behavior: the route feature builder assembled those 20 fields from application simulation records, scaled occupancy, substituted vehicle count for flow, and passed application km/h speed unchanged. That builder is no longer called by the route endpoint. The endpoint now reports `unavailable_incompatible_input` for matched simulation roads and leaves prediction and route-score fields null. The standalone prediction API does not claim a physical unit for its speed result because training/source metadata inspected does not establish that unit; route inference remains disabled until compatibility is demonstrated.

## Rush-hour feature conventions

The application calendar feature `is_rush_hour` follows `ml/preprocessing/features.py`: weekdays 07:00–09:59 and 17:00–19:59 are true; weekends are false. The routing feature builder follows the same convention. The simulator's volume multiplier is a separate generation curve, using hours 07–09 and 16–19 on every day; it is not the `is_rush_hour` calendar feature. Metro has its own dataset-specific window (07:00–09:59 and 16:00–18:59). These separate definitions are preserved and tested rather than silently unified.

## Main request flows

1. Frontend requests destination geocoding from FastAPI, which proxies Nominatim.
2. Frontend sends coordinates to authenticated `POST /api/routing/routes`.
3. Backend calls OSRM for actual route geometries, distances and estimated durations. It samples up to five evenly spaced route vertices per candidate and batches uncached coordinates into one Open-Meteo request. The requested forecast horizon covers the longest candidate trip, rounded up by day plus one day of buffer, with a minimum of two and maximum of seven forecast days. Normalized forecasts are cached in-process for 15 minutes (rounded coordinates at 0.001 degrees and separated by forecast horizon). If refresh fails, cache data up to 30 minutes old may be shown as stale; stale data never enables weather-based ranking.
4. Open-Meteo model-provided current conditions and hourly forecasts cover temperature, precipitation, rain, wind speed, gusts, snowfall and WMO weather codes. These are location-based provider data, not direct roadside observations or road measurements. Forecast values are used for the current estimated travel window and response timestamps/coverage are included.
5. If every feasible route has complete forecast coverage, the recommendation is a transparent rule-based comparison: 70% normalized travel penalty `min(100, max(0, (route metric / best feasible metric - 1) * 100))`, plus 30% weather-exposure index. The exposure index weights normalized mean hourly precipitation 40%, mean wind speed 25%, peak gust 25%, and peak snowfall 10%. Thresholds are 5 mm/h, 60 km/h, 80 km/h and 2 mm/h respectively. Temperature and weather codes are displayed but not included in the score. This is a comparison heuristic, not trained AI or a safety score. Rain does not imply flooding. Confirmed closures remain hard exclusions; other incident reports remain warnings and are not converted into inferred hazards or delays.
6. Weather requests have a 5-second timeout and make at most two attempts for timeouts, connection failures and transient 5xx responses, with a short bounded delay. HTTP 429 and authentication/configuration errors are not retried. If a request fails or any feasible route has incomplete/stale forecast inputs, weather ranking is disabled for the entire comparison and ordinary fastest/shortest OSRM ranking remains in effect with an explanation. Public Open-Meteo is a non-commercial service (education use is permitted), licensed CC-BY 4.0 with attribution and subject to per-IP limits and availability disclaimers; the frontend attributes the displayed forecast to Open-Meteo.
7. For matched simulation records, routing reports `unavailable_incompatible_input`; it does not invoke PEMS08. Local simulation coverage is not provider-reported or live traffic, and does not affect route ranking.
8. Dashboard calls authenticated SQL aggregation endpoints with the selected source/date filters and displays observed traffic analytics.
9. Predictions accepts manually supplied PEMS08 sensor features and calls the separate PEMS08 endpoints; application records are not passed to that pipeline.
10. Alerts list verified incidents and their persisted resolution state. Reports aggregate stored traffic, incident, and simulation-run data; predictions are not persisted.

## Deployment boundary

The repository includes `docker-compose.yml`, `backend/Dockerfile`, and `.env.example`. Compose starts PostgreSQL and FastAPI, but does not include frontend, migrations, or PEMS08 files/artifacts. `backend/app/core/config.py` reads `../.env`; database URL format must match installed driver. CORS allows localhost development origins only. Deployment has not been verified.
