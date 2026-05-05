from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.feature_utils import absolute_change, percent_change, rolling_zscore

STABLECOIN_LIQUIDITY_NOTE = (
    "Stablecoin supply is used as a proxy for crypto-native dollar liquidity."
)
STABLECOIN_HISTORY_NOTE = (
    "USDT and USDC historical supply are not fully available in Step 4A; current values are "
    "included without backfilling historical values."
)


class StablecoinLiquidityError(ValueError):
    """Raised when stablecoin liquidity inputs are incomplete or invalid."""


def build_stablecoin_liquidity(
    charts_df: pd.DataFrame,
    current_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Build daily stablecoin liquidity features from total historical supply and current summary."""

    _require_columns(charts_df, {"date", "total_stablecoin_supply"}, "charts_df")
    _require_columns(current_summary, {"metric", "value", "date"}, "current_summary")
    if charts_df.empty:
        raise StablecoinLiquidityError("stablecoin charts are empty.")

    output = charts_df[["date", "total_stablecoin_supply"]].copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["total_stablecoin_supply"] = pd.to_numeric(
        output["total_stablecoin_supply"], errors="coerce"
    )
    output = output.dropna(subset=["date"]).sort_values("date")
    output = output.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    if output.empty:
        raise StablecoinLiquidityError("stablecoin charts are empty after date parsing.")

    _add_derived_fields(output, "total_stablecoin_supply")
    _add_current_usdt_usdc(output, current_summary)
    output["stablecoin_liquidity_score"] = pd.NA
    validate_stablecoin_liquidity(output)
    return output


def update_macro_features_with_stablecoins(
    features: pd.DataFrame,
    stablecoin_liquidity: pd.DataFrame,
) -> pd.DataFrame:
    """Merge stablecoin liquidity fields into macro_features_daily without dropping old fields."""

    features_out = features.copy()
    features_out["date"] = pd.to_datetime(features_out["date"], errors="coerce")
    stablecoins = stablecoin_liquidity.copy()
    stablecoins["date"] = pd.to_datetime(stablecoins["date"], errors="coerce")

    columns = [
        "date",
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_7d",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
        "total_stablecoin_supply_pct_change_30d",
        "total_stablecoin_supply_pct_change_90d",
        "total_stablecoin_supply_zscore_252d",
        "total_stablecoin_supply_slope_30d",
        "total_stablecoin_supply_slope_90d",
        "usdt_supply",
        "usdc_supply",
        "usdt_supply_change_30d",
        "usdt_supply_change_90d",
        "usdc_supply_change_30d",
        "usdc_supply_change_90d",
        "usdt_dominance",
        "usdc_dominance",
        "usdt_history_available",
        "usdc_history_available",
        "stablecoin_liquidity_score",
    ]
    merge_frame = stablecoins[[column for column in columns if column in stablecoins.columns]]
    for column in merge_frame.columns:
        if column != "date" and column in features_out.columns:
            features_out = features_out.drop(columns=[column])
    return features_out.merge(merge_frame, on="date", how="outer").sort_values("date")


def update_macro_snapshot_with_stablecoins(
    snapshot: dict[str, Any],
    stablecoin_liquidity: pd.DataFrame,
) -> dict[str, Any]:
    """Update macro snapshot with latest stablecoin liquidity fields and notes."""

    updated = dict(snapshot)
    latest = stablecoin_liquidity.sort_values("date").iloc[-1]
    key_features = dict(updated.get("key_features") or {})
    for column in [
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
        "total_stablecoin_supply_zscore_252d",
        "usdt_supply",
        "usdc_supply",
        "usdt_dominance",
        "usdc_dominance",
        "usdt_history_available",
        "usdc_history_available",
    ]:
        key_features[column] = _to_json_value(latest.get(column))
    updated["key_features"] = key_features

    notes = _dedupe_notes(list(updated.get("notes") or []))
    for note in [STABLECOIN_LIQUIDITY_NOTE, STABLECOIN_HISTORY_NOTE]:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    return updated


def run_stablecoin_liquidity_update(
    charts_df: pd.DataFrame,
    current_summary: pd.DataFrame,
    output_path: Path,
    features_path: Path,
    snapshot_path: Path,
    current_summary_path: Path | None = None,
) -> list[str]:
    """Build stablecoin outputs and update macro features/snapshot."""

    stablecoin_liquidity = build_stablecoin_liquidity(charts_df, current_summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stablecoin_liquidity.to_csv(output_path, index=False)

    if current_summary_path is not None:
        current_summary_path.parent.mkdir(parents=True, exist_ok=True)
        current_summary.to_csv(current_summary_path, index=False)

    if features_path.exists():
        features = pd.read_csv(features_path)
    else:
        features = stablecoin_liquidity[["date"]].copy()
    updated_features = update_macro_features_with_stablecoins(features, stablecoin_liquidity)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    updated_features.to_csv(features_path, index=False)

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot = {}
    updated_snapshot = update_macro_snapshot_with_stablecoins(snapshot, stablecoin_liquidity)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated_snapshot, indent=2), encoding="utf-8")
    return validate_stablecoin_liquidity(stablecoin_liquidity)


def validate_stablecoin_liquidity(df: pd.DataFrame) -> list[str]:
    """Validate stablecoin liquidity output."""

    _require_columns(df, {"date", "total_stablecoin_supply"}, "stablecoin_liquidity")
    warnings: list[str] = []
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["total_stablecoin_supply"] = pd.to_numeric(
        data["total_stablecoin_supply"], errors="coerce"
    )
    if data["total_stablecoin_supply"].isna().all():
        raise StablecoinLiquidityError("total_stablecoin_supply is entirely empty.")
    if (data["total_stablecoin_supply"].dropna() < 0).any():
        raise StablecoinLiquidityError("total_stablecoin_supply contains negative values.")

    latest_date = data["date"].max()
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    if pd.notna(latest_date) and (now - latest_date).days > 14:
        warnings.append(f"Stablecoin latest date {latest_date.date()} is more than 14 days old.")

    for column in ["usdt_dominance", "usdc_dominance"]:
        if column in data.columns:
            series = pd.to_numeric(data[column], errors="coerce").dropna()
            if not series.empty and ((series < 0) | (series > 1)).any():
                raise StablecoinLiquidityError(f"{column} must be between 0 and 1.")

    for column in ["usdt_history_available", "usdc_history_available"]:
        if column in data.columns and not bool(data[column].fillna(False).any()):
            warnings.append(f"{column} is false; current value is not backfilled.")
    return warnings


def _add_derived_fields(data: pd.DataFrame, column: str) -> None:
    series = pd.to_numeric(data[column], errors="coerce")
    data[f"{column}_change_7d"] = absolute_change(series, 7)
    data[f"{column}_change_30d"] = absolute_change(series, 30)
    data[f"{column}_change_90d"] = absolute_change(series, 90)
    data[f"{column}_pct_change_30d"] = percent_change(series, 30)
    data[f"{column}_pct_change_90d"] = percent_change(series, 90)
    data[f"{column}_zscore_252d"] = rolling_zscore(series, 252)
    data[f"{column}_slope_30d"] = absolute_change(series, 30)
    data[f"{column}_slope_90d"] = absolute_change(series, 90)


def _add_current_usdt_usdc(output: pd.DataFrame, current_summary: pd.DataFrame) -> None:
    latest_date = output["date"].max()
    metrics = _summary_metrics(current_summary)
    for column in [
        "usdt_supply",
        "usdc_supply",
        "usdt_supply_change_30d",
        "usdt_supply_change_90d",
        "usdc_supply_change_30d",
        "usdc_supply_change_90d",
        "usdt_dominance",
        "usdc_dominance",
    ]:
        output[column] = pd.NA
    latest_mask = output["date"] == latest_date
    output.loc[latest_mask, "usdt_supply"] = metrics.get("usdt_supply_current")
    output.loc[latest_mask, "usdc_supply"] = metrics.get("usdc_supply_current")
    output.loc[latest_mask, "usdt_dominance"] = metrics.get("usdt_dominance_current")
    output.loc[latest_mask, "usdc_dominance"] = metrics.get("usdc_dominance_current")
    output["usdt_history_available"] = False
    output["usdc_history_available"] = False


def _summary_metrics(current_summary: pd.DataFrame) -> dict[str, Any]:
    data = current_summary.copy()
    return dict(zip(data["metric"].astype(str), pd.to_numeric(data["value"], errors="coerce")))


def _to_json_value(value: Any) -> float | bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    return float(value)


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
        raise StablecoinLiquidityError(f"{name} missing required columns: {sorted(missing)}")
