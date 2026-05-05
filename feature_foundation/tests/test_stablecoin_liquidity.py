from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.stablecoin_liquidity import (
    STABLECOIN_LIQUIDITY_NOTE,
    build_stablecoin_liquidity,
    run_stablecoin_liquidity_update,
    update_macro_features_with_stablecoins,
    update_macro_snapshot_with_stablecoins,
)


def _charts_df(days: int = 120) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=days, freq="D"),
            "total_stablecoin_supply": [1000.0 + index for index in range(days)],
        }
    )


def _summary_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "metric": "total_stablecoin_supply_current",
                "value": 2000.0,
                "date": "2020-04-29",
                "source": "test",
            },
            {"metric": "usdt_supply_current", "value": 1200.0, "date": "2020-04-29", "source": "test"},
            {"metric": "usdc_supply_current", "value": 500.0, "date": "2020-04-29", "source": "test"},
            {
                "metric": "usdt_dominance_current",
                "value": 0.6,
                "date": "2020-04-29",
                "source": "test",
            },
            {
                "metric": "usdc_dominance_current",
                "value": 0.25,
                "date": "2020-04-29",
                "source": "test",
            },
        ]
    )


def test_build_stablecoin_liquidity_generates_change_fields() -> None:
    output = build_stablecoin_liquidity(_charts_df(), _summary_df())

    assert "total_stablecoin_supply_change_30d" in output.columns
    assert output.loc[30, "total_stablecoin_supply_change_30d"] == 30.0


def test_stablecoin_liquidity_score_is_placeholder() -> None:
    output = build_stablecoin_liquidity(_charts_df(), _summary_df())

    assert "stablecoin_liquidity_score" in output.columns
    assert output["stablecoin_liquidity_score"].isna().all()


def test_usdt_usdc_current_values_are_not_backfilled() -> None:
    output = build_stablecoin_liquidity(_charts_df(), _summary_df())

    assert output["usdt_supply"].notna().sum() == 1
    assert output["usdc_supply"].notna().sum() == 1
    assert output.iloc[-1]["usdt_supply"] == 1200.0


def test_update_macro_features_keeps_old_fields() -> None:
    features = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=120), "net_liquidity": 1.0})
    stablecoins = build_stablecoin_liquidity(_charts_df(), _summary_df())

    updated = update_macro_features_with_stablecoins(features, stablecoins)

    assert "net_liquidity" in updated.columns
    assert "total_stablecoin_supply" in updated.columns


def test_update_snapshot_keeps_net_liquidity_notes() -> None:
    stablecoins = build_stablecoin_liquidity(_charts_df(), _summary_df())
    snapshot = {
        "key_features": {"net_liquidity": 5000.0},
        "notes": ["net_liquidity is computed as WALCL_BILLION - TGA_BILLION - RRPONTSYD."],
    }

    updated = update_macro_snapshot_with_stablecoins(snapshot, stablecoins)

    assert updated["key_features"]["net_liquidity"] == 5000.0
    assert STABLECOIN_LIQUIDITY_NOTE in updated["notes"]
    assert "net_liquidity is computed as WALCL_BILLION - TGA_BILLION - RRPONTSYD." in updated[
        "notes"
    ]


def test_run_stablecoin_liquidity_update_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "stablecoins.csv"
    features = tmp_path / "features.csv"
    snapshot = tmp_path / "snapshot.json"
    summary = tmp_path / "summary.csv"
    pd.DataFrame({"date": pd.date_range("2020-01-01", periods=120), "existing": 1.0}).to_csv(
        features, index=False
    )
    snapshot.write_text(json.dumps({"key_features": {"existing": 1.0}}), encoding="utf-8")

    warnings = run_stablecoin_liquidity_update(
        charts_df=_charts_df(),
        current_summary=_summary_df(),
        output_path=output,
        features_path=features,
        snapshot_path=snapshot,
        current_summary_path=summary,
    )

    assert output.exists()
    assert summary.exists()
    assert warnings
    assert "total_stablecoin_supply" in pd.read_csv(output).columns
