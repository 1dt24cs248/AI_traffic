"""
Module 3 — Step 2: feature engineering.

Includes the congestion-labeling methodology required by Module 5, defined here
(not invented later) so it's reproducible and applied identically to train/val/test.

CONGESTION LABEL METHODOLOGY (explained, not arbitrary — Section 5 requirement):
We use relative speed reduction against each road's own free-flow speed, which is
the standard basis for Level-of-Service style congestion measures in traffic
engineering (a road's "normal" speed varies hugely by road type, so an absolute
km/h threshold would misclassify a busy arterial and a residential street the same way).

free_flow_speed(road) = 95th percentile of that road's own observed average_speed.
Using the 95th percentile instead of the max makes the baseline robust to a single
anomalous fast reading, while still representing "close to free-flowing conditions".

speed_ratio = average_speed / free_flow_speed(road)

    speed_ratio >= 0.75  -> LOW      (near free-flow)
    0.50 <= ratio < 0.75 -> MEDIUM   (noticeable slowdown)
    0.25 <= ratio < 0.50 -> HIGH     (major slowdown)
    ratio < 0.25         -> SEVERE   (near-stationary)

These cut points follow the same relative-speed logic used in common Level-of-Service
(LOS) traffic classifications (LOS A-F bands drop in similar proportional steps).
This is a defensible convention, not a claim of precise real-world calibration —
if a dataset later ships its own congestion labels, prefer those over this derived one.
"""
import pandas as pd
import numpy as np

CONGESTION_BINS = [-np.inf, 0.25, 0.50, 0.75, np.inf]
CONGESTION_LABELS = ["SEVERE", "HIGH", "MEDIUM", "LOW"]


def add_congestion_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    free_flow = df.groupby("road_id")["average_speed"].transform(lambda s: s.quantile(0.95))
    # Guard against a road with free_flow==0 (shouldn't happen after cleaning, but be defensive)
    free_flow = free_flow.replace(0, np.nan)
    df["speed_ratio"] = df["average_speed"] / free_flow
    df["congestion_level"] = pd.cut(
        df["speed_ratio"], bins=CONGESTION_BINS, labels=CONGESTION_LABELS
    )
    return df


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ts = pd.to_datetime(df["timestamp"])
    df["hour"] = ts.dt.hour
    df["minute"] = ts.dt.minute
    df["day_of_week"] = ts.dt.dayofweek  # 0=Monday
    df["month"] = ts.dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    # Rush hour: 7-10am and 5-8pm on weekdays — a stated, adjustable definition,
    # not left implicit. Tune from actual peak-hour analysis in Module 4 if it differs.
    df["is_rush_hour"] = (
        (~df["is_weekend"].astype(bool))
        & (df["hour"].between(7, 9) | df["hour"].between(17, 19))
    ).astype(int)
    return df


def add_lag_and_rolling_features(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    Lag/rolling features are computed PER ROAD, sorted by time, using only past values —
    this is what prevents future information leaking backward (Section 3 requirement).
    `window` = number of prior time steps (e.g. window=3 at 15-min intervals = 45 min).
    """
    df = df.sort_values(["road_id", "timestamp"]).copy()
    grp = df.groupby("road_id")

    df["previous_vehicle_count"] = grp["vehicle_count"].shift(1)
    df["previous_speed"] = grp["average_speed"].shift(1)
    df["previous_congestion_level"] = grp["congestion_level"].shift(1)

    # shift(1) before rolling ensures the current row's own value is never included
    # in its own rolling average — another leakage guard.
    df["rolling_average_speed"] = (
        grp["average_speed"].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    )
    df["rolling_average_vehicle_count"] = (
        grp["vehicle_count"].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    )
    return df


def feature_engineering_pipeline(df: pd.DataFrame, lag_window: int = 3) -> pd.DataFrame:
    df = add_congestion_label(df)
    df = add_temporal_features(df)
    df = add_lag_and_rolling_features(df, window=lag_window)
    return df.reset_index(drop=True)
