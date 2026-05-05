from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

SCORE_NOTES = [
    "Macro scoring v0.1 uses rule-based directional scoring.",
    "Scores are explanatory indicators, not trading signals.",
    "50 is neutral; higher is more favorable for BTC/risk assets.",
]


@dataclass(frozen=True)
class FeatureRule:
    feature: str
    weight: float
    method: str
    bullish_when: str = "up"
    scale: float | None = None
    sensitivity: float = 15.0
    notes: str = ""


SCORE_RULES: dict[str, list[FeatureRule]] = {
    "fed_policy_score": [
        FeatureRule("dff_change_30d", 0.35, "change", "down", 0.25),
        FeatureRule("dff_change_90d", 0.35, "change", "down", 0.50),
        FeatureRule("dff_zscore_252d", 0.30, "zscore", "down"),
    ],
    "usd_liquidity_score": [
        FeatureRule("net_liquidity_change_30d", 0.20, "change", "up", 150),
        FeatureRule("net_liquidity_change_90d", 0.25, "change", "up", 300),
        FeatureRule("net_liquidity_pct_change_30d", 0.15, "pct_change", "up", 0.03),
        FeatureRule("net_liquidity_pct_change_90d", 0.15, "pct_change", "up", 0.06),
        FeatureRule("net_liquidity_zscore_252d", 0.15, "zscore", "up"),
        FeatureRule("tga_billion_change_30d", 0.05, "change", "down", 100),
        FeatureRule("tga_billion_change_90d", 0.05, "change", "down", 200),
    ],
    "rates_pressure_score": [
        FeatureRule("us10y_real_change_30d", 0.35, "change", "down", 0.20),
        FeatureRule("us10y_real_zscore_252d", 0.30, "zscore", "down"),
        FeatureRule("us10y_change_30d", 0.20, "change", "down", 0.25),
        FeatureRule("us2y_change_30d", 0.15, "change", "down", 0.25),
    ],
    "risk_appetite_score": [
        FeatureRule("vix_change_30d", 0.25, "change", "down", 8),
        FeatureRule("vix_change_90d", 0.15, "change", "down", 12),
        FeatureRule("vix_zscore_252d", 0.15, "zscore", "down"),
        FeatureRule("hy_oas_change_30d", 0.25, "change", "down", 0.75),
        FeatureRule("hy_oas_change_90d", 0.10, "change", "down", 1.25),
        FeatureRule("hy_oas_zscore_252d", 0.10, "zscore", "down"),
    ],
    "stablecoin_liquidity_score": [
        FeatureRule("total_stablecoin_supply_change_30d", 0.20, "change", "up", 5_000_000_000),
        FeatureRule("total_stablecoin_supply_change_90d", 0.25, "change", "up", 15_000_000_000),
        FeatureRule("total_stablecoin_supply_pct_change_30d", 0.20, "pct_change", "up", 0.02),
        FeatureRule("total_stablecoin_supply_pct_change_90d", 0.20, "pct_change", "up", 0.05),
        FeatureRule("total_stablecoin_supply_zscore_252d", 0.15, "zscore", "up"),
    ],
    "btc_market_score": [
        FeatureRule("btc_return_30d", 0.20, "neutral", notes="neutral-preferred short-term trend"),
        FeatureRule("btc_return_90d", 0.25, "pct_change", "up", 0.25),
        FeatureRule("stablecoin_to_btc_mcap", 0.15, "ratio_zscore", "up"),
        FeatureRule("stablecoin_btc_growth_gap_90d", 0.20, "pct_change", "up", 0.20),
        FeatureRule("net_liquidity_btc_growth_gap_90d", 0.20, "pct_change", "up", 0.20),
    ],
}

COMPOSITE_WEIGHTS = {
    "fed_policy_score": 0.15,
    "usd_liquidity_score": 0.25,
    "rates_pressure_score": 0.20,
    "risk_appetite_score": 0.15,
    "stablecoin_liquidity_score": 0.15,
    "btc_market_score": 0.10,
}


def clip_0_100(x: Any) -> Any:
    """Clip scalar or Series to the 0-100 score range."""

    if isinstance(x, pd.Series):
        return x.clip(0, 100)
    if pd.isna(x):
        return x
    return min(max(float(x), 0), 100)


def score_from_zscore(
    z: pd.Series,
    bullish_when: str,
    sensitivity: float = 15.0,
) -> pd.Series:
    raw = 50 + sensitivity * pd.to_numeric(z, errors="coerce")
    if bullish_when == "down":
        raw = 50 - sensitivity * pd.to_numeric(z, errors="coerce")
    return clip_0_100(raw)


def score_from_change(x: pd.Series, bullish_when: str, scale: float) -> pd.Series:
    series = pd.to_numeric(x, errors="coerce")
    raw = 50 + 50 * (series / scale).map(_tanh)
    if bullish_when == "down":
        raw = 50 - 50 * (series / scale).map(_tanh)
    return clip_0_100(raw)


def score_from_pct_change(x: pd.Series, bullish_when: str, scale: float) -> pd.Series:
    return score_from_change(x, bullish_when=bullish_when, scale=scale)


def neutral_preferred_score(
    x: pd.Series,
    center: float = 0.0,
    tolerance: float = 0.05,
    max_penalty: float = 40.0,
) -> pd.Series:
    distance = (pd.to_numeric(x, errors="coerce") - center).abs()
    return clip_0_100(100 - max_penalty * (distance / tolerance).map(_tanh))


def build_macro_scores(
    features: pd.DataFrame,
    scoring_candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build daily score table and long-form feature contributions."""

    if "date" not in features.columns:
        raise ValueError("features must include date")
    allowed_features = set(scoring_candidates.loc[scoring_candidates["usable_for_scoring"], "feature"])
    data = features.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    scores = pd.DataFrame({"date": data["date"]})
    contribution_frames = []
    for score_name, rules in SCORE_RULES.items():
        score_series, contributions = _build_subscore(data, score_name, rules, allowed_features)
        scores[score_name] = score_series
        contribution_frames.append(contributions)
    scores["macro_liquidity_score"], composite = _build_composite_score(scores)
    scores["score_coverage_ratio"] = scores[list(COMPOSITE_WEIGHTS)].notna().sum(axis=1) / len(
        COMPOSITE_WEIGHTS
    )
    contribution_frames.append(composite)
    contributions_df = pd.concat(contribution_frames, ignore_index=True)
    return scores, contributions_df


def build_score_audit(scores: pd.DataFrame, contributions: pd.DataFrame) -> pd.DataFrame:
    """Build one-row-per-score audit table."""

    rows = []
    for score_name in list(SCORE_RULES) + ["macro_liquidity_score"]:
        score = pd.to_numeric(scores[score_name], errors="coerce")
        contrib = contributions[contributions["score_name"] == score_name]
        target_features = sorted(contrib["feature"].dropna().unique())
        available_features = sorted(
            contrib.loc[
                contrib["notes"].astype(str) != "missing or not scoring-eligible",
                "feature",
            ]
            .dropna()
            .unique()
        )
        missing_features = sorted(set(target_features) - set(available_features))
        rows.append(
            {
                "score_name": score_name,
                "target_features": ",".join(target_features),
                "available_features": ",".join(available_features),
                "missing_features": ",".join(missing_features),
                "coverage_ratio": len(available_features) / len(target_features)
                if target_features
                else 0,
                "mean": _stat(score, "mean"),
                "std": _stat(score, "std"),
                "min": _stat(score, "min"),
                "max": _stat(score, "max"),
                "latest_value": _latest_value(score),
                "latest_date": scores["date"].max().strftime("%Y-%m-%d"),
                "notes": "missing feature" if missing_features else "",
            }
        )
    return pd.DataFrame(rows)


def update_snapshot_with_scores(snapshot_path: Path, scores: pd.DataFrame) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    updated = dict(snapshot)
    latest = scores.sort_values("date").iloc[-1]
    score_fields = list(COMPOSITE_WEIGHTS) + ["macro_liquidity_score", "score_coverage_ratio"]
    key_features = dict(updated.get("key_features") or {})
    score_summary = {}
    for field in score_fields:
        value = _json_value(latest.get(field))
        key_features[field] = value
        score_summary[field] = value
    updated["key_features"] = key_features
    updated["score_summary"] = score_summary
    notes = _dedupe_notes(list(updated.get("notes") or []))
    for note in SCORE_NOTES:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    return updated


def run_macro_scoring(
    features_path: Path,
    candidates_path: Path,
    output_path: Path,
    contributions_output_path: Path,
    audit_output_path: Path,
    latest_output_path: Path,
    snapshot_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not candidates_path.exists():
        raise FileNotFoundError(
            f"{candidates_path} not found. Run Step 5B review-feature-eligibility first."
        )
    features = pd.read_csv(features_path)
    candidates = pd.read_csv(candidates_path)
    scores, contributions = build_macro_scores(features, candidates)
    audit = build_score_audit(scores, contributions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_path, index=False)
    contributions_output_path.parent.mkdir(parents=True, exist_ok=True)
    contributions.to_csv(contributions_output_path, index=False)
    audit_output_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_output_path, index=False)
    latest_output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.sort_values("date").tail(1).to_csv(latest_output_path, index=False)
    update_snapshot_with_scores(snapshot_path, scores)
    return scores, contributions, audit


def _build_subscore(
    data: pd.DataFrame,
    score_name: str,
    rules: list[FeatureRule],
    allowed_features: set[str],
) -> tuple[pd.Series, pd.DataFrame]:
    score_parts: list[pd.Series] = []
    available_weight_parts: list[pd.Series] = []
    contribution_rows = []
    for rule in rules:
        eligible = rule.feature in allowed_features and rule.feature in data.columns
        value = (
            pd.to_numeric(data[rule.feature], errors="coerce")
            if rule.feature in data
            else pd.Series(pd.NA, index=data.index)
        )
        feature_score = _score_feature(data, rule) if eligible else pd.Series(pd.NA, index=data.index)
        feature_score = pd.to_numeric(feature_score, errors="coerce")
        available = eligible & feature_score.notna()
        weight_series = pd.Series(rule.weight, index=data.index).where(available, 0.0)
        weighted_contribution = (feature_score * weight_series).fillna(0.0)
        score_parts.append(weighted_contribution)
        available_weight_parts.append(weight_series)
        contribution_rows.append(
            pd.DataFrame(
                {
                    "date": data["date"],
                    "score_name": score_name,
                    "feature": rule.feature,
                    "feature_value": value,
                    "feature_score": feature_score,
                    "weight": weight_series,
                    "weighted_contribution": weighted_contribution,
                    "available": available,
                    "notes": "" if eligible else "missing or not scoring-eligible",
                }
            )
        )
    weighted_sum = pd.concat(score_parts, axis=1).sum(axis=1)
    weight_sum = pd.concat(available_weight_parts, axis=1).sum(axis=1)
    score = weighted_sum / weight_sum.where(weight_sum != 0)
    return clip_0_100(score), pd.concat(contribution_rows, ignore_index=True)


def _score_feature(data: pd.DataFrame, rule: FeatureRule) -> pd.Series:
    if rule.method == "zscore":
        return score_from_zscore(data[rule.feature], rule.bullish_when, rule.sensitivity)
    if rule.method == "change":
        return score_from_change(data[rule.feature], rule.bullish_when, rule.scale or 1)
    if rule.method == "pct_change":
        return score_from_pct_change(data[rule.feature], rule.bullish_when, rule.scale or 1)
    if rule.method == "neutral":
        return neutral_preferred_score(
            data[rule.feature], center=0.05, tolerance=0.20, max_penalty=35
        )
    if rule.method == "ratio_zscore":
        zscore_column = f"{rule.feature}_zscore_252d"
        if zscore_column in data.columns:
            return score_from_zscore(data[zscore_column], rule.bullish_when)
        value = pd.to_numeric(data[rule.feature], errors="coerce")
        mean = value.rolling(window=252, min_periods=30).mean()
        std = value.rolling(window=252, min_periods=30).std()
        zscore = (value - mean) / std.replace(0, pd.NA)
        return score_from_zscore(zscore, rule.bullish_when)
    return pd.Series(pd.NA, index=data.index)


def _build_composite_score(scores: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    parts = []
    weights = []
    rows = []
    for score_name, weight in COMPOSITE_WEIGHTS.items():
        available = scores[score_name].notna()
        weight_series = pd.Series(weight, index=scores.index).where(available, 0.0)
        weighted_contribution = (scores[score_name] * weight_series).fillna(0.0)
        parts.append(weighted_contribution)
        weights.append(weight_series)
        rows.append(
            pd.DataFrame(
                {
                    "date": scores["date"],
                    "score_name": "macro_liquidity_score",
                    "feature": score_name,
                    "feature_value": scores[score_name],
                    "feature_score": scores[score_name],
                    "weight": weight_series,
                    "weighted_contribution": weighted_contribution,
                    "available": available,
                    "notes": "",
                }
            )
        )
    weighted_sum = pd.concat(parts, axis=1).sum(axis=1)
    weight_sum = pd.concat(weights, axis=1).sum(axis=1)
    return clip_0_100(weighted_sum / weight_sum.where(weight_sum != 0)), pd.concat(
        rows, ignore_index=True
    )


def _tanh(value: Any) -> float | Any:
    if pd.isna(value):
        return pd.NA
    import math

    return math.tanh(float(value))


def _stat(series: pd.Series, name: str) -> float | None:
    values = series.dropna()
    if values.empty:
        return None
    return float(getattr(values, name)())


def _latest_value(series: pd.Series) -> float | None:
    values = series.dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def _json_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
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
