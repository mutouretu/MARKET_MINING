from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.transmission_features import (
    TRANSMISSION_NOTES,
    build_transmission_features,
    run_transmission_update,
    update_macro_features_with_transmission,
    update_macro_snapshot_with_transmission,
)


def _macro(days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "net_liquidity": [1000.0 + index * 2 for index in range(days)],
            "total_stablecoin_supply": [500.0 + index for index in range(days)],
            "existing": 1.0,
        }
    )


def _btc(days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "btc_price": [100.0 + index for index in range(days)],
            "btc_market_cap": [10_000.0 + index * 100 for index in range(days)],
            "btc_volume": [1000.0 for _ in range(days)],
        }
    )


def test_ratios_are_calculated() -> None:
    output = build_transmission_features(_macro(), _btc())

    assert output.loc[0, "stablecoin_to_btc_mcap"] == 0.05
    assert output.loc[0, "btc_to_stablecoin_ratio"] == 20.0


def test_liquidity_transmission_gap_30d() -> None:
    output = build_transmission_features(_macro(), _btc())
    row = output.loc[30]

    expected = row["net_liquidity_growth_30d"] - row["stablecoin_supply_growth_30d"]
    assert row["liquidity_transmission_gap_30d"] == expected


def test_stablecoin_btc_growth_gap_30d() -> None:
    output = build_transmission_features(_macro(), _btc())
    row = output.loc[30]

    expected = row["stablecoin_supply_growth_30d"] - row["btc_return_30d"]
    assert row["stablecoin_btc_growth_gap_30d"] == expected


def test_transmission_phase_rule() -> None:
    output = build_transmission_features(_macro(), _btc())

    assert output.loc[90, "transmission_phase"] == "liquidity_transmitted_to_price"


def test_update_macro_features_keeps_old_fields() -> None:
    macro = _macro()
    transmission = build_transmission_features(macro, _btc())

    updated = update_macro_features_with_transmission(macro, transmission)

    assert "existing" in updated.columns
    assert "stablecoin_to_btc_mcap" in updated.columns


def test_update_snapshot_keeps_old_notes() -> None:
    transmission = build_transmission_features(_macro(), _btc())
    snapshot = {"key_features": {"net_liquidity": 1.0}, "notes": ["existing note"]}

    updated = update_macro_snapshot_with_transmission(snapshot, transmission)

    assert updated["key_features"]["net_liquidity"] == 1.0
    assert "existing note" in updated["notes"]
    assert TRANSMISSION_NOTES[0] in updated["notes"]


def test_run_transmission_update_writes_outputs(tmp_path: Path) -> None:
    macro_path = tmp_path / "macro.csv"
    btc_path = tmp_path / "btc.csv"
    transmission_path = tmp_path / "transmission.csv"
    features_path = tmp_path / "features.csv"
    snapshot_path = tmp_path / "snapshot.json"
    _macro().to_csv(macro_path, index=False)
    snapshot_path.write_text(json.dumps({"notes": ["existing"]}), encoding="utf-8")

    run_transmission_update(
        macro_features_path=macro_path,
        btc_market=_btc(),
        btc_output_path=btc_path,
        output_path=transmission_path,
        features_path=features_path,
        snapshot_path=snapshot_path,
    )

    assert btc_path.exists()
    assert transmission_path.exists()
    assert "transmission_phase" in pd.read_csv(transmission_path).columns
