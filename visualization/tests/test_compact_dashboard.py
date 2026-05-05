from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_visualization.build_compact_dashboard import (
    build_compact_dashboard,
    build_compact_dashboard_html,
    load_compact_dashboard_inputs,
    write_compact_dashboard,
)


def _write_inputs(path: Path, include_regime: bool = True, include_contrib: bool = True) -> None:
    path.mkdir()
    snapshot = {
        "key_features": {
            "net_liquidity": 4500.0,
            "net_liquidity_change_30d": -100.0,
            "net_liquidity_change_90d": 50.0,
            "tga_billion_change_30d": 20.0,
            "total_stablecoin_supply": 200_000_000_000.0,
            "total_stablecoin_supply_change_30d": 3_000_000_000.0,
            "total_stablecoin_supply_change_90d": 10_000_000_000.0,
            "btc_price": 100000.0,
            "btc_return_30d": 0.1,
            "btc_return_90d": 0.2,
            "stablecoin_to_btc_mcap": 0.2,
            "liquidity_transmission_gap_90d": -0.01,
            "stablecoin_btc_growth_gap_90d": 0.03,
            "net_liquidity_btc_growth_gap_90d": -0.02,
            "transmission_phase": "crypto_liquidity_accumulating",
        },
        "score_summary": {
            "macro_liquidity_score": 54.0,
            "fed_policy_score": 53.0,
            "usd_liquidity_score": 35.0,
            "rates_pressure_score": 47.0,
            "risk_appetite_score": 66.0,
            "stablecoin_liquidity_score": 82.0,
            "btc_market_score": 60.0,
            "score_coverage_ratio": 1.0,
        },
    }
    if include_regime:
        snapshot["regime_summary"] = {
            "date": "2026-05-04",
            "regime": "liquidity_drain",
            "regime_score": 55.0,
            "regime_confidence": 0.9,
            "risk_level": "medium_high",
            "primary_driver": "usd_liquidity",
            "secondary_driver": "net_liquidity",
            "allowed_actions": "observe",
            "forbidden_actions": "avoid leverage",
            "reason": "liquidity drain reason",
        }
    (path / "macro_snapshot_latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
    dates = pd.date_range("2026-01-01", periods=200)
    pd.DataFrame(
        {
            "date": dates,
            "macro_liquidity_score": range(200),
            "fed_policy_score": 50.0,
            "usd_liquidity_score": 40.0,
            "rates_pressure_score": 45.0,
            "risk_appetite_score": 60.0,
            "stablecoin_liquidity_score": 70.0,
            "btc_market_score": 55.0,
            "score_coverage_ratio": 1.0,
        }
    ).to_csv(path / "macro_scores_daily.csv", index=False)
    pd.DataFrame(
        {
            "date": ["2026-05-04"],
            "macro_liquidity_score": [54.0],
            "fed_policy_score": [53.0],
            "usd_liquidity_score": [35.0],
            "rates_pressure_score": [47.0],
            "risk_appetite_score": [66.0],
            "stablecoin_liquidity_score": [82.0],
            "btc_market_score": [60.0],
            "score_coverage_ratio": [1.0],
        }
    ).to_csv(path / "macro_score_latest_snapshot.csv", index=False)
    if include_contrib:
        pd.DataFrame(
            {
                "date": ["2026-05-04"] * 3,
                "score_name": ["macro_liquidity_score", "usd_liquidity_score", "risk_appetite_score"],
                "feature": ["stablecoin_liquidity_score", "net_liquidity_change_30d", "vix_change_30d"],
                "feature_value": [82.0, -100.0, -5.0],
                "feature_score": [82.0, 20.0, 80.0],
                "weight": [0.15, 0.2, 0.25],
                "weighted_contribution": [12.3, 4.0, 20.0],
                "available": [True, True, True],
            }
        ).to_csv(path / "macro_score_contributions_daily.csv", index=False)
    if include_regime:
        pd.DataFrame(
            {
                "date": ["2026-05-04"],
                "regime": ["liquidity_drain"],
                "regime_score": [55.0],
                "regime_confidence": [0.9],
                "risk_level": ["medium_high"],
                "primary_driver": ["usd_liquidity"],
                "secondary_driver": ["net_liquidity"],
                "allowed_actions": ["observe"],
                "forbidden_actions": ["avoid leverage"],
                "reason": ["liquidity drain reason"],
            }
        ).to_csv(path / "market_regime_latest_snapshot.csv", index=False)
    pd.DataFrame(
        {
            "date": dates,
            "regime": "liquidity_drain",
            "regime_score": 55.0,
        }
    ).to_csv(path / "market_regime_daily.csv", index=False)
    pd.DataFrame(
        {
            "date": dates,
            "net_liquidity_change_90d": range(200),
            "total_stablecoin_supply_change_90d": range(200),
        }
    ).to_csv(path / "macro_features_daily.csv", index=False)


def test_build_compact_dashboard_html_contains_sections(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    _write_inputs(analysis_dir)
    inputs = load_compact_dashboard_inputs(analysis_dir)

    html = build_compact_dashboard_html(inputs)

    assert "Current Market State" in html
    assert "Macro Scores" in html
    assert "Liquidity Core" in html
    assert "BTC / Transmission" in html
    assert "Top Drivers and Drags" in html


def test_missing_regime_does_not_crash(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    _write_inputs(analysis_dir, include_regime=False)
    inputs = load_compact_dashboard_inputs(analysis_dir)

    html = build_compact_dashboard_html(inputs)

    assert "Market regime not available. Run Step 7 first." in html


def test_missing_contributions_does_not_crash(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    _write_inputs(analysis_dir, include_contrib=False)
    inputs = load_compact_dashboard_inputs(analysis_dir)

    html = build_compact_dashboard_html(inputs)

    assert "Score contributions not available. Run Step 6 first." in html


def test_write_and_build_compact_dashboard(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    output = tmp_path / "dashboard_compact.html"
    _write_inputs(analysis_dir)

    inputs = build_compact_dashboard(analysis_dir, output)

    assert output.exists()
    assert inputs.loaded_files
    write_compact_dashboard("<html></html>", output)
    assert output.read_text(encoding="utf-8") == "<html></html>"
