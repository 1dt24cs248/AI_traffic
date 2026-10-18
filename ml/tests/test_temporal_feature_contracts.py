"""Regression tests for the separate application and Metro calendar contracts."""
from datetime import datetime

import pandas as pd
import pytest

from ml.preprocessing.features import add_temporal_features as add_application_temporal_features
from ml.preprocessing.real_dataset_features import add_temporal_features as add_metro_temporal_features


@pytest.mark.parametrize(
    "hour,expected",
    [(6, 0), (7, 1), (9, 1), (10, 0), (16, 0), (17, 1), (19, 1), (20, 0)],
)
def test_application_calendar_rush_hour_weekday_boundaries(hour, expected):
    timestamps = pd.to_datetime([datetime(2026, 1, 5, hour)])  # Monday
    result = add_application_temporal_features(pd.DataFrame({"timestamp": timestamps}))
    assert result.loc[0, "is_rush_hour"] == expected


@pytest.mark.parametrize("day", [5, 6])
@pytest.mark.parametrize("hour", [7, 9, 17, 19])
def test_application_calendar_rush_hour_is_false_on_weekends(day, hour):
    timestamp = datetime(2026, 1, 5, hour) + pd.Timedelta(days=day)
    result = add_application_temporal_features(pd.DataFrame({"timestamp": [timestamp]}))
    assert result.loc[0, "is_weekend"] == 1
    assert result.loc[0, "is_rush_hour"] == 0


@pytest.mark.parametrize(
    "hour,expected",
    [(6, 0), (7, 1), (9, 1), (10, 0), (15, 0), (16, 1), (18, 1), (19, 0)],
)
def test_metro_pipeline_keeps_its_dataset_specific_calendar_window(hour, expected):
    timestamp = pd.to_datetime([datetime(2017, 1, 2, hour)])  # Monday
    result = add_metro_temporal_features(
        pd.DataFrame({"date_time": timestamp, "holiday": ["None"]})
    )
    assert result.loc[0, "is_rush_hour"] == expected
