from __future__ import annotations

import pandas as pd

from market_mining_visualization.build_dashboard import (
    build_dashboard_html,
    build_transmission_divergence,
)


def _summary_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series_id": "DFF",
                "label": "Effective Federal Funds Rate",
                "group": "fed_policy",
                "first_date": "2020-01-01",
                "last_date": "2020-01-03",
                "latest_value": 4.5,
                "observations": 3,
                "missing_values_raw": 0,
                "missing_values_after_ffill": 0,
                "unit": "percent",
                "bullish_when": "down",
                "change_30d": -0.1,
                "change_90d": -0.2,
                "pct_change_90d": -0.04,
                "zscore_252d": 0.5,
                "btc_implication": "positive_for_btc",
                "status": "improving",
            }
        ]
    )


def _features(include_gap_90d: bool = True) -> pd.DataFrame:
    data = {
        "date": pd.date_range("2020-01-01", periods=3, freq="D"),
        "net_liquidity": [4500.0, 4510.0, 4520.0],
        "net_liquidity_change_30d": [10.0, 11.0, 12.0],
        "net_liquidity_change_90d": [30.0, 31.0, 32.0],
        "tga_billion": [500.0, 490.0, 480.0],
        "tga_billion_change_30d": [-10.0, -11.0, -12.0],
        "tga_billion_change_90d": [-30.0, -31.0, -32.0],
        "usd_liquidity_proxy_no_tga": [5000.0, 5000.0, 5000.0],
        "DFII10": [1.0, 1.1, 1.2],
        "VIXCLS": [20.0, 19.0, 18.0],
        "BAMLH0A0HYM2": [3.0, 2.9, 2.8],
        "VIXCLS_change_30d": [-1.0, -1.0, -1.0],
        "BAMLH0A0HYM2_change_30d": [-0.1, -0.1, -0.1],
        "total_stablecoin_supply": [1000.0, 1010.0, 1020.0],
        "total_stablecoin_supply_change_30d": [10.0, 11.0, 12.0],
        "total_stablecoin_supply_change_90d": [30.0, 31.0, 32.0],
        "usdt_supply": [pd.NA, pd.NA, 600.0],
        "usdc_supply": [pd.NA, pd.NA, 300.0],
        "usdt_dominance": [pd.NA, pd.NA, 0.6],
        "usdc_dominance": [pd.NA, pd.NA, 0.3],
        "btc_price": [100.0, 101.0, 102.0],
        "btc_market_cap": [10000.0, 10100.0, 10200.0],
        "stablecoin_to_btc_mcap": [0.1, 0.1, 0.1],
        "liquidity_transmission_gap_30d": [0.01, 0.02, 0.03],
        "liquidity_transmission_gap_90d": [0.02, 0.03, 0.04],
        "stablecoin_supply_growth_30d": [0.01, 0.02, 0.03],
        "btc_return_30d": [0.02, 0.03, 0.04],
        "net_liquidity_growth_90d": [0.01, 0.02, 0.03],
        "btc_return_90d": [0.02, 0.03, 0.04],
    }
    if not include_gap_90d:
        data.pop("liquidity_transmission_gap_90d")
    return pd.DataFrame(data)


def _snapshot() -> dict:
    return {
        "key_features": {
            "net_liquidity": 4520.0,
            "total_stablecoin_supply": 1020.0,
            "btc_price": 102.0,
            "btc_market_cap": 10200.0,
            "stablecoin_to_btc_mcap": 0.1,
            "liquidity_transmission_gap_30d": 0.03,
            "liquidity_transmission_gap_90d": 0.04,
            "stablecoin_btc_growth_gap_30d": -0.01,
            "stablecoin_btc_growth_gap_90d": -0.02,
            "transmission_phase": "neutral",
        },
        "notes": [],
    }


def test_dashboard_html_contains_transmission_area() -> None:
    html, _ = build_dashboard_html(_summary_df(), _features(), _snapshot())

    assert "Transmission / Divergence" in html
    assert "Stablecoin / BTC Market Cap" in html
    assert "Liquidity Transmission Gap" in html


def test_missing_transmission_field_does_not_crash() -> None:
    html, warnings = build_transmission_divergence(_features(include_gap_90d=False), _snapshot())

    assert "Missing columns: liquidity_transmission_gap_90d" in html
    assert warnings
