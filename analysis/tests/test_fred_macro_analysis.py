from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.fred_macro import (
    build_fred_wide_table,
    build_latest_snapshot,
    build_macro_features,
    build_series_summary,
    infer_btc_implication,
    load_fred_series,
    run_fred_macro_analysis,
)


def _write_series(directory: Path, series_id: str, values: list[float | str]) -> None:
    dates = pd.date_range("2020-01-01", periods=len(values), freq="D")
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "value": values}).to_csv(
        directory / f"{series_id}.csv", index=False
    )


def test_load_fred_series_handles_missing_marker(tmp_path: Path) -> None:
    path = tmp_path / "DFF.csv"
    pd.DataFrame(
        [
            {"date": "2020-01-01", "value": "1.0"},
            {"date": "2020-01-02", "value": "."},
        ]
    ).to_csv(path, index=False)

    data = load_fred_series(path=path, series_id="DFF")

    assert data.loc[0, "value"] == 1.0
    assert pd.isna(data.loc[1, "value"])


def test_load_fred_series_keeps_last_duplicate_date(tmp_path: Path) -> None:
    path = tmp_path / "DFF.csv"
    pd.DataFrame(
        [
            {"date": "2020-01-01", "value": "1.0"},
            {"date": "2020-01-01", "value": "2.0"},
        ]
    ).to_csv(path, index=False)

    data = load_fred_series(path=path, series_id="DFF")

    assert len(data) == 1
    assert data.loc[0, "value"] == 2.0


def test_build_fred_wide_table_merges_series(tmp_path: Path) -> None:
    _write_series(tmp_path, "DFF", [1.0, 1.1, 1.2])
    _write_series(tmp_path, "DGS10", [2.0, 2.1, 2.2])

    wide = build_fred_wide_table(tmp_path)

    assert list(wide["date"]) == list(pd.date_range("2020-01-01", periods=3, freq="D"))
    assert "DFF" in wide.columns
    assert "DGS10" in wide.columns


def test_build_macro_features_generates_core_fields(tmp_path: Path) -> None:
    days = 100
    _write_series(tmp_path, "WALCL", [7000 + index for index in range(days)])
    _write_series(tmp_path, "RRPONTSYD", [2000 + index for index in range(days)])
    _write_series(tmp_path, "DGS2", [1.0 + index * 0.01 for index in range(days)])
    _write_series(tmp_path, "DGS10", [2.0 + index * 0.01 for index in range(days)])
    _write_series(tmp_path, "DFII10", [0.5 + index * 0.01 for index in range(days)])

    wide = build_fred_wide_table(tmp_path)
    features = build_macro_features(wide)

    assert "yield_curve_10y_2y" in features.columns
    assert "breakeven_10y_proxy" in features.columns
    assert "usd_liquidity_proxy_no_tga" in features.columns
    assert "usd_liquidity_proxy_no_tga_change_30d" in features.columns


def test_infer_btc_implication_for_up_and_down_rules() -> None:
    assert infer_btc_implication("M2SL", 1.0) == "positive_for_btc"
    assert infer_btc_implication("M2SL", -1.0) == "negative_for_btc"
    assert infer_btc_implication("DFF", -1.0) == "positive_for_btc"
    assert infer_btc_implication("DFF", 1.0) == "negative_for_btc"
    assert infer_btc_implication("DFF", 0.0) == "neutral"


def test_snapshot_json_can_be_generated(tmp_path: Path) -> None:
    days = 300
    _write_series(tmp_path, "DFF", [5.0 - index * 0.01 for index in range(days)])
    _write_series(tmp_path, "DGS2", [1.0 + index * 0.01 for index in range(days)])
    _write_series(tmp_path, "DGS10", [2.0 + index * 0.01 for index in range(days)])
    _write_series(tmp_path, "DFII10", [0.5 + index * 0.005 for index in range(days)])
    _write_series(tmp_path, "WALCL", [7000 + index for index in range(days)])
    _write_series(tmp_path, "RRPONTSYD", [2000 - index for index in range(days)])

    wide = build_fred_wide_table(tmp_path)
    features = build_macro_features(wide)
    summary = build_series_summary(tmp_path, wide, features)
    snapshot = build_latest_snapshot(features, summary)

    assert snapshot["latest_date"] == "2020-10-26"
    assert snapshot["series_count"] == len(summary)
    assert "fed_policy" in snapshot["groups"]
    assert "usd_liquidity_proxy_no_tga" in snapshot["key_features"]
    assert snapshot["notes"]


def test_run_fred_macro_analysis_writes_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "fred"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    _write_series(input_dir, "DFF", [5.0 - index * 0.01 for index in range(300)])
    _write_series(input_dir, "DGS2", [1.0 + index * 0.01 for index in range(300)])
    _write_series(input_dir, "DGS10", [2.0 + index * 0.01 for index in range(300)])

    result = run_fred_macro_analysis(input_dir=input_dir, output_dir=output_dir)

    assert result.wide_path.exists()
    assert result.features_path.exists()
    assert result.summary_path.exists()
    assert result.snapshot_path.exists()
    snapshot = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["series_count"] == 3
