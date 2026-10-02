"""
Module 3 — Step 3: time-respecting train/validation/test split.

WHY NOT A RANDOM SHUFFLE (Section 3 explicit requirement):
This is a forecasting problem — the model predicts FUTURE congestion from PAST
features (lag values, rolling averages). If we randomly shuffled rows before
splitting, some training rows would have timestamps AFTER some test rows. The
model could then implicitly learn from data that, in a real deployment, would
not exist yet at prediction time. That's data leakage, and it inflates evaluation
metrics in a way that would not hold up in the actual viva demo or in production.

METHOD: chronological split.
Sort all data by timestamp, then cut by time — not by shuffled row index:
    earliest 70% of the time range -> train
    next 15%                       -> validation
    latest 15%                     -> test

This is done GLOBALLY across all roads by timestamp (not per-road), so the
validation/test sets represent "the future" relative to training for the whole
dataset at once — matching how the model will actually be used at deployment time.
"""
import pandas as pd


def time_based_split(
    df: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assert 0 < train_frac < 1 and 0 < val_frac < 1 and train_frac + val_frac < 1

    df = df.sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    return train_df, val_df, test_df


def split_summary(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    def bounds(d):
        if len(d) == 0:
            return None, None
        return str(d["timestamp"].min()), str(d["timestamp"].max())

    return {
        "train": {"rows": len(train_df), "range": bounds(train_df)},
        "val": {"rows": len(val_df), "range": bounds(val_df)},
        "test": {"rows": len(test_df), "range": bounds(test_df)},
    }
