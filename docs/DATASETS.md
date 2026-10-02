# Datasets

## Real dataset: Metro Interstate Traffic Volume

- **Source**: UCI Machine Learning Repository
- **Original URL**: https://archive.ics.uci.edu/ml/machine-learning-databases/00492/Metro_Interstate_Traffic_Volume.csv.gz
- **Downloaded via**: GitHub mirror (`raw.githubusercontent.com/ManojKumarMaruthi/Regression/master/Metro_Interstate_Traffic_Volume.csv`) — this sandbox's network egress is restricted to an allowlist that does not include `archive.ics.uci.edu`, so the file was retrieved from a mirror and its integrity verified against the file's independently-documented properties before use (see Verification below)
- **Date accessed**: this session
- **License**: UCI ML Repository datasets are made available for research/academic use; the original data provider is the Minnesota Department of Transportation (traffic) and OpenWeatherMap (weather)
- **Local path**: `ml/data/real/metro_interstate_traffic_volume.csv`

### Verification performed

- Row count: 48,204 data rows (48,205 lines including header) — matches the count documented by three independent public repositories that describe this dataset
- File size: 3,237,208 bytes — exact match
- SHA-256: `749c90d720360a4215bb15345526073c079ba4cc95e3fa558796d083f85fce9e` — exact match to the checksum documented by an independent public repository
- Not verified against the original UCI server directly (network restriction, above) — verified by independent cross-reference instead

### Fields (as supplied, unmodified)

| Column | Description |
|---|---|
| `holiday` | Categorical US holiday name, or "None". Only populated on the 00:00 row of each holiday. |
| `temp` | Temperature in Kelvin |
| `rain_1h` | mm of rain in the past hour |
| `snow_1h` | mm of snow in the past hour |
| `clouds_all` | % cloud cover |
| `weather_main` / `weather_description` | Categorical weather condition |
| `date_time` | Hourly timestamp |
| `traffic_volume` | Hourly traffic volume — the target variable |

### Known limitations (stated honestly, not hidden)

1. **Single location, single direction**: this is I-94 westbound at MN DoT ATR Station 301, near Minneapolis-St. Paul. There is no `road_id`, no multiple roads, no latitude/longitude per segment. This is fundamentally different from the multi-road schema used elsewhere in this project (`traffic_records` table, Modules 1-4). **This dataset is used standalone for Module 5 model training/evaluation** — it is not loaded into the application's PostgreSQL database or the live ingestion pipeline.
2. **No speed field**: unlike our own `traffic_records` schema, this dataset has no `average_speed`. The congestion-labeling methodology used in `ml/preprocessing/features.py` (speed-ratio based) cannot be applied here. A separate, explicitly different methodology is used for this dataset — documented in `ml/preprocessing/real_dataset_features.py` — based on traffic-volume quantiles of the **target hour (T+1h)**, since volume is the only load indicator available. This is a genuinely different (and weaker) proxy for congestion than a real speed measurement, and is documented as such rather than silently reused. **Audit correction**: an earlier version of this pipeline computed the label from the same row's own volume (same timestamp as the input features) — a same-timestamp nowcast mislabeled as a "+60 minute forecast". This has been corrected; the label now genuinely reflects the volume one hour after the feature timestamp, with an explicit timestamp check (not a blind shift) so rows spanning the data gap below don't get a fabricated target. See `docs/CURRENT_STATUS.md` for the full before/after.
6. **Weather features excluded from Module 5 modeling**: the corrected T→T+1h pipeline does not use `temp`, `rain_1h`, `snow_1h`, `clouds_all`, or `weather_main` as model inputs at all, because this repo has no weather-forecast source — using the dataset's actual (historical) weather for the target hour would itself be a form of leakage relative to a genuine prediction-time system. Calendar features (hour, day_of_week, month, weekend, holiday, rush-hour) and historical traffic lag/rolling features are used instead.
3. **Data gap**: no observations between August 2014 and mid-2015 (documented by multiple independent sources). Lag/rolling features that would span this gap are treated as missing, not silently computed across the gap — see the time-delta guard in `real_dataset_features.py`.
4. **Known sensor artifacts**: a small number of rows record implausible values (`temp = 0 K`, one `rain_1h = 9831.3mm`). These are handled explicitly in cleaning, not silently imputed with invented numbers — outlier rows are flagged and either dropped or documented, never replaced with a fabricated "corrected" value.
5. **Duplicate timestamps**: ~17 exact duplicate rows and additional repeated timestamps under different weather descriptions exist in the raw file (documented by independent sources); deduplication is handled explicitly in cleaning.

### Why this dataset, given the constraints

The project spec requires a real, licensed, well-documented public dataset with sufficient records and timestamp resolution for time-series forecasting (Section 19). This dataset satisfies size (48k+ hourly records over ~6 years), license clarity, and reproducibility (its content is independently verifiable, as shown above) within what this sandboxed environment's network access actually allows me to retrieve. Its lack of a speed field and single-location scope are real, stated constraints — not glossed over — and the modeling in Module 5 is scoped accordingly (volume-based congestion classification for this dataset, kept separate from the speed-based methodology used for the application's own multi-road data).
