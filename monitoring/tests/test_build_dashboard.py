from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_mining_visualization.build_dashboard import (
    build_dashboard_html,
    build_key_charts,
    build_summary_cards,
    write_dashboard,
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


def _features_df(include_all_columns: bool = True) -> pd.DataFrame:
    data = {
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "net_liquidity": [0.5, 1.5, 2.5],
        "net_liquidity_change_30d": [0.1, 0.2, 0.3],
        "net_liquidity_change_90d": [0.2, 0.3, 0.4],
        "tga_billion": [0.5, 0.5, 0.5],
        "tga_billion_change_30d": [0.0, 0.0, 0.0],
        "tga_billion_change_90d": [0.0, 0.0, 0.0],
        "usd_liquidity_proxy_no_tga": [1.0, 2.0, 3.0],
        "usd_liquidity_proxy_no_tga_change_30d": [0.1, 0.2, 0.3],
        "usd_liquidity_proxy_no_tga_change_90d": [0.2, 0.3, 0.4],
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
    if not include_all_columns:
        data.pop("tga_billion_change_90d")
    return pd.DataFrame(data)


def _snapshot() -> dict:
    return {
        "latest_date": "2020-01-03",
        "series_count": 1,
        "key_features": {
            "net_liquidity": 2.5,
            "net_liquidity_change_30d": 0.3,
            "net_liquidity_change_90d": 0.4,
            "tga_billion": 0.5,
            "tga_billion_change_30d": 0.0,
            "tga_billion_change_90d": 0.0,
            "yield_curve_10y_2y": 0.5,
            "breakeven_10y_proxy": 1.0,
            "usd_liquidity_proxy_no_tga": 3.0,
            "usd_liquidity_proxy_no_tga_change_30d": 0.3,
            "usd_liquidity_proxy_no_tga_change_90d": 0.4,
            "total_stablecoin_supply": 1020.0,
            "total_stablecoin_supply_change_30d": 12.0,
            "total_stablecoin_supply_change_90d": 32.0,
            "usdt_supply": 600.0,
            "usdc_supply": 300.0,
            "usdt_dominance": 0.6,
            "usdc_dominance": 0.3,
            "btc_price": 102.0,
            "btc_market_cap": 10200.0,
            "stablecoin_to_btc_mcap": 0.1,
            "liquidity_transmission_gap_30d": 0.03,
            "liquidity_transmission_gap_90d": 0.04,
            "transmission_phase": "neutral",
        },
        "notes": ["usd_liquidity_proxy_no_tga excludes TGA."],
    }


def test_build_summary_cards() -> None:
    html = build_summary_cards(_summary_df())

    assert "Effective Federal Funds Rate" in html
    assert "positive_for_btc" in html
    assert "fed_policy" in html


def test_build_key_charts_generates_plotly_chart() -> None:
    html, warnings = build_key_charts(_features_df())

    assert warnings == []
    assert "plotly" in html.lower()
    assert "Net Liquidity" in html


def test_build_key_charts_handles_missing_columns() -> None:
    html, warnings = build_key_charts(_features_df(include_all_columns=False))

    assert "Missing columns: tga_billion_change_90d" in html
    assert warnings


def test_build_dashboard_html_contains_sections() -> None:
    html, warnings = build_dashboard_html(_summary_df(), _features_df(), _snapshot())

    assert warnings == []
    assert "Macro Snapshot" in html
    assert "Key Charts" in html
    assert "Data Inventory" in html


def test_write_dashboard(tmp_path: Path) -> None:
    output = tmp_path / "dashboard.html"

    write_dashboard("<html></html>", output)

    assert output.exists()
    assert output.read_text(encoding="utf-8") == "<html></html>"
