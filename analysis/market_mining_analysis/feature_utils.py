from __future__ import annotations

import pandas as pd


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Calculate a rolling z-score with a conservative minimum window."""

    rolling_mean = series.rolling(window=window, min_periods=max(2, window // 2)).mean()
    rolling_std = series.rolling(window=window, min_periods=max(2, window // 2)).std()
    return (series - rolling_mean) / rolling_std.replace(0, pd.NA)


def absolute_change(series: pd.Series, periods: int) -> pd.Series:
    """Calculate absolute change over a fixed number of periods."""

    return series - series.shift(periods)


def percent_change(series: pd.Series, periods: int) -> pd.Series:
    """Calculate percent change over a fixed number of periods."""

    return series.pct_change(periods=periods, fill_method=None)
