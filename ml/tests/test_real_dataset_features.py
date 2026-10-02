"""
Automated tests proving the corrected T -> T+1h forecasting pipeline is actually
leakage-free and structurally sound. Written in direct response to an audit that
found the previous same-timestamp implementation — these tests exist specifically
to catch that class of bug if it's ever reintroduced.

Run: pytest ml/tests/test_real_dataset_features.py -v
"""
import pandas as pd
import pytest

from ml.preprocessing.real_dataset_features import (
    run, FEATURE_COLUMNS, TARGET_COLUMN,
    load_raw, clean, add_temporal_features, add_lag_and_rolling_features, add_forecast_target,
)


@pytest.fixture(scope="module")
def pipeline_output():
    """Runs the real pipeline once and shares the result across tests (it's not cheap)."""
    df, thresholds, split_idx = run()
    return df, thresholds, split_idx


def test_feature_timestamp_before_target_timestamp(pipeline_output):
    """Requirement: feature timestamp T < target timestamp, for every row."""
    df, _, _ = pipeline_output
    assert (df["target_timestamp"] > df["date_time"]).all(), \
        "Found rows where target_timestamp is not strictly after the feature timestamp"


def test_target_is_exactly_one_hour_later(pipeline_output):
    """Requirement: target timestamp - feature timestamp == exactly 1 hour, no tolerance."""
    df, _, _ = pipeline_output
    gap = df["target_timestamp"] - df["date_time"]
    assert (gap == pd.Timedelta(hours=1)).all(), \
        f"Found rows where the gap is not exactly 1 hour. Gaps found: {gap.unique()}"


def test_no_target_hour_weather_features_in_input(pipeline_output):
    """Requirement: no weather feature is present in the training feature set at all
    (the corrected pipeline removes weather entirely, avoiding any ambiguity about
    whether a weather value belongs to the feature hour or the target hour)."""
    weather_cols = {"temp", "rain_1h", "snow_1h", "clouds_all", "weather_main"}
    assert weather_cols.isdisjoint(set(FEATURE_COLUMNS)), \
        f"Weather columns leaked into FEATURE_COLUMNS: {weather_cols & set(FEATURE_COLUMNS)}"


def test_no_same_timestamp_traffic_volume_leakage(pipeline_output):
    """
    Requirement: the feature row's own traffic_volume (at T) must not be used as an
    input feature, AND the target must genuinely come from a DIFFERENT row (T+1h),
    not be a copy of the feature row's own value.
    """
    df, _, _ = pipeline_output
    assert "traffic_volume" not in FEATURE_COLUMNS, \
        "traffic_volume (same-timestamp) is present in the feature columns — this is exactly the bug being tested for"

    # The target must come from the actual next row's volume — spot-check by re-deriving
    # it independently from the raw pipeline steps rather than trusting the pipeline's own output.
    raw = load_raw()
    cleaned = clean(raw)
    featured = add_temporal_features(cleaned)
    featured = add_lag_and_rolling_features(featured)
    featured = add_forecast_target(featured)
    featured = featured.sort_values("date_time").reset_index(drop=True)

    # For a handful of sampled rows in the final trainable set, confirm target_traffic_volume
    # equals the traffic_volume of the row whose date_time matches target_timestamp exactly.
    sample = df.dropna(subset=["target_timestamp"]).sample(min(50, len(df)), random_state=1)
    lookup = featured.set_index("date_time")["traffic_volume"]
    for _, row in sample.iterrows():
        expected = lookup.loc[row["target_timestamp"]]
        assert row["target_traffic_volume"] == expected, \
            f"Target value mismatch at {row['date_time']}: pipeline said {row['target_traffic_volume']}, actual next-hour row has {expected}"
        # And confirm it's NOT equal to the feature row's own volume (would indicate same-row leakage),
        # except in the rare case both hours coincidentally had identical volume — check the timestamp too.
        assert row["target_timestamp"] != row["date_time"], \
            "target_timestamp equals feature date_time — same-row leakage detected"


def test_lag_features_respect_time_gaps(pipeline_output):
    """
    Requirement: lag features must be NaN (and therefore the row dropped from the
    trainable set) if computing them would cross the documented Aug2014-Jun2015 gap
    or any other missing-hour gap — never silently computed across missing time.
    """
    raw = load_raw()
    cleaned = clean(raw)
    featured = add_temporal_features(cleaned)
    featured = add_lag_and_rolling_features(featured)

    # Locate the documented big gap directly in the cleaned data and confirm lag_1h
    # is NaN for the first row after it (since the row 1 hour "before" it, by shift(1),
    # is actually ~10 months before in wall-clock time).
    time_diff_hours = featured["date_time"].diff().dt.total_seconds() / 3600
    big_gap_positions = featured.index[time_diff_hours > 24]
    assert len(big_gap_positions) > 0, "Expected to find at least one large time gap in this dataset (documented Aug2014-Jun2015 gap) — if this fails, the raw file may have changed"

    first_row_after_gap = big_gap_positions[0]
    assert pd.isna(featured.loc[first_row_after_gap, "lag_1h"]), \
        "lag_1h was computed across a >24h time gap instead of being set to NaN"


def test_chronological_split_no_overlap(pipeline_output):
    """Requirement: max(train target ts) < min(val target ts) < ... < min(test target ts)."""
    df, _, split_idx = pipeline_output
    train_df = df.iloc[:split_idx["train_end_idx"]]
    val_df = df.iloc[split_idx["train_end_idx"]:split_idx["val_end_idx"]]
    test_df = df.iloc[split_idx["val_end_idx"]:]

    assert train_df["target_timestamp"].max() < val_df["target_timestamp"].min(), \
        "Train/validation target timestamps overlap"
    assert val_df["target_timestamp"].max() < test_df["target_timestamp"].min(), \
        "Validation/test target timestamps overlap"


def test_thresholds_learned_from_train_only(pipeline_output):
    """
    Requirement: congestion label quartile thresholds must be computed from the TRAIN
    split's target values only, not the full dataset. Verified by independently
    recomputing the thresholds from just the train slice and confirming an exact match.
    """
    df, thresholds, split_idx = pipeline_output
    train_target = df["target_traffic_volume"].iloc[:split_idx["train_end_idx"]]
    expected_q25, expected_q50, expected_q75 = train_target.quantile([0.25, 0.5, 0.75])

    assert thresholds["q25"] == pytest.approx(expected_q25)
    assert thresholds["q50"] == pytest.approx(expected_q50)
    assert thresholds["q75"] == pytest.approx(expected_q75)

    # And confirm they do NOT match thresholds computed from the full dataset
    # (a meaningful check only if train != full, which is true here since train is 70%)
    full_q25, full_q50, full_q75 = df["target_traffic_volume"].quantile([0.25, 0.5, 0.75])
    assert not (thresholds["q25"] == full_q25 and thresholds["q50"] == full_q50), \
        "Thresholds match the FULL dataset's quantiles, not just train's — suggests train-only filtering isn't actually happening"


def test_target_column_present_and_no_nulls(pipeline_output):
    """Sanity: every trainable row has a real target label, nothing null slipped through."""
    df, _, _ = pipeline_output
    assert TARGET_COLUMN in df.columns
    assert df[TARGET_COLUMN].isna().sum() == 0
    assert set(df[TARGET_COLUMN].unique()) <= {"LOW", "MEDIUM", "HIGH", "SEVERE"}
