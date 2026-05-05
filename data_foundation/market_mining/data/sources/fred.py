"""Compatibility exports for the FRED mining source."""

from market_mining_data_mining.sources.fred import (
    FRED_OBSERVATIONS_URL,
    FRED_SOURCE,
    FredApiError,
    FredClient,
    fetch_fred_batch_to_csv,
    fetch_fred_series_to_csv,
    get_fred_api_key,
    save_fred_csv,
)

__all__ = [
    "FRED_OBSERVATIONS_URL",
    "FRED_SOURCE",
    "FredApiError",
    "FredClient",
    "fetch_fred_batch_to_csv",
    "fetch_fred_series_to_csv",
    "get_fred_api_key",
    "save_fred_csv",
]
