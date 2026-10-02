"""
Module 3 — Step 1: cleaning.

Most of this is a second line of defense — Module 2's ingestion pipeline already
rejects impossible speeds/coordinates at upload time. This module exists because:
1. Historical/bulk-loaded data may bypass the API (e.g. loaded directly for training)
2. "Handle missing values" and "handle outliers" are genuinely preprocessing concerns,
   not ingestion concerns — a value can be *valid* but still be an outlier worth flagging.
"""
import pandas as pd

# Thresholds are explained, not arbitrary — matches the same bounds enforced in
# backend/app/schemas/traffic.py, kept here so this module works standalone on
# any dataset, not only ones that already passed through the API.
MAX_PLAUSIBLE_SPEED_KMH = 200
MAX_PLAUSIBLE_VEHICLE_COUNT = 20000


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """A duplicate = same road_id + timestamp (mirrors the DB unique constraint)."""
    before = len(df)
    df = df.drop_duplicates(subset=["road_id", "timestamp"], keep="first")
    removed = before - len(df)
    if removed:
        print(f"[clean] removed {removed} duplicate rows")
    return df


def detect_invalid_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)
    invalid = (~mask).sum()
    if invalid:
        print(f"[clean] dropping {invalid} rows with invalid coordinates")
    return df[mask].copy()


def detect_impossible_speeds(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["average_speed"].between(0, MAX_PLAUSIBLE_SPEED_KMH)
    invalid = (~mask).sum()
    if invalid:
        print(f"[clean] dropping {invalid} rows with impossible average_speed")
    return df[mask].copy()


def detect_impossible_vehicle_counts(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["vehicle_count"].between(0, MAX_PLAUSIBLE_VEHICLE_COUNT)
    invalid = (~mask).sum()
    if invalid:
        print(f"[clean] dropping {invalid} rows with impossible vehicle_count")
    return df[mask].copy()


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Core fields (road_id, timestamp, vehicle_count, average_speed, lat/lng) are
    NOT NULL at the DB level, so missingness only affects optional fields.
    Strategy, applied explicitly rather than silently:
    - weather_condition: fill with "unknown" (categorical, safe default)
    - temperature / rainfall: leave as NaN — imputing weather numerically without
      a real weather source would be fabricating data, which the project spec
      explicitly forbids. Downstream feature engineering must handle NaN, not hide it.
    """
    df = df.copy()
    if "weather_condition" in df.columns:
        df["weather_condition"] = df["weather_condition"].fillna("unknown")
    return df


def handle_outliers_iqr(df: pd.DataFrame, column: str, group_col: str = "road_id") -> pd.DataFrame:
    """
    Flags (does not silently drop) statistical outliers per road using the IQR method,
    since "normal" speed/volume varies hugely by road. Adds a `<column>_is_outlier` flag
    column so the modeling step can decide whether to exclude or downweight them —
    outliers in traffic data are often real events (accidents, festivals), not noise.
    """
    df = df.copy()
    flag_col = f"{column}_is_outlier"
    df[flag_col] = False

    for road, group in df.groupby(group_col):
        q1, q3 = group[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_idx = group[(group[column] < lower) | (group[column] > upper)].index
        df.loc[outlier_idx, flag_col] = True

    n_outliers = df[flag_col].sum()
    if n_outliers:
        print(f"[clean] flagged {n_outliers} statistical outliers in '{column}' (kept, not dropped)")
    return df


def clean_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Runs every cleaning step in order. This is what Phase orchestration calls."""
    df = remove_duplicates(df)
    df = detect_invalid_coordinates(df)
    df = detect_impossible_speeds(df)
    df = detect_impossible_vehicle_counts(df)
    df = handle_missing_values(df)
    df = handle_outliers_iqr(df, column="vehicle_count")
    df = handle_outliers_iqr(df, column="average_speed")
    return df.reset_index(drop=True)
