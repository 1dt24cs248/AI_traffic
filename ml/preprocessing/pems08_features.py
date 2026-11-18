"""
PEMS08 preprocessing — a genuine T -> T+1h multi-sensor forecasting pipeline.

Kept entirely separate from ml/preprocessing/real_dataset_features.py (Metro) and
ml/preprocessing/features.py (application schema) — different dataset, different
schema, different sensor structure. See docs/DATASETS.md for full dataset facts.

DATASET FACTS (independently verified against the actual uploaded PEMS08.npz,
not assumed from documentation):
  shape=(17856, 170, 3), dtype=float64, 0 NaN, 0 Inf
  channels: 0=flow, 1=occupancy, 2=speed (verified via value-range/correlation evidence)
  5-minute interval, 2016-07-01 00:00:00 -> 2016-08-31 23:55:00 (verified by exact
            reconstruction match)
  170 sensor columns, of which 25 form four exact-duplicate groups:
    [48, 61, 80, 121, 122, 123, 141, 142]
    [50, 51, 74, 75, 90, 91, 115, 131]
    [55, 70, 73, 81, 83, 84, 159]
    [62, 109]
  No verified latitude/longitude or road names exist for this file — none are used
  or invented anywhere in this pipeline.

DESIGN DECISIONS (final, as specified):
- NO rolling features in this experiment (removed after review — current-T values
  plus explicit lag features are used instead; rolling_flow/speed/occupancy were
  implemented and tested in an earlier iteration but are deliberately excluded here).
- Current-T flow/occupancy/speed ARE used as direct features (legitimately known at
  prediction time).
- No duplicate_group_id feature — duplicate sensors are documented, not modeled.
- No is_holiday — PEMS08 has no holiday field to derive one from.
- target_timestamp, target_speed are retained for audit/testing but are NEVER placed
  in FEATURE_COLUMNS.
- Rush-hour bounds: 07-09 and 17-19 on weekdays (differs slightly from
  real_dataset_features.py's 16-18 evening bound for Metro — a small pre-existing
  inconsistency between the two files, documented not resolved).
- Chronological split is snapped to TIMESTAMP boundaries, not raw row position.
  Splitting by row position alone can cut through the ~170 sensor rows that share
  a single timestamp, causing train's last row and val's first row to have an
  IDENTICAL timestamp — this was caught by an earlier failing test run, not assumed
  safe. The fix: compute split boundaries on the sorted array of UNIQUE timestamps,
  then use searchsorted to find the row index where each boundary timestamp begins.

Run standalone: python -m ml.preprocessing.pems08_features
"""
import os
import time
import numpy as np
import pandas as pd

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "real", "PEMS08.npz")

EXPECTED_SHAPE = (17856, 170, 3)
N_TIMESTEPS, N_SENSORS, N_CHANNELS = EXPECTED_SHAPE
FREQ = "5min"
START_TIMESTAMP = pd.Timestamp("2016-07-01 00:00:00")

HORIZON_STEPS = 12  # 1 hour at 5-minute resolution
LAG_STEPS = {"5m": 1, "15m": 3, "30m": 6, "1h": 12}

CONGESTION_LABELS = ["LOW", "MEDIUM", "HIGH", "SEVERE"]
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15

DUPLICATE_SENSOR_GROUPS = [
    [48, 61, 80, 121, 122, 123, 141, 142],
    [50, 51, 74, 75, 90, 91, 115, 131],
    [55, 70, 73, 81, 83, 84, 159],
    [62, 109],
]


def load_raw() -> np.ndarray:
    """Loads and validates the raw array. Fails loudly on any mismatch against what
    was independently verified — this is not a re-trust of documentation."""
    f = np.load(RAW_PATH)
    if "data" not in f:
        raise ValueError(f"Expected key 'data' in {RAW_PATH}, found: {list(f.keys())}")
    data = f["data"]
    if data.shape != EXPECTED_SHAPE:
        raise ValueError(f"Expected shape {EXPECTED_SHAPE}, got {data.shape}")
    if np.isnan(data).sum() != 0:
        raise ValueError(f"Expected 0 NaN, found {np.isnan(data).sum()}")
    if np.isinf(data).sum() != 0:
        raise ValueError(f"Expected 0 Inf, found {np.isinf(data).sum()}")
    return data


def build_long_dataframe(data: np.ndarray) -> pd.DataFrame:
    """
    Vectorized reshape from (17856, 170, 3) into a long-format table.
    dtype: float64 -> float32 for the three measurement channels — a real precision
    change, disclosed and numerically verified (see verify_downcast_precision) rather
    than silently assumed harmless. sensor_id stored as int16.
    """
    timestamps = pd.date_range(start=START_TIMESTAMP, periods=N_TIMESTEPS, freq=FREQ)

    timestamp_col = np.repeat(timestamps.values, N_SENSORS)
    sensor_col = np.tile(np.arange(N_SENSORS, dtype=np.int16), N_TIMESTEPS)

    flow = data[:, :, 0].reshape(-1).astype(np.float32)
    occupancy = data[:, :, 1].reshape(-1).astype(np.float32)
    speed = data[:, :, 2].reshape(-1).astype(np.float32)

    df = pd.DataFrame({
        "sensor_id": sensor_col,
        "timestamp": timestamp_col,
        "flow": flow,
        "occupancy": occupancy,
        "speed": speed,
    })
    return df


def verify_downcast_precision(original: np.ndarray, df: pd.DataFrame) -> dict:
    """Numerically confirms the float64->float32 downcast did not materially change values."""
    orig_flow = original[:, :, 0].reshape(-1)
    orig_occ = original[:, :, 1].reshape(-1)
    orig_speed = original[:, :, 2].reshape(-1)

    return {
        "max_abs_diff_flow": float(np.abs(orig_flow - df["flow"].to_numpy(dtype=np.float64)).max()),
        "max_abs_diff_occupancy": float(np.abs(orig_occ - df["occupancy"].to_numpy(dtype=np.float64)).max()),
        "max_abs_diff_speed": float(np.abs(orig_speed - df["speed"].to_numpy(dtype=np.float64)).max()),
    }


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar features known in advance at prediction time T. No is_holiday: PEMS08
    has no holiday field to derive one from."""
    df = df.copy()
    ts = df["timestamp"]
    df["hour"] = ts.dt.hour.astype(np.int8)
    df["day_of_week"] = ts.dt.dayofweek.astype(np.int8)
    df["month"] = ts.dt.month.astype(np.int8)
    df["is_weekend"] = ts.dt.dayofweek.isin([5, 6]).astype(np.int8)
    df["is_rush_hour"] = (
        (~df["is_weekend"].astype(bool)) & (df["hour"].between(7, 9) | df["hour"].between(17, 19))
    ).astype(np.int8)
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lag features computed strictly PER SENSOR, sorted by time. groupby.shift never
    crosses group boundaries — sensor A's lag can never come from sensor B."""
    df = df.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    grp = df.groupby("sensor_id")

    for channel in ["flow", "speed", "occupancy"]:
        for label, steps in LAG_STEPS.items():
            df[f"{channel}_lag_{label}"] = grp[channel].shift(steps).astype(np.float32)
    return df


def add_forecast_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Target construction: for sensor S at timestamp T, target comes from sensor S at
    T+12 steps (T+1h) via groupby().shift(-HORIZON_STEPS) — scoped per-sensor, never
    a raw whole-dataframe shift(-12) that could cross sensor boundaries.
    """
    df = df.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    grp = df.groupby("sensor_id")

    df["target_speed"] = grp["speed"].shift(-HORIZON_STEPS).astype(np.float32)
    df["target_timestamp"] = grp["timestamp"].shift(-HORIZON_STEPS)

    has_target = df["target_timestamp"].notna()
    gap = df.loc[has_target, "target_timestamp"] - df.loc[has_target, "timestamp"]
    if not (gap == pd.Timedelta(hours=1)).all():
        bad = gap[gap != pd.Timedelta(hours=1)]
        raise ValueError(f"Target timestamp relationship violated for {len(bad)} rows — refusing to proceed")

    return df


def compute_timestamp_aligned_split(df: pd.DataFrame) -> dict:
    """
    Computes train/val/test row-index boundaries snapped to TIMESTAMP boundaries,
    not raw row position. df must already be sorted by timestamp.

    Why this matters (found via a failing test, not assumed): ~170 sensor rows share
    every single timestamp. Splitting by raw row fraction can land in the middle of
    one timestamp's block of sensor rows, giving train's last row and val's first row
    an IDENTICAL timestamp — a real chronological-split violation. This function
    guarantees every row for a given timestamp lands entirely in one split.
    """
    unique_ts = df["timestamp"].unique()  # already sorted, since df is sorted by timestamp
    n_ts = len(unique_ts)
    train_end_ts_idx = int(n_ts * TRAIN_FRAC)
    val_end_ts_idx = int(n_ts * (TRAIN_FRAC + VAL_FRAC))

    val_start_ts = unique_ts[train_end_ts_idx]
    test_start_ts = unique_ts[val_end_ts_idx]

    ts_series = df["timestamp"]
    train_end_idx = int(ts_series.searchsorted(val_start_ts, side="left"))
    val_end_idx = int(ts_series.searchsorted(test_start_ts, side="left"))

    return {"train_end_idx": train_end_idx, "val_end_idx": val_end_idx}


def add_congestion_label(df: pd.DataFrame, train_end_idx: int) -> tuple[pd.DataFrame, dict]:
    """
    Per-sensor free-flow speed = 95th percentile of that sensor's speed, computed
    from the TRAIN split's rows only. Applied to target_speed (the label describes
    congestion AT the target hour, not the feature hour).
    """
    df = df.copy()
    train_df = df.iloc[:train_end_idx]
    free_flow_by_sensor = train_df.groupby("sensor_id")["speed"].quantile(0.95)

    df["_free_flow_speed"] = df["sensor_id"].map(free_flow_by_sensor)
    df["_speed_ratio"] = df["target_speed"] / df["_free_flow_speed"]

    bins = [-np.inf, 0.25, 0.50, 0.75, np.inf]
    labels = ["SEVERE", "HIGH", "MEDIUM", "LOW"]
    df["target_congestion_1h"] = pd.cut(df["_speed_ratio"], bins=bins, labels=labels)

    thresholds_by_sensor = free_flow_by_sensor.to_dict()
    df = df.drop(columns=["_free_flow_speed", "_speed_ratio"])
    return df, thresholds_by_sensor


FEATURE_COLUMNS = [
    "flow", "occupancy", "speed",
    "flow_lag_5m", "flow_lag_15m", "flow_lag_30m", "flow_lag_1h",
    "speed_lag_5m", "speed_lag_15m", "speed_lag_30m", "speed_lag_1h",
    "occupancy_lag_5m", "occupancy_lag_15m", "occupancy_lag_30m", "occupancy_lag_1h",
    "hour", "day_of_week", "month", "is_weekend", "is_rush_hour",
]
# Deliberately excluded from FEATURE_COLUMNS — audit/testing columns only.
AUDIT_COLUMNS = ["target_timestamp", "target_speed"]
TARGET_COLUMN = "target_congestion_1h"


def run(verbose: bool = True) -> tuple[pd.DataFrame, dict, dict, dict]:
    """Returns (trainable_df, free_flow_thresholds, split_indices, run_stats)."""
    t_start = time.time()
    stats = {}

    raw = load_raw()
    stats["raw_shape"] = raw.shape

    long_df = build_long_dataframe(raw)
    stats["precision_check"] = verify_downcast_precision(raw, long_df)
    stats["long_df_rows"] = len(long_df)
    stats["long_df_memory_bytes"] = int(long_df.memory_usage(deep=True).sum())

    featured = add_calendar_features(long_df)
    featured = add_lag_features(featured)
    featured = add_forecast_target(featured)

    rows_before_filter = len(featured)

    missing_lag = featured["flow_lag_1h"].isna()
    missing_target = featured["target_speed"].isna()

    n_dropped_lag_only = int((missing_lag & ~missing_target).sum())
    n_dropped_target_only = int((missing_target & ~missing_lag).sum())
    n_dropped_both = int((missing_lag & missing_target).sum())

    trainable = featured[~(missing_lag | missing_target)].sort_values("timestamp").reset_index(drop=True)

    stats["rows_before_filter"] = rows_before_filter
    stats["dropped_lag_incomplete_only"] = n_dropped_lag_only
    stats["dropped_no_target_only"] = n_dropped_target_only
    stats["dropped_both_lag_and_target"] = n_dropped_both
    stats["trainable_rows"] = len(trainable)

    split_indices = compute_timestamp_aligned_split(trainable)

    trainable, free_flow_thresholds = add_congestion_label(trainable, split_indices["train_end_idx"])

    stats["trainable_memory_bytes"] = int(trainable.memory_usage(deep=True).sum())
    stats["elapsed_seconds"] = round(time.time() - t_start, 2)
    stats["n_sensors_present"] = int(trainable["sensor_id"].nunique())

    if verbose:
        print(f"Raw shape: {stats['raw_shape']}")
        print(f"Precision check (float64->float32 max abs diff): {stats['precision_check']}")
        print(f"Long-format rows: {stats['long_df_rows']:,}  memory: {stats['long_df_memory_bytes']/1e6:.2f} MB")
        print(f"Rows before filtering: {rows_before_filter:,}")
        print(f"  Dropped (incomplete lag history only): {n_dropped_lag_only:,}")
        print(f"  Dropped (no valid T+1h target only): {n_dropped_target_only:,}")
        print(f"  Dropped (both): {n_dropped_both:,}")
        print(f"Trainable rows: {stats['trainable_rows']:,}")
        print(f"Trainable dataframe memory: {stats['trainable_memory_bytes']/1e6:.2f} MB")
        print(f"Sensors present in trainable set: {stats['n_sensors_present']} (expected 170)")
        print(f"Split indices (timestamp-aligned): {split_indices}")
        print(f"Elapsed: {stats['elapsed_seconds']}s")

    return trainable, free_flow_thresholds, split_indices, stats


if __name__ == "__main__":
    df, thresholds, split_idx, stats = run()
    print("\ntarget_congestion_1h distribution:")
    print(df["target_congestion_1h"].value_counts())
    print("\nDistribution as %:")
    print((df["target_congestion_1h"].value_counts(normalize=True) * 100).round(2))
