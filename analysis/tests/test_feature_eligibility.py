from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.feature_eligibility import (
    review_feature_eligibility,
    run_feature_eligibility_review,
    update_snapshot_with_eligibility,
)
from market_mining_analysis.macro_feature_consolidation import build_feature_audit


def _features(days: int = 700) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "net_liquidity_change_90d": [pd.NA] * 90 + [1.0] * (days - 90),
            "vix_change_30d": [pd.NA] * 30 + [0.1] * (days - 30),
            "btc_forward_return_90d": [0.2] * (days - 90) + [pd.NA] * 90,
            "transmission_phase": ["neutral"] * days,
            "usdt_supply": [pd.NA] * (days - 1) + [100.0],
            "stablecoin_liquidity_score": [pd.NA] * days,
            "btc_return_30d": [pd.NA] * 30 + [0.1] * (days - 30),
            "btc_return_90d": [pd.NA] * 90 + [0.2] * (days - 90),
            "stablecoin_to_btc_mcap": [pd.NA] * 120 + [0.2] * (days - 120),
            "stablecoin_btc_growth_gap_90d": [pd.NA] * 90 + [0.05] * (days - 90),
            "net_liquidity_btc_growth_gap_90d": [pd.NA] * 90 + [0.03] * (days - 90),
            "hy_oas_change_30d": [pd.NA] * 30 + [-0.1] * (days - 30),
            "hy_oas_zscore_252d": [pd.NA] * 252 + [-0.5] * (days - 252),
        }
    )


def _eligibility() -> pd.DataFrame:
    features = _features()
    return review_feature_eligibility(features, build_feature_audit(features)).eligibility


def _row(feature: str) -> pd.Series:
    rows = _eligibility()
    return rows[rows["feature"] == feature].iloc[0]


def test_date_is_excluded_date() -> None:
    row = _row("date")

    assert row["eligibility_status"] == "excluded_date"


def test_forward_return_is_forward_looking_and_not_scoring() -> None:
    row = _row("btc_forward_return_90d")

    assert bool(row["is_forward_looking"])
    assert not bool(row["usable_for_scoring"])


def test_phase_field_is_research_and_dashboard_not_scoring() -> None:
    row = _row("transmission_phase")

    assert not bool(row["usable_for_scoring"])
    assert bool(row["usable_for_research"])
    assert bool(row["usable_for_dashboard"])


def test_current_only_field_is_dashboard_not_scoring() -> None:
    row = _row("usdt_supply")

    assert bool(row["is_current_only"])
    assert not bool(row["usable_for_scoring"])
    assert bool(row["usable_for_dashboard"])


def test_placeholder_score_is_placeholder() -> None:
    row = _row("stablecoin_liquidity_score")

    assert bool(row["is_placeholder"])
    assert row["eligibility_status"] == "excluded_placeholder"


def test_core_change_fields_can_be_scoring_ready() -> None:
    assert _row("net_liquidity_change_90d")["eligibility_status"] == "scoring_ready"
    assert _row("vix_change_30d")["eligibility_status"] == "scoring_ready"


def test_btc_and_transmission_fields_can_be_scoring_ready() -> None:
    for feature in [
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "stablecoin_btc_growth_gap_90d",
        "net_liquidity_btc_growth_gap_90d",
    ]:
        row = _row(feature)
        assert row["eligibility_status"] == "scoring_ready"
        assert bool(row["usable_for_scoring"])


def test_hy_oas_fields_can_be_scoring_ready() -> None:
    for feature in ["hy_oas_change_30d", "hy_oas_zscore_252d"]:
        row = _row(feature)
        assert row["source_group"] == "risk_appetite"
        assert row["eligibility_status"] == "scoring_ready"


def test_usdt_supply_current_only_status() -> None:
    row = _row("usdt_supply")

    assert row["eligibility_status"] == "excluded_current_only"


def test_scoring_candidates_exclude_forward_and_placeholder(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    audit = tmp_path / "audit.csv"
    output = tmp_path / "eligibility.csv"
    scoring = tmp_path / "scoring.csv"
    research = tmp_path / "research.csv"
    dashboard = tmp_path / "dashboard.csv"
    excluded = tmp_path / "excluded.csv"
    summary = tmp_path / "summary.json"
    snapshot = tmp_path / "snapshot.json"
    data = _features()
    data.to_csv(features, index=False)
    build_feature_audit(data).to_csv(audit, index=False)
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")

    run_feature_eligibility_review(
        features_path=features,
        audit_path=audit,
        output_path=output,
        scoring_output_path=scoring,
        research_output_path=research,
        dashboard_output_path=dashboard,
        excluded_output_path=excluded,
        summary_output_path=summary,
        snapshot_path=snapshot,
    )
    scoring_features = set(pd.read_csv(scoring)["feature"])

    assert "btc_forward_return_90d" not in scoring_features
    assert "stablecoin_liquidity_score" not in scoring_features


def test_snapshot_update_keeps_old_notes(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")
    result = review_feature_eligibility(_features(), build_feature_audit(_features()))

    updated = update_snapshot_with_eligibility(snapshot, result.summary)

    assert "existing note" in updated["notes"]
    assert "Feature eligibility review completed in Step 5B." in updated["notes"]
