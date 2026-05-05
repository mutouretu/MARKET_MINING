from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from market_mining_analysis.usd_liquidity import (
    UsdLiquidityError,
    build_usd_liquidity,
    run_usd_liquidity_update,
    update_macro_features_with_usd_liquidity,
    update_macro_snapshot_with_usd_liquidity,
)


def _fred_wide(days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "WALCL_BILLION": [7000.0 + index for index in range(days)],
            "RRPONTSYD": [2000.0 for _ in range(days)],
        }
    )


def _tga_daily(days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "tga_billion": [500.0 + index for index in range(days)],
        }
    )


def test_build_usd_liquidity_calculates_proxy_and_net_liquidity() -> None:
    output = build_usd_liquidity(_fred_wide(), _tga_daily())

    assert output.loc[0, "usd_liquidity_proxy_no_tga"] == 5000.0
    assert output.loc[0, "net_liquidity"] == 4500.0


def test_build_usd_liquidity_generates_change_fields() -> None:
    output = build_usd_liquidity(_fred_wide(), _tga_daily())

    assert "net_liquidity_change_30d" in output.columns
    assert "net_liquidity_change_90d" in output.columns
    assert "net_liquidity_pct_change_30d" in output.columns
    assert "tga_billion_change_30d" in output.columns
    assert "tga_billion_change_90d" in output.columns
    assert "tga_billion_pct_change_30d" in output.columns
    assert output.loc[30, "tga_billion_change_30d"] == 30.0
    assert output.loc[30, "net_liquidity_change_30d"] == 0.0


def test_build_usd_liquidity_requires_fred_columns() -> None:
    with pytest.raises(UsdLiquidityError, match="WALCL_BILLION"):
        build_usd_liquidity(pd.DataFrame({"date": ["2020-01-01"]}), _tga_daily())

    with pytest.raises(UsdLiquidityError, match="RRPONTSYD"):
        build_usd_liquidity(
            pd.DataFrame({"date": ["2020-01-01"], "WALCL_BILLION": [7000.0]}),
            _tga_daily(),
        )

    with pytest.raises(UsdLiquidityError, match="tga_billion"):
        build_usd_liquidity(_fred_wide(), pd.DataFrame({"date": ["2020-01-01"]}))


def test_update_macro_features_adds_net_liquidity_fields() -> None:
    features = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=120, freq="D")})
    usd_liquidity = build_usd_liquidity(_fred_wide(), _tga_daily())

    updated = update_macro_features_with_usd_liquidity(features, usd_liquidity)

    assert "tga_billion_change_30d" in updated.columns
    assert "tga_billion_zscore_252d" in updated.columns
    assert "net_liquidity_change_7d" in updated.columns
    assert "net_liquidity_change_90d" in updated.columns


def test_update_macro_snapshot_keeps_existing_key_features() -> None:
    features = update_macro_features_with_usd_liquidity(
        pd.DataFrame({"date": pd.date_range("2020-01-01", periods=120, freq="D")}),
        build_usd_liquidity(_fred_wide(), _tga_daily()),
    )
    snapshot = {"key_features": {"yield_curve_10y_2y": 1.0}, "notes": ["existing note"]}

    updated = update_macro_snapshot_with_usd_liquidity(snapshot, features)

    assert updated["key_features"]["yield_curve_10y_2y"] == 1.0
    assert "net_liquidity" in updated["key_features"]
    assert "existing note" in updated["notes"]


def test_run_usd_liquidity_update_writes_outputs(tmp_path: Path) -> None:
    fred_path = tmp_path / "fred.csv"
    tga_path = tmp_path / "tga.csv"
    output_path = tmp_path / "usd_liquidity.csv"
    features_path = tmp_path / "features.csv"
    snapshot_path = tmp_path / "snapshot.json"

    _fred_wide().to_csv(fred_path, index=False)
    _tga_daily().to_csv(tga_path, index=False)
    pd.DataFrame({"date": pd.date_range("2020-01-01", periods=120, freq="D")}).to_csv(
        features_path, index=False
    )
    snapshot_path.write_text(json.dumps({"key_features": {"existing": 1.0}}), encoding="utf-8")

    warnings = run_usd_liquidity_update(
        fred_wide_path=fred_path,
        tga_path=tga_path,
        output_path=output_path,
        features_path=features_path,
        snapshot_path=snapshot_path,
    )

    assert warnings == []
    assert output_path.exists()
    assert "net_liquidity" in pd.read_csv(output_path).columns
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["key_features"]["existing"] == 1.0
