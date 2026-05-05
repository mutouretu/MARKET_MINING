from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.feature_utils import percent_change, rolling_zscore

TRANSMISSION_NOTES = [
    "Stablecoin supply is treated as a transmission variable rather than a standalone leading indicator.",
    "Transmission features are explanatory variables and should not be treated as direct trading signals.",
]


class TransmissionFeatureError(ValueError):
    """Raised when transmission feature inputs are incomplete or invalid."""


def build_transmission_features(
    macro_features: pd.DataFrame,
    btc_market: pd.DataFrame,
) -> pd.DataFrame:
    """Build stablecoin transmission and divergence features."""

    _require_columns(
        macro_features,
        {"date", "net_liquidity", "total_stablecoin_supply"},
        "macro_features",
    )
    _require_columns(btc_market, {"date", "btc_price", "btc_market_cap", "btc_volume"}, "btc_market")

    macro = macro_features.drop(
        columns=[column for column in _output_columns(macro_features) if column != "date"],
        errors="ignore",
    ).copy()
    btc = btc_market.copy()
    macro["date"] = pd.to_datetime(macro["date"], errors="coerce")
    btc["date"] = pd.to_datetime(btc["date"], errors="coerce")
    data = macro.merge(btc, on="date", how="outer").sort_values("date").reset_index(drop=True)
    for column in [
        "net_liquidity",
        "total_stablecoin_supply",
        "btc_price",
        "btc_market_cap",
        "btc_volume",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data["btc_return_7d"] = percent_change(data["btc_price"], 7)
    data["btc_return_30d"] = percent_change(data["btc_price"], 30)
    data["btc_return_90d"] = percent_change(data["btc_price"], 90)
    data["btc_return_180d"] = percent_change(data["btc_price"], 180)
    data["btc_forward_return_30d"] = data["btc_price"].shift(-30) / data["btc_price"] - 1
    data["btc_forward_return_90d"] = data["btc_price"].shift(-90) / data["btc_price"] - 1
    data["btc_forward_return_180d"] = data["btc_price"].shift(-180) / data["btc_price"] - 1

    data["stablecoin_to_btc_mcap"] = _safe_ratio(
        data["total_stablecoin_supply"], data["btc_market_cap"]
    )
    data["btc_to_stablecoin_ratio"] = _safe_ratio(
        data["btc_market_cap"], data["total_stablecoin_supply"]
    )

    data["stablecoin_supply_growth_30d"] = percent_change(data["total_stablecoin_supply"], 30)
    data["stablecoin_supply_growth_90d"] = percent_change(data["total_stablecoin_supply"], 90)
    data["net_liquidity_growth_30d"] = percent_change(data["net_liquidity"], 30)
    data["net_liquidity_growth_90d"] = percent_change(data["net_liquidity"], 90)

    data["liquidity_transmission_gap_30d"] = (
        data["net_liquidity_growth_30d"] - data["stablecoin_supply_growth_30d"]
    )
    data["liquidity_transmission_gap_90d"] = (
        data["net_liquidity_growth_90d"] - data["stablecoin_supply_growth_90d"]
    )
    data["stablecoin_btc_growth_gap_30d"] = (
        data["stablecoin_supply_growth_30d"] - data["btc_return_30d"]
    )
    data["stablecoin_btc_growth_gap_90d"] = (
        data["stablecoin_supply_growth_90d"] - data["btc_return_90d"]
    )
    data["net_liquidity_btc_growth_gap_30d"] = (
        data["net_liquidity_growth_30d"] - data["btc_return_30d"]
    )
    data["net_liquidity_btc_growth_gap_90d"] = (
        data["net_liquidity_growth_90d"] - data["btc_return_90d"]
    )

    for column in [
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
    ]:
        data[f"{column}_zscore_252d"] = rolling_zscore(pd.to_numeric(data[column], errors="coerce"), 252)

    data["transmission_phase"] = data.apply(_infer_transmission_phase, axis=1)
    return data[_output_columns(data)]


def update_macro_features_with_transmission(
    macro_features: pd.DataFrame,
    transmission: pd.DataFrame,
) -> pd.DataFrame:
    """Merge transmission fields into macro_features_daily without deleting existing fields."""

    features = macro_features.copy()
    features["date"] = pd.to_datetime(features["date"], errors="coerce")
    trans = transmission.copy()
    trans["date"] = pd.to_datetime(trans["date"], errors="coerce")
    merge_frame = trans[_output_columns(trans)]
    for column in merge_frame.columns:
        if column != "date" and column in features.columns:
            features = features.drop(columns=[column])
    return features.merge(merge_frame, on="date", how="outer").sort_values("date")


def update_macro_snapshot_with_transmission(
    snapshot: dict[str, Any],
    transmission: pd.DataFrame,
) -> dict[str, Any]:
    """Update snapshot with latest transmission fields and notes."""

    updated = dict(snapshot)
    data = transmission.sort_values("date")
    key_features = dict(updated.get("key_features") or {})
    for column in [
        "btc_price",
        "btc_market_cap",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "stablecoin_supply_growth_30d",
        "stablecoin_supply_growth_90d",
        "net_liquidity_growth_30d",
        "net_liquidity_growth_90d",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_30d",
        "stablecoin_btc_growth_gap_90d",
        "net_liquidity_btc_growth_gap_30d",
        "net_liquidity_btc_growth_gap_90d",
    ]:
        key_features[column] = _to_json_value(_latest_non_null(data, column))
    complete_phase = data.dropna(
        subset=["net_liquidity_growth_90d", "stablecoin_supply_growth_90d", "btc_return_90d"]
    )
    if not complete_phase.empty:
        key_features["transmission_phase"] = _to_json_value(
            complete_phase.iloc[-1].get("transmission_phase")
        )
    else:
        key_features["transmission_phase"] = _to_json_value(_latest_non_null(data, "transmission_phase"))
    updated["key_features"] = key_features

    notes = _dedupe_notes(list(updated.get("notes") or []))
    for note in TRANSMISSION_NOTES:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    return updated


def run_transmission_update(
    macro_features_path: Path,
    btc_market: pd.DataFrame,
    btc_output_path: Path,
    output_path: Path,
    features_path: Path,
    snapshot_path: Path,
) -> None:
    """Write BTC market, transmission features, and updated macro outputs."""

    macro = pd.read_csv(macro_features_path)
    btc_output_path.parent.mkdir(parents=True, exist_ok=True)
    btc_market.to_csv(btc_output_path, index=False)
    transmission = build_transmission_features(macro, btc_market)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    transmission.to_csv(output_path, index=False)

    updated_features = update_macro_features_with_transmission(macro, transmission)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    updated_features.to_csv(features_path, index=False)

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot = {}
    updated_snapshot = update_macro_snapshot_with_transmission(snapshot, transmission)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated_snapshot, indent=2), encoding="utf-8")


def _infer_transmission_phase(row: pd.Series) -> str:
    net_90 = row.get("net_liquidity_growth_90d")
    stable_90 = row.get("stablecoin_supply_growth_90d")
    btc_90 = row.get("btc_return_90d")
    if pd.isna(net_90) or pd.isna(stable_90) or pd.isna(btc_90):
        return "neutral"
    if net_90 > 0 and stable_90 <= 0:
        return "macro_liquidity_not_transmitted"
    if net_90 > 0 and stable_90 > 0 and btc_90 <= 0:
        return "crypto_liquidity_accumulating"
    if net_90 > 0 and stable_90 > 0 and btc_90 > 0:
        return "liquidity_transmitted_to_price"
    if net_90 <= 0 and stable_90 > 0 and btc_90 > 0:
        return "crypto_internal_momentum"
    if net_90 <= 0 and stable_90 <= 0:
        return "liquidity_contraction"
    return "neutral"


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = pd.to_numeric(denominator, errors="coerce")
    num = pd.to_numeric(numerator, errors="coerce")
    return num / denom.where(denom != 0)


def _output_columns(data: pd.DataFrame) -> list[str]:
    columns = [
        "date",
        "btc_price",
        "btc_market_cap",
        "btc_volume",
        "btc_return_7d",
        "btc_return_30d",
        "btc_return_90d",
        "btc_return_180d",
        "btc_forward_return_30d",
        "btc_forward_return_90d",
        "btc_forward_return_180d",
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "stablecoin_supply_growth_30d",
        "stablecoin_supply_growth_90d",
        "net_liquidity_growth_30d",
        "net_liquidity_growth_90d",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_30d",
        "stablecoin_btc_growth_gap_90d",
        "net_liquidity_btc_growth_gap_30d",
        "net_liquidity_btc_growth_gap_90d",
        "stablecoin_to_btc_mcap_zscore_252d",
        "btc_to_stablecoin_ratio_zscore_252d",
        "liquidity_transmission_gap_30d_zscore_252d",
        "liquidity_transmission_gap_90d_zscore_252d",
        "transmission_phase",
    ]
    return [column for column in columns if column in data.columns]


def _to_json_value(value: Any) -> float | str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        return value
    return float(value)


def _latest_non_null(data: pd.DataFrame, column: str) -> Any:
    if column not in data.columns:
        return None
    values = data[column].dropna()
    if values.empty:
        return None
    return values.iloc[-1]


def _dedupe_notes(notes: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for note in notes:
        if note in seen:
            continue
        seen.add(note)
        output.append(note)
    return output


def _require_columns(data: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns - set(data.columns)
    if missing:
        raise TransmissionFeatureError(f"{name} missing required columns: {sorted(missing)}")
