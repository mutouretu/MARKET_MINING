from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.feature_utils import absolute_change, percent_change, rolling_zscore

SERIES_REGISTRY: dict[str, dict[str, str]] = {
    "BAMLH0A0HYM2": {
        "label": "High Yield OAS",
        "group": "risk_appetite",
        "unit": "percent",
        "bullish_when": "down",
    },
    "DFF": {
        "label": "Effective Federal Funds Rate",
        "group": "fed_policy",
        "unit": "percent",
        "bullish_when": "down",
    },
    "DFII10": {
        "label": "10Y Real Yield",
        "group": "rates",
        "unit": "percent",
        "bullish_when": "down",
    },
    "DGS2": {
        "label": "2Y Treasury Yield",
        "group": "rates",
        "unit": "percent",
        "bullish_when": "down",
    },
    "DGS10": {
        "label": "10Y Treasury Yield",
        "group": "rates",
        "unit": "percent",
        "bullish_when": "down",
    },
    "M2SL": {
        "label": "M2 Money Supply",
        "group": "usd_liquidity",
        "unit": "billion_usd",
        "bullish_when": "up",
    },
    "RRPONTSYD": {
        "label": "Overnight Reverse Repo",
        "group": "usd_liquidity",
        "unit": "billion_usd",
        "bullish_when": "down",
    },
    "VIXCLS": {
        "label": "VIX",
        "group": "risk_appetite",
        "unit": "index",
        "bullish_when": "down",
    },
    "WALCL": {
        "label": "Fed Balance Sheet",
        "group": "usd_liquidity",
        "unit": "million_usd",
        "bullish_when": "up",
    },
}

BASE_COLUMNS = [
    "DFF",
    "WALCL",
    "WALCL_BILLION",
    "RRPONTSYD",
    "M2SL",
    "DGS2",
    "DGS10",
    "DFII10",
    "VIXCLS",
    "BAMLH0A0HYM2",
]

DERIVED_FEATURE_SERIES = BASE_COLUMNS + ["usd_liquidity_proxy_no_tga"]

NO_TGA_NOTE = (
    "usd_liquidity_proxy_no_tga excludes TGA and should not be treated as full net liquidity."
)


@dataclass(frozen=True)
class FredMacroAnalysisResult:
    input_dir: Path
    output_dir: Path
    loaded_series: list[str]
    missing_series: list[str]
    wide_path: Path
    features_path: Path
    summary_path: Path
    snapshot_path: Path


def load_fred_series(path: Path, series_id: str) -> pd.DataFrame:
    """Load and normalize one local FRED CSV series."""

    raw = pd.read_csv(path, na_values=[".", "", "NA"])
    columns_by_lower = {column.lower(): column for column in raw.columns}
    if "date" not in columns_by_lower or "value" not in columns_by_lower:
        msg = f"{path} must contain date and value columns"
        raise ValueError(msg)

    normalized = raw[[columns_by_lower["date"], columns_by_lower["value"]]].copy()
    normalized.columns = ["date", "value"]
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized["value"] = pd.to_numeric(normalized["value"], errors="coerce")
    normalized = normalized.dropna(subset=["date"])
    normalized = normalized.sort_values("date")
    normalized = normalized.drop_duplicates(subset=["date"], keep="last")
    normalized["series_id"] = series_id
    return normalized[["date", "series_id", "value"]].reset_index(drop=True)


def build_fred_wide_table(input_dir: Path) -> pd.DataFrame:
    """Build a daily wide table from locally available FRED CSV files."""

    series_frames: list[pd.DataFrame] = []
    for series_id in SERIES_REGISTRY:
        path = input_dir / f"{series_id}.csv"
        if not path.exists():
            continue
        series = load_fred_series(path=path, series_id=series_id)
        series_frames.append(series[["date", "value"]].rename(columns={"value": series_id}))

    if not series_frames:
        msg = f"No registered FRED CSV files found in {input_dir}"
        raise ValueError(msg)

    wide = series_frames[0]
    for frame in series_frames[1:]:
        wide = wide.merge(frame, on="date", how="outer")

    wide = wide.sort_values("date").set_index("date")
    daily_index = pd.date_range(start=wide.index.min(), end=wide.index.max(), freq="D")
    wide = wide.reindex(daily_index)
    wide.index.name = "date"
    wide = wide.ffill()

    if "WALCL" in wide.columns:
        wide["WALCL_BILLION"] = wide["WALCL"] / 1000

    ordered_columns = [column for column in BASE_COLUMNS if column in wide.columns]
    remaining_columns = [column for column in wide.columns if column not in ordered_columns]
    wide = wide[ordered_columns + remaining_columns]
    return wide.reset_index()


def build_macro_features(wide: pd.DataFrame) -> pd.DataFrame:
    """Build preliminary macro features from a FRED wide table."""

    features = wide.copy()
    if "DGS10" in features.columns and "DGS2" in features.columns:
        features["yield_curve_10y_2y"] = features["DGS10"] - features["DGS2"]
    if "DGS10" in features.columns and "DFII10" in features.columns:
        features["breakeven_10y_proxy"] = features["DGS10"] - features["DFII10"]
    if "WALCL_BILLION" in features.columns and "RRPONTSYD" in features.columns:
        # This intentionally excludes Treasury General Account. It is not full net liquidity.
        features["usd_liquidity_proxy_no_tga"] = (
            features["WALCL_BILLION"] - features["RRPONTSYD"]
        )

    for series_id in DERIVED_FEATURE_SERIES:
        if series_id not in features.columns:
            continue
        series = pd.to_numeric(features[series_id], errors="coerce")
        features[f"{series_id}_change_7d"] = absolute_change(series, 7)
        features[f"{series_id}_change_30d"] = absolute_change(series, 30)
        features[f"{series_id}_change_90d"] = absolute_change(series, 90)
        features[f"{series_id}_pct_change_30d"] = percent_change(series, 30)
        features[f"{series_id}_pct_change_90d"] = percent_change(series, 90)
        features[f"{series_id}_zscore_252d"] = rolling_zscore(series, 252)
        features[f"{series_id}_slope_30d"] = absolute_change(series, 30)
        features[f"{series_id}_slope_90d"] = absolute_change(series, 90)

    return features


def infer_btc_implication(series_id: str, change_30d: float | None) -> str:
    """Infer a simple BTC directional implication from 30-day macro change."""

    registry = SERIES_REGISTRY.get(series_id)
    if registry is None or pd.isna(change_30d) or change_30d == 0:
        return "neutral"

    bullish_when = registry["bullish_when"]
    if bullish_when == "up":
        return "positive_for_btc" if change_30d > 0 else "negative_for_btc"
    if bullish_when == "down":
        return "positive_for_btc" if change_30d < 0 else "negative_for_btc"
    return "neutral"


def build_series_summary(
    input_dir: Path,
    wide: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """Build per-series summary rows from raw and derived FRED data."""

    latest = features.sort_values("date").iloc[-1]
    rows: list[dict[str, Any]] = []
    for series_id, metadata in SERIES_REGISTRY.items():
        if series_id not in wide.columns:
            continue

        raw_path = input_dir / f"{series_id}.csv"
        raw_series = load_fred_series(raw_path, series_id) if raw_path.exists() else pd.DataFrame()
        change_30d = _to_json_value(latest.get(f"{series_id}_change_30d"))
        btc_implication = infer_btc_implication(series_id, change_30d)

        rows.append(
            {
                "series_id": series_id,
                "label": metadata["label"],
                "group": metadata["group"],
                "unit": metadata["unit"],
                "first_date": _format_date(raw_series["date"].min()) if not raw_series.empty else None,
                "last_date": _format_date(raw_series["date"].max()) if not raw_series.empty else None,
                "latest_value": _to_json_value(latest.get(series_id)),
                "observations": int(raw_series["value"].notna().sum()) if not raw_series.empty else 0,
                "missing_values_raw": int(raw_series["value"].isna().sum())
                if not raw_series.empty
                else 0,
                "missing_values_after_ffill": int(wide[series_id].isna().sum()),
                "change_30d": change_30d,
                "change_90d": _to_json_value(latest.get(f"{series_id}_change_90d")),
                "pct_change_90d": _to_json_value(latest.get(f"{series_id}_pct_change_90d")),
                "zscore_252d": _to_json_value(latest.get(f"{series_id}_zscore_252d")),
                "bullish_when": metadata["bullish_when"],
                "btc_implication": btc_implication,
                "status": _status_from_implication(btc_implication),
            }
        )

    return pd.DataFrame(rows)


def build_latest_snapshot(features: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    """Build the latest macro snapshot JSON payload."""

    latest = features.sort_values("date").iloc[-1]
    groups: dict[str, list[dict[str, Any]]] = {}
    for _, row in summary.iterrows():
        item = {
            "series_id": row["series_id"],
            "label": row["label"],
            "group": row["group"],
            "latest_value": _to_json_value(row["latest_value"]),
            "latest_date": _format_date(latest["date"]),
            "change_30d": _to_json_value(row["change_30d"]),
            "change_90d": _to_json_value(row["change_90d"]),
            "zscore_252d": _to_json_value(row["zscore_252d"]),
            "bullish_when": row["bullish_when"],
            "btc_implication": row["btc_implication"],
        }
        groups.setdefault(row["group"], []).append(item)

    return {
        "latest_date": _format_date(latest["date"]),
        "series_count": int(len(summary)),
        "groups": groups,
        "key_features": {
            "yield_curve_10y_2y": _to_json_value(latest.get("yield_curve_10y_2y")),
            "breakeven_10y_proxy": _to_json_value(latest.get("breakeven_10y_proxy")),
            "usd_liquidity_proxy_no_tga": _to_json_value(
                latest.get("usd_liquidity_proxy_no_tga")
            ),
            "usd_liquidity_proxy_no_tga_change_30d": _to_json_value(
                latest.get("usd_liquidity_proxy_no_tga_change_30d")
            ),
        },
        "notes": [NO_TGA_NOTE],
    }


def run_fred_macro_analysis(input_dir: Path, output_dir: Path) -> FredMacroAnalysisResult:
    """Run the Step 2.5 FRED macro analysis pipeline and write outputs."""

    resolved_input_dir = _resolve_input_dir(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    loaded_series = [
        series_id
        for series_id in SERIES_REGISTRY
        if (resolved_input_dir / f"{series_id}.csv").exists()
    ]
    missing_series = [series_id for series_id in SERIES_REGISTRY if series_id not in loaded_series]

    wide = build_fred_wide_table(resolved_input_dir)
    features = build_macro_features(wide)
    summary = build_series_summary(resolved_input_dir, wide, features)
    snapshot = build_latest_snapshot(features, summary)

    wide_path = output_dir / "fred_macro_wide_daily.csv"
    features_path = output_dir / "macro_features_daily.csv"
    summary_path = output_dir / "fred_series_summary.csv"
    snapshot_path = output_dir / "macro_snapshot_latest.json"

    wide.to_csv(wide_path, index=False)
    features.to_csv(features_path, index=False)
    summary.to_csv(summary_path, index=False)
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return FredMacroAnalysisResult(
        input_dir=resolved_input_dir,
        output_dir=output_dir,
        loaded_series=loaded_series,
        missing_series=missing_series,
        wide_path=wide_path,
        features_path=features_path,
        summary_path=summary_path,
        snapshot_path=snapshot_path,
    )


def _resolve_input_dir(input_dir: Path) -> Path:
    return input_dir


def _status_from_implication(implication: str) -> str:
    if implication == "positive_for_btc":
        return "improving"
    if implication == "negative_for_btc":
        return "deteriorating"
    return "neutral"


def _format_date(value: Any) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _to_json_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
