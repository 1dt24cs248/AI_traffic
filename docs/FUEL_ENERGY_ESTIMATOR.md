# Stop-and-Go Fuel & Energy Impact Estimator

The Simulations navigation page now provides an approximate commute energy scenario estimator. SmartCommute AI remains the only route planner. From a SmartCommute route card, select **Estimate fuel & energy** to transfer that route's OSRM distance, its already-retrieved TomTom route samples, and its Open-Meteo route forecast into the estimator. The handoff stays in the current browser tab's session storage and expires after two hours. The estimator does not make routing, traffic, or weather requests. It can also use a user-entered distance without route traffic data.

## Inputs and units

- Petrol car, diesel car, and petrol two-wheeler: user-entered km/L.
- Electric vehicle: user-entered kWh/100 km.
- Optional petrol/diesel price: ₹/L; optional electricity tariff: ₹/kWh. Leave blank when unknown; additional cost is then unavailable.
- Optional EV battery capacity in kWh and current charge from 0–100%. Charge requires capacity. These are user-entered values; example placeholders are not defaults.
- Congestion scenario cap: default 15%, editable from 0–30%. It is an illustrative, configurable heuristic assumption, not measured or vehicle-calibrated data.

## Formula and traffic rules

For combustion vehicles, baseline litres = distance (km) ÷ efficiency (km/L). For EVs, baseline kWh = distance (km) × efficiency (kWh/100 km) ÷ 100.

Only TomTom samples with finite `current_speed >= 0` and finite `free_flow_speed > 0` are paired. Their ratio is current speed ÷ free-flow speed. Samples are categorized as near free-flow (≥0.85), reduced (≥0.60 and <0.85), heavy reduction (≥0.40 and <0.60), or severe reduction (<0.40). These are project heuristics, not provider or regulatory classifications.

Mean sampled speed deficit = mean of `max(0, 1 − min(1, speed ratio))`. Additional fuel/energy = baseline use × (user-selected scenario cap ÷ 100) × mean sampled speed deficit. Total = baseline + additional. Additional cost = additional units × the user's optional price. Additional battery percentage = additional kWh ÷ battery capacity × 100; estimated post-trip charge = current charge − (total kWh ÷ capacity × 100).

No valid paired samples means baseline remains calculable, while additional use, total use, cost, and battery effects that depend on additional use are unavailable. Sample counts describe sampled points, not continuous route coverage. The estimate does not infer bottlenecks, idling duration, actual consumption, or savings. Weather is displayed when passed from the route, but no weather adjustment is applied because this project has no validated vehicle-specific weather-to-energy rule. Open-Meteo forecasts are provider model data for sampled locations, not roadside measurements.

Driving style, passengers/cargo, vehicle condition, temperature, weather, accessory load, and vehicle-specific regenerative braking affect real consumption. This is a scenario comparison aid, not a trained AI prediction, measurement, or guaranteed saving.

The authenticated endpoint is `POST /api/simulations/fuel-impact`; it calculates an estimate only and does not persist traffic observations or simulation runs.

## Incident reports and moderation

Reports submitted from Map & Routing are stored with status `reported` and `verified=false`. A submitter can see only their own pending, rejected, verified, and resolved records through `GET /api/incidents/mine` and the **My incident reports** panel on Reports. Other ordinary users see incident details only after verification; the shared report analytics endpoint includes only verified/resolved incident details. Active Alerts require both `verified=true` and status `verified`. Rejected and resolved reports are not active alerts.

Only `User.role == ADMIN` passes the `require_admin` dependency used by moderation endpoints. There is no default administrator or public role-change endpoint. The verified initial setup mechanism is a one-time interactive CLI: configure the database and apply `alembic -c alembic.ini upgrade head`, ensure the `users` table exists, then from `backend/` run `python -m app.cli.bootstrap_admin`. The CLI prompts for email, name, and a matching password using hidden input; it requires typing `CREATE ADMIN`, enforces the password policy, and refuses when an administrator or that email already exists. Do not provide passwords as arguments or use this process without an authorized database operator. Sign in through the normal login page and confirm the current user's role is `ADMIN`; the UI then exposes Incident moderation.

New `REJECTED` status support uses an additive Alembic enum migration. Existing incident rows are preserved; downgrade is intentionally unsupported.

## Run and test

From the repository root, run `npm test` and `npm run build` in `frontend/`. From `backend/`, run `python -m pytest tests -q`; from repository root, run `python -m pytest ml/tests -q`. Focused coverage for the calculator and moderation workflow is in `backend/tests/test_fuel_impact.py`, `backend/tests/test_incidents.py`, `backend/tests/test_alerts_reports.py`, and `backend/tests/test_simulations.py`.
