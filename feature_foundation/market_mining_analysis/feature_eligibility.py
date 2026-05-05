from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from market_mining_analysis.macro_feature_consolidation import build_feature_audit

ELIGIBILITY_NOTES = [
    "Feature eligibility review completed in Step 5B.",
    "Current-only fields are excluded from scoring.",
    "Forward-looking return fields are excluded from live scoring and reserved for research/backtesting.",
    "Placeholder score fields are excluded until implemented.",
]

CORE_MACRO = {
    "dff",
    "dff_change_30d",
    "m2_yoy",
    "us10y_real",
    "us10y_real_change_30d",
    "yield_curve_10y_2y",
    "vix",
    "hy_oas",
}
CORE_LIQUIDITY = {
    "net_liquidity",
    "net_liquidity_change_30d",
    "net_liquidity_change_90d",
    "net_liquidity_pct_change_30d",
    "net_liquidity_pct_change_90d",
    "net_liquidity_zscore_252d",
    "tga_billion",
    "tga_billion_change_30d",
    "total_stablecoin_supply",
    "total_stablecoin_supply_change_30d",
    "total_stablecoin_supply_change_90d",
    "total_stablecoin_supply_zscore_252d",
}
CORE_RISK = {
    "vix",
    "vix_change_30d",
    "hy_oas",
    "hy_oas_change_30d",
    "us10y_real",
    "us10y_real_change_30d",
}
CORE_CRYPTO = {
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
}
SCORING_TYPES = {"absolute_change", "pct_change", "zscore", "ratio", "return", "raw_level"}
FORCED_EXCLUDE_SCORING = {
    "date",
    "transmission_phase",
    "integration_phase",
    "stablecoin_liquidity_score",
    "usdt_history_available",
    "usdc_history_available",
}


@dataclass
class FeatureEligibilityResult:
    eligibility: pd.DataFrame
    scoring: pd.DataFrame
    research: pd.DataFrame
    dashboard: pd.DataFrame
    excluded: pd.DataFrame
    summary: dict[str, Any]
    warnings: list[str]


def review_feature_eligibility(
    features: pd.DataFrame,
    audit: pd.DataFrame | None = None,
) -> FeatureEligibilityResult:
    """Classify each feature for scoring, research, dashboard, or exclusion."""

    if audit is None or audit.empty:
        audit = build_feature_audit(features)
    latest_date = pd.to_datetime(features["date"], errors="coerce").max()
    rows = []
    for column in features.columns:
        audit_row = _audit_row(audit, column)
        rows.append(_classify_feature(column, features[column], audit_row))
    eligibility = pd.DataFrame(rows)
    scoring = _sort_candidates(eligibility[eligibility["usable_for_scoring"]])
    research = eligibility[eligibility["usable_for_research"]].sort_values("feature")
    dashboard = eligibility[eligibility["usable_for_dashboard"]].sort_values("feature")
    excluded = eligibility[
        (~eligibility["usable_for_scoring"])
        & (~eligibility["usable_for_research"])
        & (~eligibility["usable_for_dashboard"])
        | eligibility["eligibility_status"].astype(str).str.startswith("excluded_")
    ].sort_values("feature")
    summary = _build_summary(latest_date, eligibility, scoring)
    return FeatureEligibilityResult(
        eligibility=eligibility.sort_values("feature").reset_index(drop=True),
        scoring=scoring.reset_index(drop=True),
        research=research.reset_index(drop=True),
        dashboard=dashboard.reset_index(drop=True),
        excluded=excluded.reset_index(drop=True),
        summary=summary,
        warnings=summary["warnings"],
    )


def run_feature_eligibility_review(
    features_path: Path,
    audit_path: Path,
    output_path: Path,
    scoring_output_path: Path,
    research_output_path: Path,
    dashboard_output_path: Path,
    excluded_output_path: Path,
    summary_output_path: Path,
    snapshot_path: Path,
) -> FeatureEligibilityResult:
    """Run feature eligibility review from disk and write all outputs."""

    features = pd.read_csv(features_path)
    audit = pd.read_csv(audit_path) if audit_path.exists() else build_feature_audit(features)
    result = review_feature_eligibility(features, audit)
    for path, data in [
        (output_path, result.eligibility),
        (scoring_output_path, result.scoring),
        (research_output_path, result.research),
        (dashboard_output_path, result.dashboard),
        (excluded_output_path, result.excluded),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path, index=False)
    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_output_path.write_text(json.dumps(result.summary, indent=2), encoding="utf-8")
    update_snapshot_with_eligibility(snapshot_path, result.summary)
    return result


def update_snapshot_with_eligibility(snapshot_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    """Update macro snapshot with feature eligibility summary and notes."""

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    updated = dict(snapshot)
    updated["feature_eligibility_summary"] = {
        key: summary[key]
        for key in [
            "scoring_ready_count",
            "research_only_count",
            "dashboard_only_count",
            "excluded_count",
            "current_only_count",
            "placeholder_count",
            "forward_looking_count",
        ]
    }
    notes = _dedupe_notes(list(updated.get("notes") or []))
    for note in ELIGIBILITY_NOTES:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    return updated


def _classify_feature(feature: str, series: pd.Series, audit_row: dict[str, Any]) -> dict[str, Any]:
    non_null_count = int(audit_row.get("non_null_count", series.notna().sum()) or 0)
    null_ratio = float(audit_row.get("null_ratio", series.isna().mean()) or 0)
    latest_value = audit_row.get("latest_value")
    latest_missing = _is_missing(latest_value)
    history_days = _history_days(audit_row)
    feature_type = infer_feature_type(feature, series, null_ratio)
    is_forward = "forward_return" in feature or "forward_log_return" in feature
    is_phase = feature_type == "phase_label"
    is_placeholder = feature_type == "score_placeholder"
    is_current_only = non_null_count <= 5 and not latest_missing and feature != "date"
    is_date = feature == "date"
    source_group = infer_source_group(feature)
    is_core_macro = feature in CORE_MACRO
    is_core_liquidity = feature in CORE_LIQUIDITY
    is_core_risk = feature in CORE_RISK
    is_core_crypto = feature in CORE_CRYPTO

    min_history_days = _minimum_scoring_history_days(source_group)
    has_sufficient_scoring_history = (
        history_days >= min_history_days and non_null_count >= min_history_days
    )
    missing_is_acceptable = null_ratio <= 0.40 or has_sufficient_scoring_history
    usable_for_research = (
        not is_date
        and non_null_count >= 30
        and not is_placeholder
        and not is_current_only
    ) or (is_forward and non_null_count >= 30) or is_phase
    usable_for_dashboard = (not latest_missing and non_null_count > 0) or is_phase or is_current_only
    forced_excluded = feature in FORCED_EXCLUDE_SCORING or is_forward or is_phase or is_placeholder
    usable_for_scoring = (
        not is_date
        and not forced_excluded
        and not is_current_only
        and missing_is_acceptable
        and has_sufficient_scoring_history
        and not latest_missing
        and feature_type in SCORING_TYPES
    )
    status = _eligibility_status(
        feature=feature,
        is_forward=is_forward,
        is_placeholder=is_placeholder,
        is_current_only=is_current_only,
        usable_for_scoring=usable_for_scoring,
        usable_for_research=usable_for_research,
        usable_for_dashboard=usable_for_dashboard,
        null_ratio=null_ratio,
        latest_missing=latest_missing,
    )
    return {
        "feature": feature,
        "source_group": source_group,
        "feature_type": feature_type,
        "non_null_count": non_null_count,
        "null_ratio": null_ratio,
        "first_valid_date": audit_row.get("first_valid_date"),
        "last_valid_date": audit_row.get("last_valid_date"),
        "latest_value": latest_value,
        "history_days": history_days,
        "usable_for_scoring": usable_for_scoring,
        "usable_for_research": usable_for_research,
        "usable_for_dashboard": usable_for_dashboard,
        "is_current_only": is_current_only,
        "is_placeholder": is_placeholder,
        "is_forward_looking": is_forward,
        "is_label_or_phase": is_phase,
        "is_core_macro": is_core_macro,
        "is_core_liquidity": is_core_liquidity,
        "is_core_risk": is_core_risk,
        "is_core_crypto": is_core_crypto,
        "eligibility_status": status,
        "exclusion_reason": _exclusion_reason(status),
        "notes": _feature_notes(audit_row.get("notes"), status),
    }


def infer_source_group(feature: str) -> str:
    if "forward_return" in feature or "forward_log_return" in feature:
        return "future_return"
    if any(token in feature for token in ["transmission", "stablecoin_btc_growth_gap", "net_liquidity_btc_growth_gap", "stablecoin_to_btc_mcap", "btc_to_stablecoin_ratio"]):
        return "transmission"
    if any(token in feature for token in ["btc_price", "btc_market_cap", "btc_volume", "btc_return"]):
        return "btc_market"
    if any(token in feature for token in ["stablecoin", "usdt", "usdc"]):
        return "stablecoin_liquidity"
    if any(token in feature for token in ["vix", "hy_oas"]):
        return "risk_appetite"
    if any(token in feature for token in ["us2y", "us10y", "yield_curve", "breakeven", "real"]):
        return "rates"
    if "m2" in feature:
        return "money_supply"
    if any(token in feature for token in ["net_liquidity", "tga", "walcl", "rrp", "usd_liquidity_proxy"]):
        return "usd_liquidity"
    if any(token in feature for token in ["dff", "fed_target", "policy_rate"]):
        return "fed_policy"
    if feature == "date":
        return "unknown"
    return "unknown"


def _minimum_scoring_history_days(source_group: str) -> int:
    if source_group in {"btc_market", "transmission"}:
        return 180
    return 365


def infer_feature_type(feature: str, series: pd.Series, null_ratio: float) -> str:
    if feature == "date":
        return "date"
    if "forward_return" in feature or "forward_log_return" in feature:
        return "forward_return"
    if "phase" in feature:
        return "phase_label"
    if "score" in feature and (null_ratio >= 0.95 or feature == "stablecoin_liquidity_score"):
        return "score_placeholder"
    if "zscore" in feature:
        return "zscore"
    if "slope" in feature:
        return "slope"
    if "pct_change" in feature or "growth" in feature:
        return "pct_change"
    if feature.endswith(("_change_7d", "_change_30d", "_change_90d", "_change_180d")):
        return "absolute_change"
    if any(token in feature for token in ["ratio", "dominance", "stablecoin_to_btc_mcap", "btc_to_stablecoin_ratio"]):
        return "ratio"
    if "return" in feature:
        return "return"
    if "available" in feature or "positive" in feature or "zero_cross" in feature:
        return "boolean_flag"
    non_null = series.dropna()
    if not non_null.empty and non_null.map(lambda value: isinstance(value, bool)).all():
        return "boolean_flag"
    return "raw_level"


def _eligibility_status(
    feature: str,
    is_forward: bool,
    is_placeholder: bool,
    is_current_only: bool,
    usable_for_scoring: bool,
    usable_for_research: bool,
    usable_for_dashboard: bool,
    null_ratio: float,
    latest_missing: bool,
) -> str:
    if feature == "date":
        return "excluded_date"
    if is_forward:
        return "excluded_forward_looking"
    if is_placeholder:
        return "excluded_placeholder"
    if is_current_only:
        return "excluded_current_only"
    if usable_for_scoring:
        return "scoring_ready"
    if usable_for_research:
        return "research_only"
    if usable_for_dashboard:
        return "dashboard_only"
    if null_ratio > 0.80:
        return "excluded_too_sparse"
    if latest_missing:
        return "excluded_missing_latest"
    return "excluded_unknown"


def _exclusion_reason(status: str) -> str:
    return {
        "scoring_ready": "",
        "excluded_date": "date column",
        "excluded_forward_looking": "forward-looking return; allowed only for research/backtesting",
        "excluded_current_only": "current-only field; insufficient history",
        "excluded_placeholder": "placeholder field with insufficient real values",
        "excluded_too_sparse": "too many missing values",
        "excluded_missing_latest": "latest value missing",
        "research_only": "usable for research but not suitable for live scoring",
        "dashboard_only": "usable for dashboard display only",
        "excluded_unknown": "not enough information for scoring eligibility",
    }.get(status, "not enough information for scoring eligibility")


def _build_summary(latest_date: pd.Timestamp, eligibility: pd.DataFrame, scoring: pd.DataFrame) -> dict[str, Any]:
    warnings = []
    if eligibility["is_current_only"].any():
        warnings.append("USDT/USDC fields are current-only and excluded from scoring.")
    if eligibility["is_forward_looking"].any():
        warnings.append("Forward return fields are excluded from live scoring.")
    if eligibility["is_placeholder"].any():
        warnings.append("Placeholder score fields are excluded.")
    status = eligibility["eligibility_status"]
    return {
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "total_features": int(len(eligibility)),
        "scoring_ready_count": int((status == "scoring_ready").sum()),
        "research_only_count": int((status == "research_only").sum()),
        "dashboard_only_count": int((status == "dashboard_only").sum()),
        "excluded_count": int(status.astype(str).str.startswith("excluded_").sum()),
        "current_only_count": int(eligibility["is_current_only"].sum()),
        "placeholder_count": int(eligibility["is_placeholder"].sum()),
        "forward_looking_count": int(eligibility["is_forward_looking"].sum()),
        "core_scoring_features": scoring[
            scoring[["is_core_macro", "is_core_liquidity", "is_core_risk", "is_core_crypto"]].any(axis=1)
        ]["feature"].tolist(),
        "warnings": warnings,
    }


def _sort_candidates(data: pd.DataFrame) -> pd.DataFrame:
    sort_columns = [
        "is_core_macro",
        "is_core_liquidity",
        "is_core_risk",
        "is_core_crypto",
        "source_group",
        "feature",
    ]
    return data.sort_values(sort_columns, ascending=[False, False, False, False, True, True])


def _audit_row(audit: pd.DataFrame, feature: str) -> dict[str, Any]:
    if "feature" not in audit.columns:
        return {}
    rows = audit[audit["feature"] == feature]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _history_days(audit_row: dict[str, Any]) -> int:
    first = pd.to_datetime(audit_row.get("first_valid_date"), errors="coerce")
    last = pd.to_datetime(audit_row.get("last_valid_date"), errors="coerce")
    if pd.isna(first) or pd.isna(last):
        return 0
    return int((last - first).days) + 1


def _feature_notes(existing: Any, status: str) -> str:
    notes = [] if _is_missing(existing) else [str(existing)]
    if status != "scoring_ready":
        reason = _exclusion_reason(status)
        if reason:
            notes.append(reason)
    return ";".join(note for note in notes if note)


def _is_missing(value: Any) -> bool:
    return value is None or pd.isna(value) or value == ""


def _dedupe_notes(notes: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for note in notes:
        if note in seen:
            continue
        seen.add(note)
        output.append(note)
    return output
