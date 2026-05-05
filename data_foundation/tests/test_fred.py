from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import requests

from market_mining_data_mining.sources.fred import (
    FredApiError,
    FredClient,
    get_fred_api_key,
    save_fred_csv,
)


class FakeResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "observations": [
                {
                    "realtime_start": "2020-01-01",
                    "realtime_end": "2020-01-01",
                    "date": "2020-01-01",
                    "value": "1.55",
                },
                {
                    "realtime_start": "2020-01-02",
                    "realtime_end": "2020-01-02",
                    "date": "2020-01-02",
                    "value": ".",
                },
            ]
        }


class FakeSession:
    def __init__(self) -> None:
        self.params: dict[str, Any] | None = None

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
        self.params = params
        assert "fred/series/observations" in url
        assert timeout == 30
        return FakeResponse()


class FailingSession:
    def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
        raise requests.ConnectionError("connection failed with sensitive request details")


def test_get_fred_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    assert get_fred_api_key() == "test-key"


def test_get_fred_api_key_requires_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FRED API key"):
        get_fred_api_key()


def test_fetch_series_normalizes_observations() -> None:
    session = FakeSession()
    client = FredClient(api_key="test-key", session=session)  # type: ignore[arg-type]

    data = client.fetch_series(series_id="DFF", start="2020-01-01", end="2020-01-02")

    assert session.params == {
        "series_id": "DFF",
        "api_key": "test-key",
        "file_type": "json",
        "observation_start": "2020-01-01",
        "observation_end": "2020-01-02",
    }
    assert list(data.columns) == [
        "date",
        "series_id",
        "value",
        "source",
        "realtime_start",
        "realtime_end",
        "created_at",
    ]
    assert data.loc[0, "value"] == 1.55
    assert pd.isna(data.loc[1, "value"])
    assert data.loc[0, "series_id"] == "DFF"
    assert data.loc[0, "source"] == "fred"


def test_fetch_series_sanitizes_request_errors() -> None:
    client = FredClient(api_key="test-key", session=FailingSession())  # type: ignore[arg-type]

    with pytest.raises(FredApiError) as exc_info:
        client.fetch_series(series_id="DFF")

    error_message = str(exc_info.value)
    assert "DFF" in error_message
    assert "test-key" not in error_message
    assert "sensitive request details" not in error_message


def test_save_fred_csv(tmp_path: Path) -> None:
    data = pd.DataFrame(
        [{"date": "2020-01-01", "series_id": "DFF", "value": 1.55, "source": "fred"}]
    )

    output = save_fred_csv(data, tmp_path / "raw" / "DFF.csv")

    saved = pd.read_csv(output)
    assert output.exists()
    assert list(saved.columns) == ["date", "series_id", "value", "source"]


def test_save_fred_csv_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    data = pd.DataFrame(
        [{"date": "2020-01-01", "series_id": "DFF", "value": 1.55, "source": "fred"}]
    )
    output_path = tmp_path / "raw" / "DFF.csv"

    first_output = save_fred_csv(data, output_path)
    second_output = save_fred_csv(data, output_path)

    assert first_output == output_path
    assert second_output != output_path
    assert second_output.exists()
