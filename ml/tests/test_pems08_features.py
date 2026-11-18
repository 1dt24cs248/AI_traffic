"""
Automated leakage/correctness tests for the PEMS08 T -> T+1h forecasting pipeline.
Mirrors the discipline of ml/tests/test_real_dataset_features.py (Metro), adapted
for PEMS08's per-sensor, dense-grid structure.

NOTE: no rolling-feature test here — rolling features were deliberately removed
from this pipeline (see pems08_features.py module docstring).

Run: pytest ml/tests/test_pems08_features.py -v
"""
import pandas as pd
import numpy as np
import pytest

from ml.preprocessing.pems08_features import (
    run, FEATURE_COLUMNS, TARGET_COLUMN, AUDIT_COLUMNS,
    load_raw, build_long_dataframe,
    DUPLICATE_SENSOR_GROUPS, N_SENSORS,
)


@pytest.fixture(scope="module")
def pipeline_output():
    df, thresholds, split_idx, stats = run(verbose=False)
    return df, thresholds, split_idx, stats


def test_target_timestamp_exactly_one_hour_later(pipeline_output):
    """Requirement: target_timestamp == timestamp + exactly 1 hour, for every row."""
    df, _, _, _ = pipeline_output
    gap = df["target_timestamp"] - df["timestamp"]
    assert (gap == pd.Timedelta(hours=1)).all(), \
        f"Found rows where the gap is not exactly 1 hour: {gap[gap != pd.Timedelta(hours=1)].unique()}"


def test_target_speed_comes_from_same_sensor_at_t_plus_12(pipeline_output):
    """Requirement: target_speed must independently be re-derivable as
    data[sensor, T+12, speed] — not assumed correct, not a cross-sensor value."""
    df, _, _, _ = pipeline_output
    raw = load_raw()
    long_df = build_long_dataframe(raw)
    lookup = long_df.set_index(["sensor_id", "timestamp"])["speed"]

    sample = df.sample(min(100, len(df)), random_state=7)
    for _, row in sample.iterrows():
        expected = lookup.loc[(row["sensor_id"], row["target_timestamp"])]
        assert abs(row["target_speed"] - expected) < 1e-3, \
            f"Mismatch at sensor {row['sensor_id']}, T={row['timestamp']}: " \
            f"target_speed={row['target_speed']}, actual sensor {row['sensor_id']} speed at T+1h={expected}"


def test_no_target_columns_in_feature_columns():
    """Requirement: target_timestamp, target_speed, target_congestion_1h must never
    appear in FEATURE_COLUMNS."""
    forbidden = set(AUDIT_COLUMNS + [TARGET_COLUMN])
    leaked = forbidden & set(FEATURE_COLUMNS)
    assert not leaked, f"Target/audit columns leaked into FEATURE_COLUMNS: {leaked}"


def test_no_rolling_features_present():
    """Requirement (final decision): rolling features must NOT be part of this
    experiment's feature set at all."""
    rolling_cols = {"rolling_flow", "rolling_speed", "rolling_occupancy"}
    assert rolling_cols.isdisjoint(set(FEATURE_COLUMNS)), \
        f"Rolling features found in FEATURE_COLUMNS despite being explicitly removed: {rolling_cols & set(FEATURE_COLUMNS)}"


def test_no_is_holiday_or_duplicate_group_id():
    """Requirement: no fabricated is_holiday, no duplicate_group_id as a feature."""
    forbidden = {"is_holiday", "duplicate_group_id"}
    assert forbidden.isdisjoint(set(FEATURE_COLUMNS)), \
        f"Forbidden columns found in FEATURE_COLUMNS: {forbidden & set(FEATURE_COLUMNS)}"


def test_lag_features_stay_within_same_sensor(pipeline_output):
    """Requirement: lag features must come from the SAME sensor's own history,
    never another sensor. Verified by re-deriving flow_lag_1h independently."""
    df, _, _, _ = pipeline_output
    raw = load_raw()
    long_df = build_long_dataframe(raw).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)

    sample = df.sample(min(30, len(df)), random_state=11)
    for _, row in sample.iterrows():
        expected_lag_timestamp = row["timestamp"] - pd.Timedelta(hours=1)
        match = long_df[(long_df["sensor_id"] == row["sensor_id"]) & (long_df["timestamp"] == expected_lag_timestamp)]
        assert len(match) == 1, f"Expected exactly one row for sensor {row['sensor_id']} at {expected_lag_timestamp}"
        expected_value = match["flow"].iloc[0]
        assert abs(row["flow_lag_1h"] - expected_value) < 1e-3, \
            f"flow_lag_1h mismatch at sensor {row['sensor_id']}, T={row['timestamp']}"


def test_chronological_split_no_overlap(pipeline_output):
    """Requirement: train timestamps < validation timestamps < test timestamps —
    strict, including at the boundary where many sensors share one timestamp."""
    df, _, split_idx, _ = pipeline_output
    train_df = df.iloc[:split_idx["train_end_idx"]]
    val_df = df.iloc[split_idx["train_end_idx"]:split_idx["val_end_idx"]]
    test_df = df.iloc[split_idx["val_end_idx"]:]

    assert train_df["timestamp"].max() < val_df["timestamp"].min(), "Train/validation timestamps overlap"
    assert val_df["timestamp"].max() < test_df["timestamp"].min(), "Validation/test timestamps overlap"


def test_thresholds_fitted_on_train_only(pipeline_output):
    """Requirement: per-sensor free_flow_speed (95th percentile) must be computed
    from TRAIN split rows only. Verified by independent recomputation."""
    df, thresholds, split_idx, _ = pipeline_output
    train_df = df.iloc[:split_idx["train_end_idx"]]

    expected = train_df.groupby("sensor_id")["speed"].quantile(0.95)
    for sensor_id, expected_val in expected.items():
        assert thresholds[sensor_id] == pytest.approx(expected_val), \
            f"Sensor {sensor_id} threshold does not match train-only recomputation"

    full_thresholds = df.groupby("sensor_id")["speed"].quantile(0.95)
    n_differ = sum(abs(thresholds[sid] - full_thresholds[sid]) > 1e-9 for sid in thresholds)
    assert n_differ > 0, "Train-only thresholds are identical to full-dataset thresholds"


def test_all_170_sensors_retained(pipeline_output):
    """Requirement: preprocessing must not silently reduce sensor count from 170,
    including the 25 duplicate sensors — documented, not removed."""
    df, _, _, _ = pipeline_output
    assert df["sensor_id"].nunique() == N_SENSORS, \
        f"Expected all {N_SENSORS} sensors present, found {df['sensor_id'].nunique()}"
    all_ids = set(range(N_SENSORS))
    present_ids = set(df["sensor_id"].unique())
    assert all_ids == present_ids, f"Missing sensor IDs: {all_ids - present_ids}"

    raw = load_raw()
    for group in DUPLICATE_SENSOR_GROUPS:
        first = raw[:, group[0], :]
        for other in group[1:]:
            assert np.array_equal(first, raw[:, other, :]), \
                f"Documented duplicate group {group} is no longer identical in the raw file"


def test_first_12_rows_per_sensor_dropped_for_incomplete_history():
    """Requirement: first 12 rows per sensor (no complete 1h lag history) excluded."""
    df, _, _, _ = run(verbose=False)
    raw = load_raw()
    long_df = build_long_dataframe(raw).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)

    sensor_0_first_timestamps = long_df[long_df["sensor_id"] == 0]["timestamp"].iloc[:12]
    trainable_sensor_0_timestamps = set(df[df["sensor_id"] == 0]["timestamp"])
    for ts in sensor_0_first_timestamps:
        assert ts not in trainable_sensor_0_timestamps, \
            f"Row at sensor 0, T={ts} should have been dropped (incomplete lag history) but is present"


def test_last_12_rows_per_sensor_dropped_for_missing_target():
    """Requirement: last 12 rows per sensor (no valid T+1h target) excluded."""
    df, _, _, _ = run(verbose=False)
    raw = load_raw()
    long_df = build_long_dataframe(raw).sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)

    sensor_0_last_timestamps = long_df[long_df["sensor_id"] == 0]["timestamp"].iloc[-12:]
    trainable_sensor_0_timestamps = set(df[df["sensor_id"] == 0]["timestamp"])
    for ts in sensor_0_last_timestamps:
        assert ts not in trainable_sensor_0_timestamps, \
            f"Row at sensor 0, T={ts} should have been dropped (no valid target) but is present"


def test_no_nan_or_inf_in_final_feature_and_target_columns(pipeline_output):
    """Sanity: trainable set must have zero NaN/Inf in feature/target columns."""
    df, _, _, _ = pipeline_output
    for col in FEATURE_COLUMNS:
        assert df[col].isna().sum() == 0, f"Found NaN in feature column {col}"
        assert np.isinf(df[col].astype(float)).sum() == 0, f"Found Inf in feature column {col}"
    assert df["target_speed"].isna().sum() == 0
    assert df["target_congestion_1h"].isna().sum() == 0
