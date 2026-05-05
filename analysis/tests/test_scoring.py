from __future__ import annotations

import pandas as pd

from market_mining_analysis.scoring import (
    build_macro_scores,
    build_score_audit,
    neutral_preferred_score,
    score_from_change,
    score_from_pct_change,
    score_from_zscore,
)


def _features(days: int = 420) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "dff_change_30d": -0.1,
            "dff_change_90d": -0.2,
            "dff_zscore_252d": -0.5,
            "net_liquidity_change_30d": 100.0,
            "net_liquidity_change_90d": 200.0,
            "net_liquidity_pct_change_30d": 0.02,
            "net_liquidity_pct_change_90d": 0.04,
            "net_liquidity_zscore_252d": 0.5,
            "tga_billion_change_30d": -20.0,
            "tga_billion_change_90d": -50.0,
            "us10y_real_change_30d": -0.1,
            "us10y_real_zscore_252d": -0.5,
            "us10y_change_30d": -0.1,
            "us2y_change_30d": -0.1,
            "vix_change_30d": -2.0,
            "vix_change_90d": -4.0,
            "vix_zscore_252d": -0.5,
            "hy_oas_change_30d": -0.2,
            "hy_oas_change_90d": -0.4,
            "hy_oas_zscore_252d": -0.5,
            "total_stablecoin_supply_change_30d": 2_000_000_000.0,
            "total_stablecoin_supply_change_90d": 5_000_000_000.0,
            "total_stablecoin_supply_pct_change_30d": 0.01,
            "total_stablecoin_supply_pct_change_90d": 0.02,
            "total_stablecoin_supply_zscore_252d": 0.5,
            "btc_return_30d": 0.05,
            "btc_return_90d": 0.10,
            "stablecoin_to_btc_mcap": 0.2,
            "stablecoin_to_btc_mcap_zscore_252d": 0.4,
            "stablecoin_btc_growth_gap_90d": 0.05,
            "net_liquidity_btc_growth_gap_90d": 0.05,
            "btc_forward_return_90d": 0.2,
        }
    )


def _candidates(features: pd.DataFrame, exclude: set[str] | None = None) -> pd.DataFrame:
    exclude = exclude or set()
    return pd.DataFrame(
        {
            "feature": [column for column in features.columns if column != "date"],
            "usable_for_scoring": [column not in exclude for column in features.columns if column != "date"],
        }
    )


def test_score_from_zscore_up_and_down() -> None:
    z = pd.Series([1.0])
    assert score_from_zscore(z, "up").iloc[0] > 50
    assert score_from_zscore(z, "down").iloc[0] < 50


def test_score_from_change_up_and_down() -> None:
    x = pd.Series([1.0])
    assert score_from_change(x, "up", scale=1).iloc[0] > 50
    assert score_from_change(x, "down", scale=1).iloc[0] < 50


def test_score_from_pct_change() -> None:
    assert score_from_pct_change(pd.Series([0.1]), "up", scale=0.1).iloc[0] > 50


def test_neutral_preferred_center_scores_high() -> None:
    assert neutral_preferred_score(pd.Series([0.05]), center=0.05).iloc[0] == 100


def test_build_macro_scores_generates_all_scores() -> None:
    scores, _ = build_macro_scores(_features(), _candidates(_features()))

    for column in [
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "macro_liquidity_score",
    ]:
        assert column in scores.columns


def test_missing_field_renormalizes_weights() -> None:
    features = _features().drop(columns=["dff_change_90d"])
    scores, contributions = build_macro_scores(features, _candidates(features))

    fed = contributions[
        (contributions["score_name"] == "fed_policy_score") & (contributions["available"])
    ]
    assert fed.groupby("date")["weight"].sum().iloc[-1] < 1.0
    assert scores["fed_policy_score"].notna().any()


def test_not_allowed_candidate_is_not_used() -> None:
    features = _features()
    scores, contributions = build_macro_scores(features, _candidates(features, {"dff_change_30d"}))

    row = contributions[
        (contributions["score_name"] == "fed_policy_score")
        & (contributions["feature"] == "dff_change_30d")
    ].iloc[-1]
    assert not bool(row["available"])
    assert scores["macro_liquidity_score"].between(0, 100).all()


def test_score_coverage_ratio() -> None:
    scores, _ = build_macro_scores(_features(), _candidates(_features()))

    assert scores["score_coverage_ratio"].iloc[-1] == 1.0


def test_btc_market_score_uses_returns_when_ratio_zscore_missing() -> None:
    features = _features().drop(columns=["stablecoin_to_btc_mcap_zscore_252d"])
    scores, _ = build_macro_scores(features, _candidates(features))

    assert scores["btc_market_score"].notna().any()


def test_risk_appetite_contributions_include_hy_oas() -> None:
    _, contributions = build_macro_scores(_features(), _candidates(_features()))
    risk = contributions[contributions["score_name"] == "risk_appetite_score"]

    assert "hy_oas_change_30d" in set(risk["feature"])
    assert "hy_oas_zscore_252d" in set(risk["feature"])


def test_audit_missing_features_are_field_level() -> None:
    features = _features()
    features.loc[features.index[-1], "dff_change_30d"] = pd.NA
    scores, contributions = build_macro_scores(features, _candidates(features))
    audit = build_score_audit(scores, contributions)

    row = audit[audit["score_name"] == "fed_policy_score"].iloc[0]
    assert row["coverage_ratio"] == 1.0
    assert pd.isna(row["missing_features"]) or row["missing_features"] == ""


def test_audit_missing_features_include_not_candidate_target() -> None:
    features = _features()
    scores, contributions = build_macro_scores(features, _candidates(features, {"dff_change_30d"}))
    audit = build_score_audit(scores, contributions)

    row = audit[audit["score_name"] == "fed_policy_score"].iloc[0]
    assert "dff_change_30d" in row["missing_features"]
