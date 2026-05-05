from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_visualization.build_dashboard import (
    build_dashboard,
    build_dashboard_html,
    build_macro_scores_section,
)
from monitoring.tests.test_dashboard_transmission import _features, _snapshot, _summary_df


def _features_with_scores() -> pd.DataFrame:
    data = _features()
    for column in [
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "macro_liquidity_score",
    ]:
        data[column] = 60.0
    data["score_coverage_ratio"] = 1.0
    return data


def _snapshot_with_scores() -> dict:
    snapshot = _snapshot()
    snapshot["score_summary"] = {
        "fed_policy_score": 60.0,
        "usd_liquidity_score": 61.0,
        "rates_pressure_score": 62.0,
        "risk_appetite_score": 63.0,
        "stablecoin_liquidity_score": 64.0,
        "btc_market_score": 65.0,
        "macro_liquidity_score": 63.0,
        "score_coverage_ratio": 1.0,
    }
    return snapshot


def test_dashboard_html_contains_macro_scores() -> None:
    html, _ = build_dashboard_html(_summary_df(), _features_with_scores(), _snapshot_with_scores())

    assert "Macro Scores" in html
    assert "Macro Liquidity Score" in html


def test_missing_macro_scores_file_does_not_crash(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    output = tmp_path / "dashboard.html"
    analysis_dir.mkdir()
    _summary_df().to_csv(analysis_dir / "fred_series_summary.csv", index=False)
    _features().to_csv(analysis_dir / "macro_features_daily.csv", index=False)
    (analysis_dir / "macro_snapshot_latest.json").write_text(
        json.dumps(_snapshot()), encoding="utf-8"
    )

    warnings = build_dashboard(analysis_dir, output)

    assert output.exists()
    assert warnings == []
    assert "Macro Scores" not in output.read_text(encoding="utf-8")


def test_score_snapshot_cards_render() -> None:
    html, warnings = build_macro_scores_section(_features_with_scores(), _snapshot_with_scores())

    assert "macro_liquidity_score" in html
    assert warnings == []
