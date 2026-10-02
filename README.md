# AI Traffic Flow Predictor

Spatio-temporal traffic congestion prediction and dynamic route recommendation system — BCA final-year project.

## Status

- **Module 1 — Auth**: done & tested
- **Module 2 — Traffic Data Ingestion**: done & tested
- **Module 3 — Preprocessing**: done & tested
- **Module 4 — Analytics**: done & tested
- **Module 5 — ML Training** & **Module 6 — Evaluation**: done & tested — real public
  dataset (Metro Interstate Traffic Volume, UCI), genuine T→T+1h forecast (audited and
  corrected — an earlier version was accidentally same-timestamp nowcasting; see
  `docs/CURRENT_STATUS.md` for the full before/after). Random Forest: **91.4% test
  accuracy / 0.914 test F1-macro**. 8 automated leakage/correctness tests, all passing.
  See `docs/DATASETS.md` and `docs/CURRENT_STATUS.md` for full methodology.
- Module 7 onward: not yet built

See `docs/CURRENT_STATUS.md` for the full honest audit, including what is
explicitly NOT started (explainability, alerts, routing, frontend, Docker verification, etc).

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

## Endpoints implemented so far

```
GET  /api/health

POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me

POST /api/traffic/upload      (multipart CSV, requires login)
GET  /api/traffic             (filter by road_id, start, end)
GET  /api/traffic/{road_id}
GET  /api/traffic/summary
```

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
model-accuracy claims. Module 5 will use an actual public traffic dataset per the
spec's dataset-selection requirement.

## Next phases (not yet built — see project spec)

4. Traffic analytics: peak hours, congestion frequency, heatmaps
5. ML congestion classifier: baseline (Logistic Regression) vs Random Forest/XGBoost, with real evaluation metrics
6. Explainability layer (feature importance / SHAP)
7. Alerts, routing engine, route recommendation, map UI, admin dashboard, PDF reports

Each phase will be added the same way: real code, real file paths, tested before moving on.
