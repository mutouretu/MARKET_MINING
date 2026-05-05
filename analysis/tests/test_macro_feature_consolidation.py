from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_mining_analysis.macro_feature_consolidation import (
    build_daily_feature_frame,
    consolidate_macro_features,
)


def _dates(days: int = 420) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=days, freq="D")


def _fred(days: int = 420) -> pd.DataFrame:
    dates = _dates(days)
    return pd.DataFrame(
        {
            "date": dates,
            "DFF": 5.0,
            "WALCL_BILLION": 7000.0,
            "RRPONTSYD": 500.0,
            "M2SL": [20000.0 + i for i in range(days)],
            "DGS2": 4.0,
            "DGS10": 4.5,
            "DFII10": 2.0,
            "VIXCLS": 20.0,
            "BAMLH0A0HYM2": 3.0,
        }
    )


def _usd(days: int = 420) -> pd.DataFrame:
    dates = _dates(days)
    return pd.DataFrame(
        {
            "date": dates,
            "walcl_billion": 7000.0,
            "rrp_billion": 500.0,
            "tga_billion": 800.0,
            "usd_liquidity_proxy_no_tga": 6500.0,
            "net_liquidity": [5700.0 + i for i in range(days)],
        }
    )


def _stable(days: int = 420) -> pd.DataFrame:
    dates = _dates(days)
    return pd.DataFrame(
        {
            "date": dates,
            "total_stablecoin_supply": [1000.0 + i for i in range(days)],
            "usdt_supply": [pd.NA for _ in range(days - 1)] + [600.0],
            "usdc_supply": [pd.NA for _ in range(days - 1)] + [300.0],
            "usdt_dominance": [pd.NA for _ in range(days - 1)] + [0.6],
            "usdc_dominance": [pd.NA for _ in range(days - 1)] + [0.3],
            "usdt_history_available": False,
            "usdc_history_available": False,
        }
    )


def _btc(days: int = 420) -> pd.DataFrame:
    dates = _dates(days)
    return pd.DataFrame(
        {
            "date": dates,
            "btc_price": [40000.0 + i for i in range(days)],
            "btc_market_cap": [800000.0 + i * 100 for i in range(days)],
            "btc_volume": 1000.0,
        }
    )


def _transmission(days: int = 420) -> pd.DataFrame:
    dates = _dates(days)
    return pd.DataFrame(
        {
            "date": dates,
            "btc_return_30d": 0.1,
            "stablecoin_supply_growth_30d": 0.02,
            "net_liquidity_growth_30d": 0.03,
            "transmission_phase": "neutral",
        }
    )


def test_consolidates_all_inputs_and_sorts_unique_dates() -> None:
    output, _, _ = build_daily_feature_frame(_fred(), _usd(), _stable(), _btc(), _transmission())

    assert output["date"].is_unique
    assert output["date"].is_monotonic_increasing
    assert "net_liquidity" in output.columns


def test_standardizes_fred_field_names() -> None:
    output, _, _ = build_daily_feature_frame(_fred(), _usd(), _stable(), _btc(), _transmission())

    assert "dff" in output.columns
    assert "us10y_real" in output.columns
    assert "vix" in output.columns
    assert "DFF" not in output.columns


def test_computes_rate_and_money_features() -> None:
    output, _, _ = build_daily_feature_frame(_fred(), _usd(), _stable(), _btc(), _transmission())

    assert output.loc[0, "yield_curve_10y_2y"] == 0.5
    assert output.loc[0, "breakeven_10y_proxy"] == 2.5
    assert "m2_yoy" in output.columns


def test_computes_transmission_fields() -> None:
    output, _, _ = build_daily_feature_frame(_fred(), _usd(), _stable(), _btc(), None)

    assert "stablecoin_to_btc_mcap" in output.columns
    assert "liquidity_transmission_gap_30d" in output.columns


def test_does_not_produce_pandas_suffix_fields() -> None:
    output, _, _ = build_daily_feature_frame(_fred(), _usd(), _stable(), _btc(), _transmission())

    assert not [column for column in output.columns if column.endswith(("_x", "_y"))]


def test_missing_input_file_does_not_crash(tmp_path: Path) -> None:
    fred = tmp_path / "fred.csv"
    usd = tmp_path / "usd.csv"
    stable = tmp_path / "stable.csv"
    btc = tmp_path / "btc.csv"
    output = tmp_path / "macro.csv"
    audit = tmp_path / "audit.csv"
    latest = tmp_path / "latest.csv"
    snapshot = tmp_path / "snapshot.json"
    _fred().to_csv(fred, index=False)
    _usd().to_csv(usd, index=False)
    _stable().to_csv(stable, index=False)
    _btc().to_csv(btc, index=False)

    result = consolidate_macro_features(
        fred_wide_path=fred,
        usd_liquidity_path=usd,
        stablecoins_path=stable,
        btc_market_path=btc,
        transmission_path=tmp_path / "missing.csv",
        output_path=output,
        audit_output_path=audit,
        latest_output_path=latest,
        snapshot_path=snapshot,
    )

    assert result.missing_inputs
    assert output.exists()
