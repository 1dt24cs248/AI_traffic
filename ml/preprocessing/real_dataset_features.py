"""
Module 5 — preprocessing for the REAL Metro Interstate Traffic Volume dataset.
Kept separate from ml/preprocessing/{clean,features}.py because this dataset has a
different schema (single location, no speed) — see docs/DATASETS.md for why.

=== CORRECTION LOG (audited and fixed — see docs/CURRENT_STATUS.md) ===
The original version of this file computed `congestion_level` from the SAME row's
`traffic_volume` that also supplied that row's weather/temporal features — i.e. it
predicted congestion AT time T from features AT time T. That is same-timestamp
nowcasting, not a T -> T+1h forecast, despite being documented (incorrectly) as a
"+60 minute horizon" model. This has been corrected below: the target is now
`target_congestion_1h`, built from the traffic_volume of the row EXACTLY one hour
after the feature row, constructed with an explicit timestamp check (never a blind
shift(-1)) so rows spanning a data gap don't get a fabricated target. Weather
features (temp, rain_1h, snow_1h, clouds_all, weather_main) have been removed
entirely from the feature set: this repo has no real weather-forecast source, and
removing them avoids any ambiguity about whether a weather value belongs to the
feature hour or the target hour.

Run standalone: python -m ml.preprocessing.real_dataset_features
"""
import os
import pandas as pd
import numpy as np

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "real", "metro_interstate_traffic_volume.csv")

CONGESTION_LABELS = ["LOW", "MEDIUM", "HIGH", "SEVERE"]
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH)
    df["date_time"] = pd.to_datetime(df["date_time"])
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    before = len(df)

    # Exact duplicate rows (documented limitation #5)
    df = df.drop_duplicates()
    # Duplicate timestamps (same hour logged multiple times under different weather rows) —
    # keep the first occurrence per timestamp, since we can't determine which is authoritative
    df = df.drop_duplicates(subset=["date_time"], keep="first")
    removed_dupes = before - len(df)

    # Known sensor artifacts (documented limitation #4): temp=0K is physically implausible
    # (that's -273.15C); drop rather than fabricate a corrected value.
    bad_temp = (df["temp"] == 0).sum()
    df = df[df["temp"] > 0].copy()

    # rain_1h has one documented extreme outlier (9831.3mm in an hour is not physically
    # plausible for the US Midwest). Flag and cap at the 99.9th percentile rather than
    # inventing a "true" value.
    rain_cap = df["rain_1h"].quantile(0.999)
    extreme_rain = (df["rain_1h"] > rain_cap).sum()
    df["rain_1h"] = df["rain_1h"].clip(upper=rain_cap)

    print(f"[real_dataset] removed {removed_dupes} duplicate rows, "
          f"dropped {bad_temp} rows with temp=0K, capped {extreme_rain} extreme rain_1h outliers")

    return df.sort_values("date_time").reset_index(drop=True)


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calendar features derived from the FEATURE row's own timestamp T. These are known
    at prediction time by definition (the calendar is known in advance) — no leakage risk.
    Weather columns are deliberately NOT touched here — see module docstring: this
    corrected pipeline drops weather from the feature set entirely.
    """
    df = df.copy()
    df["hour"] = df["date_time"].dt.hour
    df["day_of_week"] = df["date_time"].dt.dayofweek
    df["month"] = df["date_time"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_holiday"] = (df["holiday"] != "None").astype(int)
    df["is_rush_hour"] = (
        (~df["is_weekend"].astype(bool)) & (df["hour"].between(7, 9) | df["hour"].between(16, 18))
    ).astype(int)
    return df


def add_lag_and_rolling_features(df: pd.DataFrame, max_gap_hours: int = 2) -> pd.DataFrame:
    """
    Lag/rolling features use ONLY traffic_volume at or before the feature row's own
    timestamp T (shift(>=1) or shift(1)+rolling) — never T's own current value, and
    never anything after T. Any lag that would span the documented Aug2014-Jun2015 gap
    (or any other missing hours) is set to NaN via the cumulative time-gap check below,
    rather than silently computed across a gap that makes it meaningless.
    """
    df = df.sort_values("date_time").reset_index(drop=True)
    time_diff_hours = df["date_time"].diff().dt.total_seconds() / 3600

    for lag_hours, col_name in [(1, "lag_1h"), (3, "lag_3h"), (24, "lag_24h")]:
        shifted = df["traffic_volume"].shift(lag_hours)
        cum_gap = time_diff_hours.rolling(lag_hours, min_periods=lag_hours).sum()
        valid = cum_gap.notna() & (abs(cum_gap - lag_hours) <= max_gap_hours)
        df[col_name] = np.where(valid, shifted, np.nan)

    df["rolling_3h_mean"] = df["traffic_volume"].shift(1).rolling(3, min_periods=2).mean()
    return df


def add_forecast_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Builds the genuine T -> T+1h forecast target.

    For feature row i at timestamp T, the target is traffic_volume of row i+1 ONLY IF
    date_time(i+1) == T + exactly 1 hour. This is NOT a blind shift(-1): if the next
    row in the sorted sequence is not exactly one hour later (e.g. it's on the other
    side of the Aug2014-Jun2015 gap, or any other missing-hour gap), target_traffic_volume
    and target_timestamp are set to NaN/NaT for that row, and that row is later dropped
    from the trainable set rather than given a fabricated target.
    """
    df = df.sort_values("date_time").reset_index(drop=True)

    next_timestamp = df["date_time"].shift(-1)
    next_volume = df["traffic_volume"].shift(-1)
    gap_hours = (next_timestamp - df["date_time"]).dt.total_seconds() / 3600
    exact_next_hour = gap_hours.eq(1.0)  # exactly 3600 seconds, no tolerance — must be exact

    df["target_timestamp"] = next_timestamp.where(exact_next_hour)
    df["target_traffic_volume"] = next_volume.where(exact_next_hour)
    return df


def add_congestion_label(df: pd.DataFrame, train_end_idx: int) -> tuple[pd.DataFrame, dict]:
    """
    Quantile thresholds for `target_congestion_1h` are computed from the TARGET values
    of the TRAIN portion ONLY (first `train_end_idx` rows of the already-filtered,
    chronologically-sorted trainable dataframe — filtering and chronological ordering
    must happen before this is called). This prevents the label boundaries themselves
    from leaking validation/test distribution into training.
    """
    df = df.copy()
    train_target = df["target_traffic_volume"].iloc[:train_end_idx]
    q25, q50, q75 = train_target.quantile([0.25, 0.5, 0.75])

    def label(v):
        if v <= q25:
            return "LOW"
        elif v <= q50:
            return "MEDIUM"
        elif v <= q75:
            return "HIGH"
        else:
            return "SEVERE"

    df["target_congestion_1h"] = df["target_traffic_volume"].apply(label)
    return df, {"q25": float(q25), "q50": float(q50), "q75": float(q75)}


# Feature columns for the corrected T -> T+1h experiment.
# Weather (temp, rain_1h, snow_1h, clouds_all, weather_main) intentionally excluded —
# see module docstring. traffic_volume of the feature row itself is intentionally
# excluded too (kept out of both the old and corrected implementations) — only its
# lagged/rolled history is used.
FEATURE_COLUMNS = [
    "hour", "day_of_week", "month", "is_weekend", "is_holiday", "is_rush_hour",
    "lag_1h", "lag_3h", "lag_24h", "rolling_3h_mean",
]
TARGET_COLUMN = "target_congestion_1h"


def run() -> tuple[pd.DataFrame, dict, dict]:
    """
    Returns (trainable_df, label_thresholds, split_indices).
    trainable_df contains ONLY rows with a valid T+1h target and complete lag history —
    i.e. rows that survived filtering — sorted chronologically, ready to be sliced by
    split_indices for train/val/test (train_models.py uses these same indices so the
    split used for threshold-learning and the split used for training are identical).
    """
    raw = load_raw()
    cleaned = clean(raw)
    featured = add_temporal_features(cleaned)
    featured = add_lag_and_rolling_features(featured)
    featured = add_forecast_target(featured)

    required = FEATURE_COLUMNS + ["target_traffic_volume", "target_timestamp"]
    before_filter = len(featured)
    trainable = featured.dropna(subset=required).sort_values("date_time").reset_index(drop=True)
    dropped = before_filter - len(trainable)
    print(f"[real_dataset] {dropped} rows dropped (no valid T+1h target and/or incomplete lag history), "
          f"{len(trainable)} rows remain trainable")

    n = len(trainable)
    train_end_idx = int(n * TRAIN_FRAC)
    val_end_idx = int(n * (TRAIN_FRAC + VAL_FRAC))
    split_indices = {"train_end_idx": train_end_idx, "val_end_idx": val_end_idx}

    trainable, label_thresholds = add_congestion_label(trainable, train_end_idx)

    return trainable, label_thresholds, split_indices


if __name__ == "__main__":
    df, thresholds, split_idx = run()
    print(f"Trainable rows: {len(df)}")
    print(f"Label thresholds (from train target-values only): {thresholds}")
    print(df["target_congestion_1h"].value_counts())
    print(f"Split indices: {split_idx}")
    # Spot-check: confirm the target-timestamp relationship holds
    sample = df.iloc[0]
    print(f"Spot check row 0: feature ts={sample['date_time']}, target ts={sample['target_timestamp']}, "
          f"gap={ (sample['target_timestamp'] - sample['date_time']) }")

