from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.regime import (
    add_regime_transitions,
    build_regime_audit,
    build_regime_transitions,
    run_market_regime_update,
)


def _regime_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=5),
            "regime": ["neutral", "neutral", "liquidity_drain", "liquidity_drain", "neutral"],
            "regime_score": [50, 51, 65, 66, 50],
            "regime_confidence": [0.8, 0.8, 0.9, 0.9, 0.8],
            "macro_liquidity_score": [50, 51, 45, 44, 50],
            "usd_liquidity_score": [50, 50, 35, 35, 50],
            "risk_appetite_score": [50, 50, 50, 50, 50],
            "stablecoin_liquidity_score": [50, 50, 50, 50, 50],
            "btc_market_score": [50, 50, 50, 50, 50],
            "primary_driver": ["mixed", "mixed", "usd_liquidity", "usd_liquidity", "mixed"],
            "secondary_driver": ["none", "none", "net_liquidity", "net_liquidity", "none"],
            "risk_level": ["medium", "medium", "medium_high", "medium_high", "medium"],
            "allowed_actions": ["observe"] * 5,
            "forbidden_actions": ["avoid overfitting"] * 5,
            "reason": ["reason"] * 5,
        }
    )


def test_add_regime_transitions_fields() -> None:
    data = add_regime_transitions(_regime_df())

    assert pd.isna(data.iloc[0]["previous_regime"])
    assert bool(data.iloc[2]["regime_changed"])
    assert data["regime_duration_days"].tolist() == [1, 2, 1, 2, 1]


def test_transitions_only_changed_rows() -> None:
    data = add_regime_transitions(_regime_df())
    transitions = build_regime_transitions(data)

    assert len(transitions) == 3
    assert transitions["regime_changed"].empty if "regime_changed" in transitions else True


def test_regime_audit_one_row_per_regime() -> None:
    audit = build_regime_audit(add_regime_transitions(_regime_df()))

    assert set(audit["regime"]) == {"neutral", "liquidity_drain"}


def test_run_market_regime_update_outputs_latest(tmp_path: Path) -> None:
    scores = tmp_path / "scores.csv"
    features = tmp_path / "features.csv"
    output = tmp_path / "regime.csv"
    transitions = tmp_path / "transitions.csv"
    audit = tmp_path / "audit.csv"
    latest = tmp_path / "latest.csv"
    snapshot = tmp_path / "snapshot.json"
    score_df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3),
            "fed_policy_score": [55, 55, 55],
            "usd_liquidity_score": [50, 35, 35],
            "rates_pressure_score": [50, 50, 50],
            "risk_appetite_score": [50, 50, 50],
            "stablecoin_liquidity_score": [50, 50, 50],
            "btc_market_score": [50, 50, 50],
            "macro_liquidity_score": [50, 55, 55],
            "score_coverage_ratio": [1.0, 1.0, 1.0],
        }
    )
    feature_df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3),
            "net_liquidity_change_30d": [1, -1, -1],
        }
    )
    score_df.to_csv(scores, index=False)
    feature_df.to_csv(features, index=False)
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")

    run_market_regime_update(scores, features, output, transitions, audit, latest, snapshot)

    latest_df = pd.read_csv(latest)
    assert len(latest_df) == 1
    assert latest_df.iloc[0]["date"] == "2025-01-03"
    updated = json.loads(snapshot.read_text(encoding="utf-8"))
    assert "existing note" in updated["notes"]
    assert "regime_summary" in updated
