from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_visualization.build_dashboard import build_dashboard, build_dashboard_html
from visualization.tests.test_dashboard_scores import _features_with_scores, _snapshot_with_scores
from visualization.tests.test_dashboard_transmission import _summary_df


def _features_with_regime() -> pd.DataFrame:
    data = _features_with_scores()
    data["regime"] = "macro_stabilization"
    data["regime_score"] = 55.0
    data["regime_confidence"] = 0.9
    data["risk_level"] = "medium"
    data["primary_driver"] = "macro_score"
    data["secondary_driver"] = "risk_appetite"
    data["allowed_actions"] = "observe"
    data["forbidden_actions"] = "avoid overfitting"
    data["reason"] = "macro_stabilization: scores are mixed"
    return data


def _snapshot_with_regime() -> dict:
    snapshot = _snapshot_with_scores()
    snapshot["regime_summary"] = {
        "date": "2025-01-01",
        "regime": "macro_stabilization",
        "regime_score": 55.0,
        "regime_confidence": 0.9,
        "risk_level": "medium",
        "primary_driver": "macro_score",
        "secondary_driver": "risk_appetite",
        "allowed_actions": "observe",
        "forbidden_actions": "avoid overfitting",
        "reason": "macro_stabilization: scores are mixed",
    }
    return snapshot


def test_dashboard_html_contains_market_regime() -> None:
    html, _ = build_dashboard_html(
        _summary_df(), _features_with_regime(), _snapshot_with_regime()
    )

    assert "Market Regime" in html
    assert "regime_score" in html
    assert "allowed_actions" in html


def test_missing_market_regime_file_does_not_crash(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    output = tmp_path / "dashboard.html"
    analysis_dir.mkdir()
    _summary_df().to_csv(analysis_dir / "fred_series_summary.csv", index=False)
    _features_with_scores().to_csv(analysis_dir / "macro_features_daily.csv", index=False)
    pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=2),
            "macro_liquidity_score": [50, 51],
        }
    ).to_csv(analysis_dir / "macro_scores_daily.csv", index=False)
    (analysis_dir / "macro_snapshot_latest.json").write_text(
        json.dumps(_snapshot_with_scores()), encoding="utf-8"
    )

    warnings = build_dashboard(analysis_dir, output)

    assert output.exists()
    assert "Market Regime" not in output.read_text(encoding="utf-8")
    assert isinstance(warnings, list)
