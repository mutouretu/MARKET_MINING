from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.feature_utils import absolute_change, percent_change, rolling_zscore

PROXY_NO_TGA_NOTE = (
    "usd_liquidity_proxy_no_tga excludes TGA and should not be treated as full net liquidity."
)
NET_LIQUIDITY_NOTE = "net_liquidity is computed as WALCL_BILLION - TGA_BILLION - RRPONTSYD."


class UsdLiquidityError(ValueError):
    """Raised when USD liquidity inputs are incomplete or invalid."""


def build_usd_liquidity(fred_wide: pd.DataFrame, tga_daily: pd.DataFrame) -> pd.DataFrame:
    """Build daily USD liquidity with TGA-adjusted net liquidity."""

    _require_columns(fred_wide, {"date", "WALCL_BILLION", "RRPONTSYD"}, "fred_wide")
    _require_columns(tga_daily, {"date", "tga_billion"}, "tga_daily")

    fred = fred_wide[["date", "WALCL_BILLION", "RRPONTSYD"]].copy()
    tga = tga_daily[["date", "tga_billion"]].copy()
    fred["date"] = pd.to_datetime(fred["date"], errors="coerce")
    tga["date"] = pd.to_datetime(tga["date"], errors="coerce")
    fred["WALCL_BILLION"] = pd.to_numeric(fred["WALCL_BILLION"], errors="coerce")
    fred["RRPONTSYD"] = pd.to_numeric(fred["RRPONTSYD"], errors="coerce")
    tga["tga_billion"] = pd.to_numeric(tga["tga_billion"], errors="coerce")

    if tga["tga_billion"].isna().all():
        raise UsdLiquidityError("tga_billion is entirely empty.")
    if (tga["tga_billion"].dropna() < 0).any():
        raise UsdLiquidityError("tga_billion contains negative values.")

    merged = fred.merge(tga, on="date", how="outer").sort_values("date")
    merged = merged.set_index("date")
    daily_index = pd.date_range(merged.index.min(), merged.index.max(), freq="D")
    merged = merged.reindex(daily_index)
    merged.index.name = "date"
    merged[["WALCL_BILLION", "RRPONTSYD", "tga_billion"]] = merged[
        ["WALCL_BILLION", "RRPONTSYD", "tga_billion"]
    ].ffill()

    output = pd.DataFrame(index=merged.index)
    output["walcl_billion"] = merged["WALCL_BILLION"]
    output["rrp_billion"] = merged["RRPONTSYD"]
    output["tga_billion"] = merged["tga_billion"]
    output["usd_liquidity_proxy_no_tga"] = output["walcl_billion"] - output["rrp_billion"]
    output["net_liquidity"] = (
        output["walcl_billion"] - output["tga_billion"] - output["rrp_billion"]
    )

    _add_liquidity_derived_fields(output, "net_liquidity")
    _add_liquidity_derived_fields(output, "tga_billion")
    validate_usd_liquidity(output.reset_index())
    return output.reset_index()


def validate_usd_liquidity(df: pd.DataFrame) -> list[str]:
    """Run basic data quality checks on USD liquidity output."""

    _require_columns(
        df,
        {"date", "walcl_billion", "rrp_billion", "tga_billion", "net_liquidity"},
        "usd_liquidity",
    )
    warnings: list[str] = []
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in ["walcl_billion", "rrp_billion", "tga_billion", "net_liquidity"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    for column in ["net_liquidity", "tga_billion", "walcl_billion", "rrp_billion"]:
        if data[column].isna().all():
            raise UsdLiquidityError(f"{column} is entirely empty.")
    if (data["tga_billion"].dropna() < 0).any():
        raise UsdLiquidityError("tga_billion contains negative values.")

    if "net_liquidity_zscore_252d" in data.columns:
        zscore = pd.to_numeric(data["net_liquidity_zscore_252d"], errors="coerce")
        latest_zscore = zscore.dropna().iloc[-1] if not zscore.dropna().empty else None
        if latest_zscore is not None and abs(float(latest_zscore)) > 5:
            warnings.append(
                f"net_liquidity latest zscore is extreme: {float(latest_zscore):.2f}"
            )
    return warnings


def update_macro_features_with_usd_liquidity(
    features: pd.DataFrame,
    usd_liquidity: pd.DataFrame,
) -> pd.DataFrame:
    """Merge TGA and net liquidity fields into macro_features_daily."""

    features_out = features.copy()
    features_out["date"] = pd.to_datetime(features_out["date"], errors="coerce")
    liquidity = usd_liquidity.copy()
    liquidity["date"] = pd.to_datetime(liquidity["date"], errors="coerce")

    columns = [
        "date",
        "tga_billion",
        "tga_billion_change_7d",
        "tga_billion_change_30d",
        "tga_billion_change_90d",
        "tga_billion_pct_change_30d",
        "tga_billion_pct_change_90d",
        "tga_billion_zscore_252d",
        "tga_billion_slope_30d",
        "tga_billion_slope_90d",
        "net_liquidity",
        "net_liquidity_change_7d",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "net_liquidity_pct_change_30d",
        "net_liquidity_pct_change_90d",
        "net_liquidity_zscore_252d",
        "net_liquidity_slope_30d",
        "net_liquidity_slope_90d",
    ]
    merge_frame = liquidity.copy()
    _add_tga_derived_fields(merge_frame)
    merge_frame = merge_frame[[column for column in columns if column in merge_frame.columns]]

    for column in merge_frame.columns:
        if column != "date" and column in features_out.columns:
            features_out = features_out.drop(columns=[column])

    return features_out.merge(merge_frame, on="date", how="outer").sort_values("date")


def update_macro_snapshot_with_usd_liquidity(
    snapshot: dict[str, Any],
    features: pd.DataFrame,
) -> dict[str, Any]:
    """Update latest snapshot key features and notes with TGA-adjusted net liquidity."""

    updated = dict(snapshot)
    latest = features.sort_values("date").iloc[-1]
    key_features = dict(updated.get("key_features") or {})
    for column in [
        "tga_billion",
        "tga_billion_change_30d",
        "tga_billion_change_90d",
        "tga_billion_zscore_252d",
        "net_liquidity",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "net_liquidity_zscore_252d",
    ]:
        key_features[column] = _to_json_value(latest.get(column))
    updated["key_features"] = key_features

    notes = list(updated.get("notes") or [])
    for note in [PROXY_NO_TGA_NOTE, NET_LIQUIDITY_NOTE]:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    return updated


def run_usd_liquidity_update(
    fred_wide_path: Path,
    tga_path: Path,
    output_path: Path,
    features_path: Path,
    snapshot_path: Path,
) -> list[str]:
    """Build usd_liquidity_daily and update macro features and snapshot outputs."""

    fred_wide = pd.read_csv(fred_wide_path)
    tga_daily = pd.read_csv(tga_path)
    if "tga_billion" not in tga_daily.columns and "close_today_bal_million" in tga_daily.columns:
        tga_daily = tga_daily.copy()
        tga_daily["tga_billion"] = pd.to_numeric(
            tga_daily["close_today_bal_million"], errors="coerce"
        ) / 1000

    usd_liquidity = build_usd_liquidity(fred_wide, tga_daily)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    usd_liquidity.to_csv(output_path, index=False)

    if features_path.exists():
        features = pd.read_csv(features_path)
    else:
        features = fred_wide.copy()
    updated_features = update_macro_features_with_usd_liquidity(features, usd_liquidity)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    updated_features.to_csv(features_path, index=False)

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot = {}
    updated_snapshot = update_macro_snapshot_with_usd_liquidity(snapshot, updated_features)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated_snapshot, indent=2), encoding="utf-8")

    return _build_data_quality_warnings(fred_wide, tga_daily)


def _add_liquidity_derived_fields(data: pd.DataFrame, column: str) -> None:
    series = pd.to_numeric(data[column], errors="coerce")
    data[f"{column}_change_7d"] = absolute_change(series, 7)
    data[f"{column}_change_30d"] = absolute_change(series, 30)
    data[f"{column}_change_90d"] = absolute_change(series, 90)
    data[f"{column}_pct_change_30d"] = percent_change(series, 30)
    data[f"{column}_pct_change_90d"] = percent_change(series, 90)
    data[f"{column}_zscore_252d"] = rolling_zscore(series, 252)
    data[f"{column}_slope_30d"] = absolute_change(series, 30)
    data[f"{column}_slope_90d"] = absolute_change(series, 90)


def _add_tga_derived_fields(data: pd.DataFrame) -> None:
    _add_liquidity_derived_fields(data, "tga_billion")


def _build_data_quality_warnings(fred_wide: pd.DataFrame, tga_daily: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    fred_latest = pd.to_datetime(fred_wide["date"], errors="coerce").max()
    tga_latest = pd.to_datetime(tga_daily["date"], errors="coerce").max()
    if pd.notna(fred_latest) and pd.notna(tga_latest) and (fred_latest - tga_latest).days > 7:
        warnings.append(
            f"TGA latest date {tga_latest.date()} is more than 7 days older than "
            f"FRED latest date {fred_latest.date()}."
        )
    return warnings


def _require_columns(data: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns - set(data.columns)
    if missing:
        raise UsdLiquidityError(f"{name} missing required columns: {sorted(missing)}")


def _to_json_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
