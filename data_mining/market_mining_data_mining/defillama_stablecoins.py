from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

STABLECOINS_CURRENT_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
STABLECOIN_CHARTS_ALL_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
DEFILLAMA_SOURCE = "defillama_stablecoins"


class DeFiLlamaStablecoinError(ValueError):
    """Raised when DeFiLlama stablecoin data cannot be parsed."""


def fetch_stablecoins_current() -> dict[str, Any]:
    """Fetch current DeFiLlama stablecoin supply data."""

    try:
        response = requests.get(STABLECOINS_CURRENT_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DeFiLlamaStablecoinError(
            f"DeFiLlama stablecoins current request failed: {exc.__class__.__name__}"
        ) from None
    payload = response.json()
    if not isinstance(payload, dict):
        raise DeFiLlamaStablecoinError("Current stablecoins response is not a JSON object.")
    return payload


def fetch_stablecoin_charts_all() -> dict[str, Any] | list[Any] | None:
    """Fetch DeFiLlama total stablecoin historical chart data."""

    try:
        response = requests.get(STABLECOIN_CHARTS_ALL_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Warning: DeFiLlama stablecoin charts request failed: {exc.__class__.__name__}")
        return None
    return response.json()


def save_json(data: Any, output: Path) -> Path:
    """Save raw JSON payload to disk."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return output


def load_json(path: Path) -> Any:
    """Load a raw JSON payload from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def parse_stablecoins_current(raw: dict[str, Any]) -> pd.DataFrame:
    """Parse current stablecoin metadata and circulating supply."""

    stablecoins = raw.get("peggedAssets") or raw.get("stablecoins") or raw.get("data") or []
    if not isinstance(stablecoins, list):
        raise DeFiLlamaStablecoinError("Unable to locate stablecoin list in current response.")

    rows: list[dict[str, Any]] = []
    for item in stablecoins:
        if not isinstance(item, dict):
            continue
        chains = item.get("chains")
        if chains is None and isinstance(item.get("chainCirculating"), dict):
            chains = sorted(item["chainCirculating"].keys())
        rows.append(
            {
                "stablecoin_id": item.get("id"),
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "peg_type": item.get("pegType"),
                "peg_mechanism": item.get("pegMechanism"),
                "price": _to_float(item.get("price")),
                "circulating_current": extract_pegged_usd(item.get("circulating")),
                "circulating_prev_day": extract_pegged_usd(item.get("circulatingPrevDay")),
                "circulating_prev_week": extract_pegged_usd(item.get("circulatingPrevWeek")),
                "circulating_prev_month": extract_pegged_usd(item.get("circulatingPrevMonth")),
                "chains": ",".join(chains) if isinstance(chains, list) else chains,
                "source": DEFILLAMA_SOURCE,
            }
        )
    return pd.DataFrame(rows)


def build_stablecoin_current_summary(current_df: pd.DataFrame) -> pd.DataFrame:
    """Build point-in-time summary metrics for current stablecoin supply."""

    if current_df.empty:
        raise DeFiLlamaStablecoinError("Current stablecoin table is empty.")

    data = current_df.copy()
    data["circulating_current"] = pd.to_numeric(data["circulating_current"], errors="coerce")
    usd_mask = data["peg_type"].astype(str).str.lower().str.contains("usd", na=False)
    # DeFiLlama peg_type naming has changed over time. If peg_type is unavailable or unstable,
    # fall back to summing all assets with a current circulating USD value.
    supply_pool = data[usd_mask] if usd_mask.any() else data
    total_supply = float(supply_pool["circulating_current"].sum(skipna=True))

    usdt_supply = _sum_matching_supply(data, symbols={"USDT"}, name_terms=["tether"])
    usdc_supply = _sum_matching_supply(data, symbols={"USDC"}, name_terms=["usd coin", "usdc"])
    today = pd.Timestamp.now(tz="UTC").date().isoformat()
    metrics = {
        "total_stablecoin_supply_current": total_supply,
        "usdt_supply_current": usdt_supply,
        "usdc_supply_current": usdc_supply,
        "usdt_dominance_current": _safe_divide(usdt_supply, total_supply),
        "usdc_dominance_current": _safe_divide(usdc_supply, total_supply),
    }
    return pd.DataFrame(
        [
            {"metric": metric, "value": value, "date": today, "source": DEFILLAMA_SOURCE}
            for metric, value in metrics.items()
        ]
    )


def parse_stablecoin_charts_all(raw: Any) -> pd.DataFrame:
    """Parse DeFiLlama total stablecoin historical supply from common response shapes."""

    if raw is None:
        print("Warning: stablecoin charts payload is empty.")
        return pd.DataFrame(columns=["date", "total_stablecoin_supply"])

    records = _extract_chart_records(raw)
    rows: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        date = _parse_chart_date(item.get("date"))
        total_supply = (
            extract_pegged_usd(item.get("totalCirculating"))
            or extract_pegged_usd(item.get("totalCirculatingUSD"))
            or extract_pegged_usd(item.get("totalCirculatingUSDValue"))
        )
        if date is None or total_supply is None:
            continue
        rows.append({"date": date, "total_stablecoin_supply": total_supply})

    if not rows:
        print("Warning: unable to parse stablecoincharts/all response.")
        return pd.DataFrame(columns=["date", "total_stablecoin_supply"])

    output = pd.DataFrame(rows)
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["total_stablecoin_supply"] = pd.to_numeric(
        output["total_stablecoin_supply"], errors="coerce"
    )
    output = output.dropna(subset=["date"])
    output = output.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return output.reset_index(drop=True)


def extract_pegged_usd(value: Any) -> float | None:
    """Extract pegged USD amount from a number or DeFiLlama value dict."""

    if value is None:
        return None
    if not isinstance(value, dict) and pd.isna(value):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return _to_float(value)
    if isinstance(value, dict):
        for key in ["peggedUSD", "USD", "usd"]:
            if key in value:
                return _to_float(value[key])
    return None


def _extract_chart_records(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get("peggedUSD"), list):
            return raw["peggedUSD"]
        for key in ["data", "chart", "charts"]:
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def _parse_chart_date(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.strip().isdigit()):
        parsed = pd.to_datetime(float(value), unit="s", errors="coerce")
    else:
        parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def _sum_matching_supply(data: pd.DataFrame, symbols: set[str], name_terms: list[str]) -> float:
    symbol = data["symbol"].astype(str).str.upper()
    name = data["name"].astype(str).str.lower()
    mask = symbol.isin(symbols)
    for term in name_terms:
        mask = mask | name.str.contains(term, na=False)
    return float(data.loc[mask, "circulating_current"].sum(skipna=True))


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.lower() in {"", "na", "nan", "none", "null"}:
            return None
        return float(cleaned)
    if pd.isna(value):
        return None
    return float(value)
