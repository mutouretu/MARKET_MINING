from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

REGIME_NOTES = [
    "Market regime v0.1 is rule-based and explanatory.",
    "Regime labels describe macro/crypto environment, not trading signals.",
    "Allowed and forbidden actions are descriptive guidelines, not automated execution rules.",
]

SCORE_COLUMNS = [
    "fed_policy_score",
    "usd_liquidity_score",
    "rates_pressure_score",
    "risk_appetite_score",
    "stablecoin_liquidity_score",
    "btc_market_score",
    "macro_liquidity_score",
    "score_coverage_ratio",
]

OPTIONAL_FEATURE_COLUMNS = [
    "net_liquidity_change_30d",
    "net_liquidity_change_90d",
    "total_stablecoin_supply_change_30d",
    "total_stablecoin_supply_change_90d",
    "btc_return_30d",
    "btc_return_90d",
    "liquidity_transmission_gap_30d",
    "liquidity_transmission_gap_90d",
    "stablecoin_btc_growth_gap_30d",
    "stablecoin_btc_growth_gap_90d",
    "net_liquidity_btc_growth_gap_30d",
    "net_liquidity_btc_growth_gap_90d",
    "transmission_phase",
]


class RegimeError(ValueError):
    """Raised when market regime construction cannot proceed."""


def detect_regime_for_row(row: pd.Series) -> dict[str, Any]:
    """Detect one row's market regime using ordered rule priority."""

    triggered = _triggered_regimes(row)
    regime_name = triggered[0] if triggered else "neutral"
    result = _regime_payload(regime_name, row)
    result["regime_confidence"] = _regime_confidence(row, result["regime_score"], len(triggered))
    return result


def build_market_regime(
    scores: pd.DataFrame,
    features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build daily market regime table from macro scores and optional feature context."""

    if "date" not in scores.columns:
        raise RegimeError("scores must include date")
    missing_scores = [column for column in SCORE_COLUMNS if column not in scores.columns]
    if missing_scores:
        raise RegimeError(f"scores missing required columns: {', '.join(missing_scores)}")

    data = scores[["date", *SCORE_COLUMNS]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    if features is not None and not features.empty and "date" in features.columns:
        feature_columns = [
            column for column in OPTIONAL_FEATURE_COLUMNS if column in features.columns
        ]
        feature_frame = features[["date", *feature_columns]].copy()
        feature_frame["date"] = pd.to_datetime(feature_frame["date"], errors="coerce")
        data = data.merge(feature_frame, on="date", how="left")
    data = data.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    rows = []
    for _, row in data.iterrows():
        detected = detect_regime_for_row(row)
        rows.append({**row.to_dict(), **detected})
    regime = pd.DataFrame(rows)
    ordered = [
        "date",
        "regime",
        "regime_score",
        "regime_confidence",
        *SCORE_COLUMNS[:-1],
        "score_coverage_ratio",
        "primary_driver",
        "secondary_driver",
        "risk_level",
        "allowed_actions",
        "forbidden_actions",
        "reason",
    ]
    regime = regime[[column for column in ordered if column in regime.columns]]
    return add_regime_transitions(regime)


def add_regime_transitions(regime_df: pd.DataFrame) -> pd.DataFrame:
    """Add previous regime, change flag, and current run duration."""

    data = regime_df.copy()
    data["previous_regime"] = data["regime"].shift(1)
    data["regime_changed"] = data["regime"] != data["previous_regime"]
    if not data.empty:
        data.loc[data.index[0], "regime_changed"] = True
    group_id = data["regime_changed"].cumsum()
    data["regime_duration_days"] = data.groupby(group_id).cumcount() + 1
    return data


def build_regime_transitions(regime_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "date",
        "previous_regime",
        "regime",
        "regime_score",
        "regime_confidence",
        "macro_liquidity_score",
        "primary_driver",
        "secondary_driver",
        "risk_level",
        "reason",
    ]
    transitions = regime_df[regime_df["regime_changed"]].copy()
    return transitions[[column for column in columns if column in transitions.columns]]


def build_regime_audit(regime_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for regime_name, group in regime_df.groupby("regime", dropna=False):
        rows.append(
            {
                "regime": regime_name,
                "count": int(len(group)),
                "first_date": _date_value(group["date"].min()),
                "last_date": _date_value(group["date"].max()),
                "avg_regime_score": _mean(group, "regime_score"),
                "avg_confidence": _mean(group, "regime_confidence"),
                "avg_macro_liquidity_score": _mean(group, "macro_liquidity_score"),
                "avg_usd_liquidity_score": _mean(group, "usd_liquidity_score"),
                "avg_risk_appetite_score": _mean(group, "risk_appetite_score"),
                "avg_stablecoin_liquidity_score": _mean(
                    group, "stablecoin_liquidity_score"
                ),
                "avg_btc_market_score": _mean(group, "btc_market_score"),
            }
        )
    return pd.DataFrame(rows).sort_values("regime").reset_index(drop=True)


def update_snapshot_with_regime(snapshot_path: Path, regime_df: pd.DataFrame) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    updated = dict(snapshot)
    latest = regime_df.sort_values("date").iloc[-1]
    key_features = dict(updated.get("key_features") or {})
    key_features.update(
        {
            "market_regime": latest["regime"],
            "regime_score": _json_value(latest["regime_score"]),
            "regime_confidence": _json_value(latest["regime_confidence"]),
            "risk_level": latest["risk_level"],
            "primary_driver": latest["primary_driver"],
            "secondary_driver": latest["secondary_driver"],
        }
    )
    updated["key_features"] = key_features
    updated["regime_summary"] = {
        "date": _date_value(latest["date"]),
        "regime": latest["regime"],
        "regime_score": _json_value(latest["regime_score"]),
        "regime_confidence": _json_value(latest["regime_confidence"]),
        "risk_level": latest["risk_level"],
        "primary_driver": latest["primary_driver"],
        "secondary_driver": latest["secondary_driver"],
        "allowed_actions": latest["allowed_actions"],
        "forbidden_actions": latest["forbidden_actions"],
        "reason": latest["reason"],
    }
    notes = _dedupe_notes(list(updated.get("notes") or []))
    for note in REGIME_NOTES:
        if note not in notes:
            notes.append(note)
    updated["notes"] = notes
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    return updated


def run_market_regime_update(
    scores_path: Path,
    features_path: Path,
    output_path: Path,
    transitions_output_path: Path,
    audit_output_path: Path,
    latest_output_path: Path,
    snapshot_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scores = pd.read_csv(scores_path)
    features = pd.read_csv(features_path) if features_path.exists() else None
    regime = build_market_regime(scores, features)
    transitions = build_regime_transitions(regime)
    audit = build_regime_audit(regime)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    regime.to_csv(output_path, index=False)
    transitions_output_path.parent.mkdir(parents=True, exist_ok=True)
    transitions.to_csv(transitions_output_path, index=False)
    audit_output_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_output_path, index=False)
    latest_output_path.parent.mkdir(parents=True, exist_ok=True)
    _latest_snapshot(regime).to_csv(latest_output_path, index=False)
    update_snapshot_with_regime(snapshot_path, regime)
    return regime, transitions, audit


def _triggered_regimes(row: pd.Series) -> list[str]:
    checks = [
        ("risk_off_deleveraging", _is_risk_off_deleveraging(row)),
        ("liquidity_drain", _is_liquidity_drain(row)),
        ("macro_tightening", _is_macro_tightening(row)),
        ("risk_on_expansion", _is_risk_on_expansion(row)),
        ("liquidity_recovery", _is_liquidity_recovery(row)),
        ("crypto_liquidity_accumulating", _is_crypto_liquidity_accumulating(row)),
        ("macro_stabilization", _is_macro_stabilization(row)),
    ]
    return [name for name, triggered in checks if triggered]


def _is_risk_off_deleveraging(row: pd.Series) -> bool:
    risk = _num(row, "risk_appetite_score")
    btc = _num(row, "btc_market_score")
    macro = _num(row, "macro_liquidity_score")
    return (risk < 35 and btc < 45 and macro < 50) or (risk < 30 and macro < 55)


def _is_liquidity_drain(row: pd.Series) -> bool:
    usd = _num(row, "usd_liquidity_score")
    macro = _num(row, "macro_liquidity_score")
    liquidity_negative = _num(row, "net_liquidity_change_30d") < 0 or _num(
        row, "net_liquidity_change_90d"
    ) < 0
    return usd < 40 and macro < 60 and liquidity_negative


def _is_macro_tightening(row: pd.Series) -> bool:
    fed = _num(row, "fed_policy_score")
    rates = _num(row, "rates_pressure_score")
    macro = _num(row, "macro_liquidity_score")
    return (fed < 40 and rates < 45) or (rates < 35 and macro < 55)


def _is_risk_on_expansion(row: pd.Series) -> bool:
    return (
        _num(row, "macro_liquidity_score") >= 70
        and _num(row, "usd_liquidity_score") >= 60
        and _num(row, "risk_appetite_score") >= 60
        and _num(row, "stablecoin_liquidity_score") >= 60
        and _num(row, "btc_market_score") >= 55
    )


def _is_liquidity_recovery(row: pd.Series) -> bool:
    return (
        _num(row, "macro_liquidity_score") >= 60
        and _num(row, "usd_liquidity_score") >= 55
        and _num(row, "risk_appetite_score") >= 55
        and _num(row, "rates_pressure_score") >= 45
    )


def _is_crypto_liquidity_accumulating(row: pd.Series) -> bool:
    stable = _num(row, "stablecoin_liquidity_score")
    btc = _num(row, "btc_market_score")
    macro = _num(row, "macro_liquidity_score")
    usd = _num(row, "usd_liquidity_score")
    transmission_phase = str(row.get("transmission_phase", ""))
    transmission_confirmed = (
        transmission_phase == "crypto_liquidity_accumulating"
        or stable - usd >= 20
        or (stable >= 75 and usd < 55)
    )
    return stable >= 65 and btc >= 45 and macro >= 45 and transmission_confirmed


def _is_macro_stabilization(row: pd.Series) -> bool:
    macro = _num(row, "macro_liquidity_score")
    risk = _num(row, "risk_appetite_score")
    usd = _num(row, "usd_liquidity_score")
    rates = _num(row, "rates_pressure_score")
    return (45 <= macro < 60 and risk >= 50) or (macro >= 50 and usd >= 40 and rates >= 40)


def _regime_payload(regime_name: str, row: pd.Series) -> dict[str, Any]:
    payloads = {
        "risk_off_deleveraging": {
            "risk_level": "high",
            "primary_driver": "risk_appetite",
            "secondary_driver": "btc_market",
            "allowed_actions": "observe, reduce risk, avoid aggressive long exposure",
            "forbidden_actions": "avoid leverage expansion, avoid chasing rebounds",
            "score_fields": [
                ("risk_appetite_score", True),
                ("btc_market_score", True),
                ("macro_liquidity_score", True),
            ],
        },
        "liquidity_drain": {
            "risk_level": "medium_high",
            "primary_driver": "usd_liquidity",
            "secondary_driver": "net_liquidity",
            "allowed_actions": "observe, keep defensive stance, wait for liquidity stabilization",
            "forbidden_actions": "avoid aggressive accumulation, avoid high leverage",
            "score_fields": [("usd_liquidity_score", True), ("macro_liquidity_score", True)],
        },
        "macro_tightening": {
            "risk_level": "medium_high",
            "primary_driver": "fed_policy_or_rates",
            "secondary_driver": "rates_pressure",
            "allowed_actions": "monitor, reduce sensitivity to risk assets, avoid early risk-on assumptions",
            "forbidden_actions": "avoid treating rebounds as full cycle recovery",
            "score_fields": [("fed_policy_score", True), ("rates_pressure_score", True)],
        },
        "risk_on_expansion": {
            "risk_level": "medium",
            "primary_driver": "broad_liquidity",
            "secondary_driver": "risk_appetite_and_crypto",
            "allowed_actions": "risk-on monitoring, allow trend participation in upper layers",
            "forbidden_actions": "avoid ignoring overheating and leverage risk",
            "score_fields": [
                ("macro_liquidity_score", False),
                ("usd_liquidity_score", False),
                ("risk_appetite_score", False),
                ("stablecoin_liquidity_score", False),
                ("btc_market_score", False),
            ],
        },
        "liquidity_recovery": {
            "risk_level": "medium",
            "primary_driver": "usd_liquidity",
            "secondary_driver": "risk_appetite",
            "allowed_actions": "prepare for risk-on transition, monitor confirmation",
            "forbidden_actions": "avoid overcommitting before BTC and stablecoin confirmation",
            "score_fields": [
                ("macro_liquidity_score", False),
                ("usd_liquidity_score", False),
                ("risk_appetite_score", False),
                ("rates_pressure_score", False),
            ],
        },
        "crypto_liquidity_accumulating": {
            "risk_level": "medium",
            "primary_driver": "stablecoin_liquidity",
            "secondary_driver": "transmission",
            "allowed_actions": "monitor accumulation, watch for BTC trend confirmation, avoid assuming full macro risk-on",
            "forbidden_actions": "avoid treating stablecoin expansion as standalone buy signal",
            "score_fields": [
                ("stablecoin_liquidity_score", False),
                ("btc_market_score", False),
                ("macro_liquidity_score", False),
            ],
        },
        "macro_stabilization": {
            "risk_level": "medium",
            "primary_driver": "macro_score",
            "secondary_driver": "risk_appetite",
            "allowed_actions": "observe recovery, prepare scenarios, wait for stronger confirmation",
            "forbidden_actions": "avoid aggressive positioning based on partial improvement",
            "score_fields": [
                ("macro_liquidity_score", False),
                ("risk_appetite_score", False),
                ("usd_liquidity_score", False),
                ("rates_pressure_score", False),
            ],
        },
        "neutral": {
            "risk_level": "medium",
            "primary_driver": "mixed",
            "secondary_driver": "none",
            "allowed_actions": "observe, collect data, avoid strong assumptions",
            "forbidden_actions": "avoid overfitting weak signals",
            "score_fields": [("macro_liquidity_score", False)],
        },
    }
    config = payloads[regime_name]
    score = _regime_score(row, config["score_fields"])
    return {
        "regime": regime_name,
        "regime_score": score,
        "primary_driver": config["primary_driver"],
        "secondary_driver": config["secondary_driver"],
        "risk_level": config["risk_level"],
        "allowed_actions": config["allowed_actions"],
        "forbidden_actions": config["forbidden_actions"],
        "reason": _reason(row, regime_name),
    }


def _regime_score(row: pd.Series, fields: list[tuple[str, bool]]) -> float:
    values = []
    for field, invert in fields:
        value = _num_or_none(row, field)
        if value is None:
            continue
        values.append(100 - value if invert else value)
    if not values:
        return 50.0
    return _clip(float(sum(values) / len(values)), 0, 100)


def _regime_confidence(row: pd.Series, regime_score: float, triggered_count: int) -> float:
    base = _num(row, "score_coverage_ratio", default=0.0)
    bonus = 0.15 if regime_score >= 70 else 0.10 if regime_score >= 60 else 0.0
    penalty = 0.10 if triggered_count > 1 else 0.0
    key_scores = [
        "macro_liquidity_score",
        "usd_liquidity_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
    ]
    if any(_num_or_none(row, field) is None for field in key_scores):
        penalty += 0.20
    return _clip(base + bonus - penalty, 0, 1)


def _reason(row: pd.Series, regime_name: str) -> str:
    parts = [
        f"macro_liquidity_score={_fmt(row, 'macro_liquidity_score')}",
        f"usd_liquidity_score={_fmt(row, 'usd_liquidity_score')}",
        f"risk_appetite_score={_fmt(row, 'risk_appetite_score')}",
        f"rates_pressure_score={_fmt(row, 'rates_pressure_score')}",
        f"stablecoin_liquidity_score={_fmt(row, 'stablecoin_liquidity_score')}",
        f"btc_market_score={_fmt(row, 'btc_market_score')}",
    ]
    if "net_liquidity_change_30d" in row:
        parts.append(f"net_liquidity_change_30d={_fmt(row, 'net_liquidity_change_30d')}")
    if "net_liquidity_change_90d" in row:
        parts.append(f"net_liquidity_change_90d={_fmt(row, 'net_liquidity_change_90d')}")
    if "transmission_phase" in row and not pd.isna(row.get("transmission_phase")):
        parts.append(f"transmission_phase={row.get('transmission_phase')}")
    return f"{regime_name}: " + "; ".join(parts)


def _latest_snapshot(regime_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "date",
        "regime",
        "regime_score",
        "regime_confidence",
        "risk_level",
        "primary_driver",
        "secondary_driver",
        "macro_liquidity_score",
        "usd_liquidity_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "allowed_actions",
        "forbidden_actions",
        "reason",
    ]
    return regime_df.sort_values("date").tail(1)[columns]


def _mean(data: pd.DataFrame, column: str) -> float | None:
    if column not in data.columns:
        return None
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _num(row: pd.Series, field: str, default: float = float("nan")) -> float:
    value = _num_or_none(row, field)
    return default if value is None else value


def _num_or_none(row: pd.Series, field: str) -> float | None:
    value = row.get(field)
    if value is None or pd.isna(value):
        return None
    return float(value)


def _fmt(row: pd.Series, field: str) -> str:
    value = _num_or_none(row, field)
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _json_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _date_value(value: Any) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _dedupe_notes(notes: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for note in notes:
        if note in seen:
            continue
        seen.add(note)
        output.append(note)
    return output
