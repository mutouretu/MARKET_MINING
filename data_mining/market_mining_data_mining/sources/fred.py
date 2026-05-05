from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SOURCE = "fred"


class FredApiError(RuntimeError):
    """Raised when the FRED API request fails."""


def get_fred_api_key(api_key: str | None = None, api_key_env: str = "FRED_API_KEY") -> str:
    """Return the FRED API key from an explicit value or environment variable."""

    resolved_api_key = api_key or os.getenv(api_key_env)
    if not resolved_api_key:
        msg = f"FRED API key is required. Set {api_key_env} or pass api_key explicitly."
        raise ValueError(msg)
    return resolved_api_key


def _parse_fred_value(value: str | None) -> float | None:
    if value in (None, "."):
        return None
    return float(value)


class FredClient:
    """Minimal FRED series observations client."""

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env: str = "FRED_API_KEY",
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = get_fred_api_key(api_key=api_key, api_key_env=api_key_env)
        self.session = session or requests.Session()

    def fetch_series(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Fetch one FRED series and return normalized raw observations."""

        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
        }
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        try:
            response = self.session.get(FRED_OBSERVATIONS_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            msg = f"FRED request failed for {series_id}: {exc.__class__.__name__}"
            raise FredApiError(msg) from None
        if response.status_code != 200:
            msg = f"FRED request failed for {series_id}: HTTP {response.status_code}"
            raise FredApiError(msg)

        payload = response.json()
        if "error_code" in payload:
            msg = f"FRED request failed for {series_id}: {payload.get('error_message')}"
            raise FredApiError(msg)

        created_at = datetime.now(timezone.utc).isoformat()
        observations = payload.get("observations", [])
        rows = [
            {
                "date": item.get("date"),
                "series_id": series_id,
                "value": _parse_fred_value(item.get("value")),
                "source": FRED_SOURCE,
                "realtime_start": item.get("realtime_start"),
                "realtime_end": item.get("realtime_end"),
                "created_at": created_at,
            }
            for item in observations
        ]
        return pd.DataFrame(
            rows,
            columns=[
                "date",
                "series_id",
                "value",
                "source",
                "realtime_start",
                "realtime_end",
                "created_at",
            ],
        )


def save_fred_csv(data: pd.DataFrame, output: str | Path) -> Path:
    """Save normalized FRED observations to CSV without overwriting existing files."""

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_path = _next_available_path(output_path)
    data.to_csv(target_path, index=False)
    return target_path


def _next_available_path(output_path: Path) -> Path:
    if not output_path.exists():
        return output_path

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = output_path.with_name(
            f"{output_path.stem}_{timestamp}_{counter}{output_path.suffix}"
        )
        counter += 1
    return candidate


def fetch_fred_series_to_csv(
    series_id: str,
    output: str | Path,
    start: str | None = None,
    end: str | None = None,
    api_key: str | None = None,
    api_key_env: str = "FRED_API_KEY",
) -> Path:
    """Fetch one FRED series and save it as a raw CSV file."""

    client = FredClient(api_key=api_key, api_key_env=api_key_env)
    data = client.fetch_series(series_id=series_id, start=start, end=end)
    return save_fred_csv(data, output)


def fetch_fred_batch_to_csv(
    series_ids: list[str],
    output_dir: str | Path,
    start: str | None = None,
    end: str | None = None,
    api_key: str | None = None,
    api_key_env: str = "FRED_API_KEY",
) -> list[Path]:
    """Fetch multiple FRED series and save one CSV per series."""

    client = FredClient(api_key=api_key, api_key_env=api_key_env)
    output_path = Path(output_dir)
    saved_paths: list[Path] = []
    for series_id in series_ids:
        data = client.fetch_series(series_id=series_id, start=start, end=end)
        saved_paths.append(save_fred_csv(data, output_path / f"{series_id}.csv"))
    return saved_paths
