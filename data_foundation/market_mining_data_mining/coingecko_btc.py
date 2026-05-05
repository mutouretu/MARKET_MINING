from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

COINGECKO_BTC_MARKET_CHART_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range"
)
REQUEST_HEADERS = {"accept": "application/json", "User-Agent": "market_mining/0.1"}


class CoinGeckoBtcError(ValueError):
    """Raised when CoinGecko BTC market data cannot be fetched or parsed."""


def fetch_btc_market_chart(
    start_date: str = "2020-01-01",
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch BTC price, market cap, and volume from CoinGecko."""

    start_ts = _date_to_unix(start_date)
    end_ts = _date_to_unix(end_date) if end_date else int(pd.Timestamp.now(tz="UTC").timestamp())
    params = {"vs_currency": "usd", "from": start_ts, "to": end_ts}
    try:
        response = requests.get(
            COINGECKO_BTC_MARKET_CHART_URL,
            params=params,
            timeout=30,
            headers=REQUEST_HEADERS,
        )
        if response.status_code in {400, 401} and "10012" in response.text:
            fallback_start = int(
                (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=360)).timestamp()
            )
            print(
                "Warning: CoinGecko public API limits range queries to the past 365 days; "
                "retrying with the earliest allowed public range."
            )
            params["from"] = fallback_start
            response = requests.get(
                COINGECKO_BTC_MARKET_CHART_URL,
                params=params,
                timeout=30,
                headers=REQUEST_HEADERS,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "unknown")
        raise CoinGeckoBtcError(
            f"CoinGecko BTC market chart request failed: {exc.__class__.__name__} "
            f"(status={status})"
        ) from None
    payload = response.json()
    if not isinstance(payload, dict):
        raise CoinGeckoBtcError("CoinGecko BTC response is not a JSON object.")
    return payload


def parse_btc_market_chart(raw: dict[str, Any]) -> pd.DataFrame:
    """Parse CoinGecko market_chart/range response into daily BTC market data."""

    price_df = _parse_series(raw.get("prices", []), "btc_price")
    market_cap_df = _parse_series(raw.get("market_caps", []), "btc_market_cap")
    volume_df = _parse_series(raw.get("total_volumes", []), "btc_volume")

    frames = [frame for frame in [price_df, market_cap_df, volume_df] if not frame.empty]
    if not frames:
        raise CoinGeckoBtcError("CoinGecko BTC response has no parseable market data.")

    output = frames[0]
    for frame in frames[1:]:
        output = output.merge(frame, on="date", how="outer")
    output = output.sort_values("date").reset_index(drop=True)
    for column in ["btc_price", "btc_market_cap", "btc_volume"]:
        if column not in output.columns:
            output[column] = pd.NA
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output[["date", "btc_price", "btc_market_cap", "btc_volume"]]


def save_json(data: Any, output: Path) -> Path:
    """Save raw JSON payload to disk."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return output


def load_json(path: Path) -> Any:
    """Load raw JSON payload from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def save_btc_market_daily(data: pd.DataFrame, output: Path) -> Path:
    """Save parsed BTC market data to CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output, index=False)
    return output


def _parse_series(values: Any, column: str) -> pd.DataFrame:
    if not isinstance(values, list):
        return pd.DataFrame(columns=["date", column])
    rows = []
    for item in values:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        timestamp_ms, value = item[0], item[1]
        date = pd.to_datetime(timestamp_ms, unit="ms", errors="coerce")
        if pd.isna(date):
            continue
        rows.append({"date": date.normalize(), column: _to_float(value)})
    if not rows:
        return pd.DataFrame(columns=["date", column])
    output = pd.DataFrame(rows)
    output = output.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return output.reset_index(drop=True)


def _date_to_unix(value: str) -> int:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise CoinGeckoBtcError(f"Invalid date: {value}")
    return int(parsed.timestamp())


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
