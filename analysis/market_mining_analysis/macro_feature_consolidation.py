from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.feature_utils import absolute_change, percent_change, rolling_zscore

CONSOLIDATED_NOTE = (
    "macro_features_daily.csv is the consolidated feature table used by scoring, regime "
    "detection, and research modules."
)

FRED_RENAME = {
    "DFF": "dff",
    "WALCL": "walcl",
    "WALCL_BILLION": "walcl_billion",
    "RRPONTSYD": "rrp_billion",
    "M2SL": "m2",
    "DGS2": "us2y",
    "DGS10": "us10y",
    "DFII10": "us10y_real",
    "VIXCLS": "vix",
    "BAMLH0A0HYM2": "hy_oas",
}

SOURCE_GROUPS = {
    "dff": "fed_policy",
    "fed_target_upper": "fed_policy",
    "fed_target_lower": "fed_policy",
    "policy_rate_change_30d": "fed_policy",
    "policy_rate_change_90d": "fed_policy",
    "walcl_billion": "usd_liquidity",
    "rrp_billion": "usd_liquidity",
    "tga_billion": "usd_liquidity",
    "usd_liquidity_proxy_no_tga": "usd_liquidity",
    "net_liquidity": "usd_liquidity",
    "m2": "money_supply",
    "m2_yoy": "money_supply",
    "m2_3m_change": "money_supply",
    "us2y": "rates",
    "us10y": "rates",
    "us10y_real": "rates",
    "yield_curve_10y_2y": "rates",
    "breakeven_10y_proxy": "rates",
    "vix": "risk_appetite",
    "hy_oas": "risk_appetite",
    "total_stablecoin_supply": "stablecoin_liquidity",
    "usdt_supply": "stablecoin_liquidity",
    "usdc_supply": "stablecoin_liquidity",
    "usdt_dominance": "stablecoin_liquidity",
    "usdc_dominance": "stablecoin_liquidity",
    "stablecoin_liquidity_score": "stablecoin_liquidity",
    "btc_price": "btc_market",
    "btc_market_cap": "btc_market",
    "btc_volume": "btc_market",
    "transmission_phase": "transmission",
}

LOW_FREQUENCY_FIELDS = {
    "dff",
    "walcl_billion",
    "rrp_billion",
    "tga_billion",
    "m2",
    "us2y",
    "us10y",
    "us10y_real",
    "vix",
    "hy_oas",
    "total_stablecoin_supply",
    "usd_liquidity_proxy_no_tga",
    "net_liquidity",
}

BTC_FILL_FIELDS = {"btc_price", "btc_market_cap", "btc_volume"}
CURRENT_ONLY_FIELDS = {
    "usdt_supply",
    "usdc_supply",
    "usdt_dominance",
    "usdc_dominance",
}
PLACEHOLDER_FIELDS = {"stablecoin_liquidity_score"}

CORE_FIELDS = ["net_liquidity", "btc_price", "total_stablecoin_supply", "us10y_real", "vix"]


@dataclass
class ConsolidationResult:
    features: pd.DataFrame
    audit: pd.DataFrame
    latest_snapshot: pd.DataFrame
    warnings: list[str]
    missing_inputs: list[str]


class MacroFeatureConsolidationError(ValueError):
    """Raised when macro feature consolidation cannot be completed."""


def build_daily_feature_frame(
    fred_wide: pd.DataFrame | None = None,
    usd_liquidity: pd.DataFrame | None = None,
    stablecoins: pd.DataFrame | None = None,
    btc_market: pd.DataFrame | None = None,
    transmission: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, set[str]], list[str]]:
    """Build the consolidated daily feature frame from available inputs."""

    notes: dict[str, set[str]] = {}
    warnings: list[str] = []
    frames = [
        _prepare_fred(fred_wide, notes),
        _prepare_simple(usd_liquidity, "usd_liquidity", notes),
        _prepare_simple(stablecoins, "stablecoin_liquidity", notes),
        _prepare_simple(btc_market, "btc_market", notes),
        _prepare_transmission(transmission, notes),
    ]
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        raise MacroFeatureConsolidationError("No valid input files were available.")

    all_dates = pd.concat([frame[["date"]] for frame in frames], ignore_index=True)
    start = all_dates["date"].min()
    end = all_dates["date"].max()
    output = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    sources: dict[str, str] = {}

    for frame in frames:
        source_name = str(frame.attrs.get("source_name", "unknown"))
        for column in [column for column in frame.columns if column != "date"]:
            if column in output.columns:
                notes.setdefault(column, set()).add("field_conflict_resolved")
                continue
            output = output.merge(frame[["date", column]], on="date", how="left")
            sources[column] = source_name

    _forward_fill_fields(output, notes)
    _compute_missing_features(output, notes)
    output = _finalize_order(output)
    warnings.extend(validate_macro_features(output))
    return output, notes, warnings


def consolidate_macro_features(
    fred_wide_path: Path,
    usd_liquidity_path: Path,
    stablecoins_path: Path,
    btc_market_path: Path,
    transmission_path: Path,
    output_path: Path,
    audit_output_path: Path,
    latest_output_path: Path,
    snapshot_path: Path,
) -> ConsolidationResult:
    """Read inputs, write consolidated features/audit/latest snapshot, and update JSON snapshot."""

    missing_inputs: list[str] = []
    inputs = {
        "fred_wide": _read_optional_csv(fred_wide_path, missing_inputs),
        "usd_liquidity": _read_optional_csv(usd_liquidity_path, missing_inputs),
        "stablecoins": _read_optional_csv(stablecoins_path, missing_inputs),
        "btc_market": _read_optional_csv(btc_market_path, missing_inputs),
        "transmission": _read_optional_csv(transmission_path, missing_inputs),
    }
    features, notes, warnings = build_daily_feature_frame(**inputs)
    for missing in missing_inputs:
        warnings.append(f"Missing input file: {missing}")

    audit = build_feature_audit(features, notes)
    latest_snapshot = build_latest_snapshot(features)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_output_path.parent.mkdir(parents=True, exist_ok=True)
    latest_output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    audit.to_csv(audit_output_path, index=False)
    latest_snapshot.to_csv(latest_output_path, index=False)
    update_macro_snapshot(snapshot_path, features, warnings)
    return ConsolidationResult(features, audit, latest_snapshot, warnings, missing_inputs)


def build_feature_audit(features: pd.DataFrame, notes: dict[str, set[str]] | None = None) -> pd.DataFrame:
    """Build one-row-per-feature quality audit."""

    notes = notes or {}
    rows: list[dict[str, Any]] = []
    for column in features.columns:
        if column == "date":
            continue
        series = features[column]
        numeric = pd.to_numeric(series, errors="coerce")
        valid = series.dropna()
        column_notes = set(notes.get(column, set()))
        if column in CURRENT_ONLY_FIELDS:
            column_notes.add("current_only_field")
        if column in PLACEHOLDER_FIELDS:
            column_notes.add("placeholder_score")
        if column in LOW_FREQUENCY_FIELDS:
            column_notes.add("field_forward_filled")
            if column == "m2":
                column_notes.add("low_frequency_source")
        rows.append(
            {
                "feature": column,
                "non_null_count": int(series.notna().sum()),
                "null_count": int(series.isna().sum()),
                "null_ratio": float(series.isna().mean()),
                "first_valid_date": _date_for_index(features, valid.index.min()),
                "last_valid_date": _date_for_index(features, valid.index.max()),
                "latest_value": _latest_value(series),
                "mean": _stat(numeric, "mean"),
                "std": _stat(numeric, "std"),
                "min": _stat(numeric, "min"),
                "max": _stat(numeric, "max"),
                "source_group": _source_group(column),
                "notes": ";".join(sorted(column_notes)),
            }
        )
    return pd.DataFrame(rows)


def build_latest_snapshot(features: pd.DataFrame) -> pd.DataFrame:
    """Build latest-row CSV for manual inspection."""

    columns = [
        "date",
        "dff",
        "net_liquidity",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "tga_billion",
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "btc_price",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "transmission_phase",
        "vix",
        "hy_oas",
        "us10y_real",
    ]
    latest = features.sort_values("date").tail(1)
    for column in columns:
        if column not in latest.columns:
            latest[column] = pd.NA
    return latest[columns]


def update_macro_snapshot(snapshot_path: Path, features: pd.DataFrame, warnings: list[str]) -> dict[str, Any]:
    """Update macro_snapshot_latest.json from consolidated features."""

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot = {}
    updated = dict(snapshot)
    latest_date = features["date"].max()
    updated["latest_date"] = latest_date.strftime("%Y-%m-%d")
    key_features = dict(updated.get("key_features") or {})
    for column in [
        "dff",
        "net_liquidity",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "tga_billion",
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
        "btc_price",
        "btc_market_cap",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_30d",
        "stablecoin_btc_growth_gap_90d",
        "net_liquidity_btc_growth_gap_30d",
        "net_liquidity_btc_growth_gap_90d",
        "transmission_phase",
        "vix",
        "hy_oas",
        "us10y_real",
        "yield_curve_10y_2y",
        "breakeven_10y_proxy",
    ]:
        key_features[column] = _json_value(_latest_non_null(features, column))
    updated["key_features"] = key_features
    notes = _dedupe_notes(list(updated.get("notes") or []))
    if CONSOLIDATED_NOTE not in notes:
        notes.append(CONSOLIDATED_NOTE)
    for warning in warnings:
        note = f"Warning: {warning}"
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    return updated


def validate_macro_features(df: pd.DataFrame) -> list[str]:
    """Validate consolidated macro features and return warnings."""

    warnings: list[str] = []
    if "date" not in df.columns:
        raise MacroFeatureConsolidationError("date column is required.")
    if df.columns.duplicated().any():
        duplicates = df.columns[df.columns.duplicated()].tolist()
        raise MacroFeatureConsolidationError(f"Duplicate columns found: {duplicates}")
    suffix_columns = [column for column in df.columns if column.endswith(("_x", "_y"))]
    if suffix_columns:
        raise MacroFeatureConsolidationError(f"Unexpected pandas suffix columns: {suffix_columns}")
    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.isna().any():
        raise MacroFeatureConsolidationError("date contains invalid values.")
    if dates.duplicated().any():
        raise MacroFeatureConsolidationError("date must be unique.")
    if not dates.is_monotonic_increasing:
        raise MacroFeatureConsolidationError("date must be sorted ascending.")
    if len(df) < 100:
        raise MacroFeatureConsolidationError("macro_features_daily must contain at least 100 rows.")
    for column in CORE_FIELDS:
        if column not in df.columns:
            warnings.append(f"Core field missing: {column}")
        elif df[column].isna().all():
            warnings.append(f"Core field entirely empty: {column}")
    if (pd.Timestamp.now().normalize() - dates.max()).days > 14:
        warnings.append(f"Latest macro feature date {dates.max().date()} is more than 14 days old.")
    return warnings


def safe_divide(a: Any, b: Any) -> Any:
    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        denominator = pd.to_numeric(b, errors="coerce")
        numerator = pd.to_numeric(a, errors="coerce")
        return numerator / denominator.where(denominator != 0)
    if b in {0, None} or pd.isna(b):
        return None
    return a / b


def rolling_change(series: pd.Series, window: int) -> pd.Series:
    return absolute_change(pd.to_numeric(series, errors="coerce"), window)


def pct_change(series: pd.Series, window: int) -> pd.Series:
    return percent_change(pd.to_numeric(series, errors="coerce"), window)


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window=window, min_periods=max(2, window // 2)).mean()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window=window, min_periods=max(2, window // 2)).std()


def clip(value: Any, lower: float, upper: float) -> Any:
    if isinstance(value, pd.Series):
        return value.clip(lower, upper)
    return min(max(value, lower), upper)


def _prepare_fred(data: pd.DataFrame | None, notes: dict[str, set[str]]) -> pd.DataFrame | None:
    if data is None or data.empty:
        return None
    frame = _with_date(data).rename(columns=FRED_RENAME)
    keep = ["date"] + [column for column in FRED_RENAME.values() if column in frame.columns]
    for column in keep:
        notes.setdefault(column, set()).add("field_standardized") if column != "date" else None
    frame = frame[keep].drop_duplicates(subset=["date"], keep="last")
    frame.attrs["source_name"] = "fred_wide"
    return frame


def _prepare_simple(
    data: pd.DataFrame | None,
    source_name: str,
    notes: dict[str, set[str]],
) -> pd.DataFrame | None:
    if data is None or data.empty:
        return None
    frame = _with_date(data).copy()
    frame = frame.loc[:, ~frame.columns.duplicated()]
    frame = frame.drop(columns=[column for column in frame.columns if column.endswith(("_x", "_y"))], errors="ignore")
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    frame.attrs["source_name"] = source_name
    for column in frame.columns:
        if column != "date":
            notes.setdefault(column, set()).add(f"source:{source_name}")
    return frame


def _prepare_transmission(
    data: pd.DataFrame | None,
    notes: dict[str, set[str]],
) -> pd.DataFrame | None:
    frame = _prepare_simple(data, "transmission", notes)
    if frame is None:
        return None
    drop = ["btc_price", "btc_market_cap", "btc_volume"]
    return frame.drop(columns=[column for column in drop if column in frame.columns])


def _with_date(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    if "date" not in frame.columns:
        raise MacroFeatureConsolidationError("Input frame missing date column.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    return frame


def _forward_fill_fields(output: pd.DataFrame, notes: dict[str, set[str]]) -> None:
    for column in LOW_FREQUENCY_FIELDS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").ffill()
            notes.setdefault(column, set()).add("field_forward_filled")
    for column in BTC_FILL_FIELDS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").ffill(limit=3)
            notes.setdefault(column, set()).add("field_forward_filled_max_3d")


def _compute_missing_features(output: pd.DataFrame, notes: dict[str, set[str]]) -> None:
    _numeric_all(output)
    _compute_change(output, "dff", [30, 90], notes)
    _compute_zscore(output, "dff", notes)
    if "dff" in output.columns:
        output["policy_rate_change_30d"] = output.get("policy_rate_change_30d", output["dff_change_30d"])
        output["policy_rate_change_90d"] = output.get("policy_rate_change_90d", output["dff_change_90d"])
    for column in ["net_liquidity", "tga_billion"]:
        _compute_change(output, column, [7, 30, 90] if column == "net_liquidity" else [30, 90], notes)
        _compute_pct(output, column, [30, 90], notes)
        _compute_zscore(output, column, notes)
        _compute_slope(output, column, [30, 90], notes)
    _compute_change(output, "m2", [30, 90], notes)
    _compute_pct(output, "m2", [90], notes)
    if "m2" in output.columns:
        _assign_if_missing(output, "m2_yoy", pct_change(output["m2"], 365), notes)
        _assign_if_missing(output, "m2_3m_change", pct_change(output["m2"], 90), notes)
    if {"us10y", "us2y"}.issubset(output.columns):
        _assign_if_missing(output, "yield_curve_10y_2y", output["us10y"] - output["us2y"], notes)
    if {"us10y", "us10y_real"}.issubset(output.columns):
        _assign_if_missing(output, "breakeven_10y_proxy", output["us10y"] - output["us10y_real"], notes)
    for column in ["us2y", "us10y", "us10y_real", "vix", "hy_oas"]:
        _compute_change(output, column, [30, 90] if column in {"vix", "hy_oas"} else [30], notes)
        if column in {"us10y_real", "vix", "hy_oas"}:
            _compute_zscore(output, column, notes)
    _compute_stablecoin(output, notes)
    _compute_btc(output, notes)
    _compute_transmission(output, notes)
    for column in ["fed_target_upper", "fed_target_lower", "stablecoin_liquidity_score"]:
        if column not in output.columns:
            output[column] = pd.NA
            notes.setdefault(column, set()).add("field_missing")


def _compute_stablecoin(output: pd.DataFrame, notes: dict[str, set[str]]) -> None:
    column = "total_stablecoin_supply"
    _compute_change(output, column, [7, 30, 90], notes)
    _compute_pct(output, column, [30, 90], notes)
    _compute_zscore(output, column, notes)
    _compute_slope(output, column, [30, 90], notes)


def _compute_btc(output: pd.DataFrame, notes: dict[str, set[str]]) -> None:
    if "btc_price" not in output.columns:
        return
    for window in [7, 30, 90, 180]:
        _assign_if_missing(output, f"btc_return_{window}d", pct_change(output["btc_price"], window), notes)
    for window in [30, 90, 180]:
        value = output["btc_price"].shift(-window) / output["btc_price"] - 1
        _assign_if_missing(output, f"btc_forward_return_{window}d", value, notes)


def _compute_transmission(output: pd.DataFrame, notes: dict[str, set[str]]) -> None:
    if {"total_stablecoin_supply", "btc_market_cap"}.issubset(output.columns):
        _assign_if_missing(output, "stablecoin_to_btc_mcap", safe_divide(output["total_stablecoin_supply"], output["btc_market_cap"]), notes)
        _assign_if_missing(output, "btc_to_stablecoin_ratio", safe_divide(output["btc_market_cap"], output["total_stablecoin_supply"]), notes)
    if "total_stablecoin_supply" in output.columns:
        _assign_if_missing(output, "stablecoin_supply_growth_30d", pct_change(output["total_stablecoin_supply"], 30), notes)
        _assign_if_missing(output, "stablecoin_supply_growth_90d", pct_change(output["total_stablecoin_supply"], 90), notes)
    if "net_liquidity" in output.columns:
        _assign_if_missing(output, "net_liquidity_growth_30d", pct_change(output["net_liquidity"], 30), notes)
        _assign_if_missing(output, "net_liquidity_growth_90d", pct_change(output["net_liquidity"], 90), notes)
    if {"net_liquidity_growth_30d", "stablecoin_supply_growth_30d"}.issubset(output.columns):
        _assign_if_missing(output, "liquidity_transmission_gap_30d", output["net_liquidity_growth_30d"] - output["stablecoin_supply_growth_30d"], notes)
    if {"net_liquidity_growth_90d", "stablecoin_supply_growth_90d"}.issubset(output.columns):
        _assign_if_missing(output, "liquidity_transmission_gap_90d", output["net_liquidity_growth_90d"] - output["stablecoin_supply_growth_90d"], notes)
    for prefix, left in [("stablecoin_btc", "stablecoin_supply_growth"), ("net_liquidity_btc", "net_liquidity_growth")]:
        for window in [30, 90]:
            left_col = f"{left}_{window}d"
            right_col = f"btc_return_{window}d"
            if {left_col, right_col}.issubset(output.columns):
                _assign_if_missing(output, f"{prefix}_growth_gap_{window}d", output[left_col] - output[right_col], notes)
    for column in [
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
    ]:
        _compute_zscore(output, column, notes)
    if {
        "net_liquidity_growth_90d",
        "stablecoin_supply_growth_90d",
        "btc_return_90d",
    }.issubset(output.columns):
        output["transmission_phase"] = output.apply(_infer_transmission_phase, axis=1)
        notes.setdefault("transmission_phase", set()).add("field_computed")


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


def _compute_change(output: pd.DataFrame, column: str, windows: list[int], notes: dict[str, set[str]]) -> None:
    if column not in output.columns:
        return
    for window in windows:
        _assign_if_missing(output, f"{column}_change_{window}d", rolling_change(output[column], window), notes)


def _compute_pct(output: pd.DataFrame, column: str, windows: list[int], notes: dict[str, set[str]]) -> None:
    if column not in output.columns:
        return
    for window in windows:
        _assign_if_missing(output, f"{column}_pct_change_{window}d", pct_change(output[column], window), notes)


def _compute_zscore(output: pd.DataFrame, column: str, notes: dict[str, set[str]]) -> None:
    if column not in output.columns:
        return
    _assign_if_missing(output, f"{column}_zscore_252d", rolling_zscore(pd.to_numeric(output[column], errors="coerce"), 252), notes)


def _compute_slope(output: pd.DataFrame, column: str, windows: list[int], notes: dict[str, set[str]]) -> None:
    if column not in output.columns:
        return
    for window in windows:
        _assign_if_missing(output, f"{column}_slope_{window}d", rolling_change(output[column], window), notes)


def _assign_if_missing(output: pd.DataFrame, column: str, value: Any, notes: dict[str, set[str]]) -> None:
    if column not in output.columns:
        output[column] = value
        notes.setdefault(column, set()).add("field_computed")
        return
    before_nulls = int(output[column].isna().sum())
    output[column] = output[column].combine_first(value)
    if int(output[column].isna().sum()) < before_nulls:
        notes.setdefault(column, set()).add("field_computed")


def _numeric_all(output: pd.DataFrame) -> None:
    for column in output.columns:
        if column == "date" or column == "transmission_phase":
            continue
        converted = pd.to_numeric(output[column], errors="coerce")
        if converted.notna().any() or output[column].isna().all():
            output[column] = converted


def _finalize_order(output: pd.DataFrame) -> pd.DataFrame:
    output = output.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    first = ["date"]
    rest = [column for column in output.columns if column not in first]
    return output[first + rest].reset_index(drop=True)


def _read_optional_csv(path: Path, missing_inputs: list[str]) -> pd.DataFrame | None:
    if not path.exists():
        missing_inputs.append(str(path))
        return None
    return pd.read_csv(path)


def _source_group(column: str) -> str:
    if column in SOURCE_GROUPS:
        return SOURCE_GROUPS[column]
    for prefix, group in [
        ("net_liquidity", "usd_liquidity"),
        ("tga_billion", "usd_liquidity"),
        ("total_stablecoin_supply", "stablecoin_liquidity"),
        ("btc_", "btc_market"),
        ("stablecoin_", "transmission"),
        ("liquidity_transmission", "transmission"),
    ]:
        if column.startswith(prefix):
            return group
    return "unknown"


def _date_for_index(features: pd.DataFrame, index: Any) -> str | None:
    if pd.isna(index):
        return None
    return pd.Timestamp(features.loc[index, "date"]).strftime("%Y-%m-%d")


def _latest_value(series: pd.Series) -> Any:
    values = series.dropna()
    if values.empty:
        return None
    value = values.iloc[-1]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def _latest_non_null(data: pd.DataFrame, column: str) -> Any:
    if column not in data.columns:
        return None
    values = data[column].dropna()
    if values.empty:
        return None
    return values.iloc[-1]


def _stat(series: pd.Series, name: str) -> float | None:
    values = series.dropna()
    if values.empty:
        return None
    return float(getattr(values, name)())


def _json_value(value: Any) -> float | str | bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str | bool):
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
