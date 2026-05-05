from __future__ import annotations

import pandas as pd

from market_mining_analysis.regime import build_market_regime, detect_regime_for_row


def _row(**overrides: object) -> pd.Series:
    values = {
        "fed_policy_score": 55.0,
        "usd_liquidity_score": 50.0,
        "rates_pressure_score": 50.0,
        "risk_appetite_score": 50.0,
        "stablecoin_liquidity_score": 50.0,
        "btc_market_score": 50.0,
        "macro_liquidity_score": 50.0,
        "score_coverage_ratio": 1.0,
        "net_liquidity_change_30d": 1.0,
        "net_liquidity_change_90d": 1.0,
        "transmission_phase": "neutral",
    }
    values.update(overrides)
    return pd.Series(values)


def _assert_payload(payload: dict) -> None:
    assert 0 <= payload["regime_score"] <= 100
    assert 0 <= payload["regime_confidence"] <= 1
    assert payload["reason"]
    assert payload["allowed_actions"]
    assert payload["forbidden_actions"]


def test_risk_off_deleveraging_rule() -> None:
    payload = detect_regime_for_row(
        _row(risk_appetite_score=25, btc_market_score=40, macro_liquidity_score=45)
    )
    assert payload["regime"] == "risk_off_deleveraging"
    _assert_payload(payload)


def test_liquidity_drain_rule() -> None:
    payload = detect_regime_for_row(
        _row(
            usd_liquidity_score=35,
            macro_liquidity_score=55,
            net_liquidity_change_30d=-1,
        )
    )
    assert payload["regime"] == "liquidity_drain"
    _assert_payload(payload)


def test_macro_tightening_rule() -> None:
    payload = detect_regime_for_row(
        _row(fed_policy_score=35, rates_pressure_score=40, macro_liquidity_score=54)
    )
    assert payload["regime"] == "macro_tightening"
    _assert_payload(payload)


def test_risk_on_expansion_rule() -> None:
    payload = detect_regime_for_row(
        _row(
            macro_liquidity_score=75,
            usd_liquidity_score=65,
            risk_appetite_score=65,
            stablecoin_liquidity_score=70,
            btc_market_score=60,
        )
    )
    assert payload["regime"] == "risk_on_expansion"
    _assert_payload(payload)


def test_liquidity_recovery_rule() -> None:
    payload = detect_regime_for_row(
        _row(
            macro_liquidity_score=62,
            usd_liquidity_score=56,
            risk_appetite_score=58,
            rates_pressure_score=48,
        )
    )
    assert payload["regime"] == "liquidity_recovery"
    _assert_payload(payload)


def test_crypto_liquidity_accumulating_rule() -> None:
    payload = detect_regime_for_row(
        _row(
            stablecoin_liquidity_score=80,
            btc_market_score=50,
            macro_liquidity_score=50,
            usd_liquidity_score=45,
            transmission_phase="crypto_liquidity_accumulating",
        )
    )
    assert payload["regime"] == "crypto_liquidity_accumulating"
    _assert_payload(payload)


def test_macro_stabilization_rule() -> None:
    payload = detect_regime_for_row(
        _row(macro_liquidity_score=52, risk_appetite_score=55, usd_liquidity_score=45)
    )
    assert payload["regime"] == "macro_stabilization"
    _assert_payload(payload)


def test_neutral_fallback() -> None:
    payload = detect_regime_for_row(
        _row(macro_liquidity_score=42, risk_appetite_score=45, usd_liquidity_score=45)
    )
    assert payload["regime"] == "neutral"
    _assert_payload(payload)


def test_build_market_regime_from_scores_only() -> None:
    scores = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=2),
            "fed_policy_score": [55, 55],
            "usd_liquidity_score": [50, 35],
            "rates_pressure_score": [50, 50],
            "risk_appetite_score": [50, 50],
            "stablecoin_liquidity_score": [50, 50],
            "btc_market_score": [50, 50],
            "macro_liquidity_score": [50, 55],
            "score_coverage_ratio": [1.0, 1.0],
        }
    )
    regime = build_market_regime(scores)

    assert "regime" in regime.columns
    assert "regime_duration_days" in regime.columns
