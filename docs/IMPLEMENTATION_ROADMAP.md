# Implementation Roadmap

Audit date: 2026-10-18. Order is adjusted to resolve trust and integration dependencies before product-layer expansion.

## Phase 1 — Audit and baseline (complete)

Recorded repository identity and dirty state; inspected current docs, application structure, APIs, model pipelines, artifacts, simulator, tests, and frontend build. Evidence and exact baseline results are in `PROJECT_STATUS.md`.

## Phase 2 — Model and data contract safety

1. Keep Metro, PEMS08, and simulation pipelines separate.
2. Include the actual PEMS08 source, tests, metadata, and artifact acquisition/training instructions inside the repository, or disable claims of availability when they are absent from a clean checkout.
3. Add explicit artifact metadata (feature order, target, horizon, units, dataset identity, model version) and verify it at model load.
4. Keep the simulation-to-PEMS08 route path disabled unless a documented, validated input contract exists. Return structured unavailable status with reasons for incompatible source/units.
5. Resolve environment dependency mismatch and make imports testable without a live database connection.

Progress: item 4 is complete for route inference: the route assessment now returns `unavailable_incompatible_input` and does not call the PEMS08 model for application simulation rows. Items 1–3 and 5 remain open.

Rush-hour conventions: the application and routing calendar feature uses weekday 07–09 and 17–19, with weekend values false. This matches `ml/preprocessing/features.py`. The simulator's 07–09/16–19 all-day volume multiplier and Metro's separate 07–09/16–18 calendar feature remain generator/dataset-specific. Tests cover hour boundaries for all these conventions and weekend exclusion for the application/routing calendar feature; Metro weekend behavior is not currently tested.

## Phase 3 — Backend reliability and contract

1. Define prediction and route response schemas with status, source, observation time, horizon, freshness, coverage, model identity, and explicit limitations.
2. Add route-data query bounds and freshness handling; avoid loading all simulation records and repeatedly scanning every route coordinate.
3. Verify OSRM response/error handling and injectable provider URL/configuration.
4. Ensure health reports database and model readiness without making liveness dependent on optional ML artifacts.

## Phase 4 — Explainable route comparison

1. Preserve OSRM distance and base duration as routing estimates.
2. Add route-level traffic coverage and prediction availability separately from base route facts.
3. Rank only routes with comparable valid signals; document a deterministic scoring formula and weights. Missing/unavailable is never scored as favorable.
4. Explain recommendation and disclose coverage, source, age, horizon, and unsupported conditions.

## Phase 5 — Frontend and map integration

1. Add origin and destination place search/selection, route selection, and clear empty/loading/error states.
2. Reflect current API types exactly; show OSRM estimates separately from observed and predicted traffic.
3. Draw only supported traffic observations/predictions; add legend and source/freshness labeling.
4. Ensure selecting a route updates the map and comparison/recommendation panel.
5. Split the current large map bundle if practical; add frontend integration/build checks.

## Phase 6 — Simulation and analytics

1. Expose controlled simulation generation/replay without destructive reseeding.
2. Label all simulation output consistently and keep analytics filters/data provenance visible.
3. Verify analytics against database-backed fixtures and missing-data cases.

## Phase 7 — Regression and deployment readiness

1. Run actual inference tests against each available artifact as well as isolated mocked boundary tests.
2. Add route, coverage, unavailable, provider failure, DB failure, and schema integration tests.
3. Verify a fresh environment setup, frontend production build, migrations, Docker startup, artifact portability, CORS, and environment handling.
4. Update setup, architecture, issues, and status docs with only reproduced results.

## Dependency rationale

The compatibility gate precedes recommendation and UI work. The existing inference path is not safe to expose as a route prediction until sensor/source and units are validated. Route ranking depends on a trustworthy traffic assessment contract. Frontend refinements then consume a stable contract rather than masking unreliable model inputs.
