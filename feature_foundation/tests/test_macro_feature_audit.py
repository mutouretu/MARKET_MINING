from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from market_mining_analysis.macro_feature_consolidation import (
    MacroFeatureConsolidationError,
    build_feature_audit,
    build_latest_snapshot,
    update_macro_snapshot,
    validate_macro_features,
)


def _features(days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "net_liquidity": [5000.0 + i for i in range(days)],
            "btc_price": [40000.0 + i for i in range(days)],
            "total_stablecoin_supply": [1000.0 + i for i in range(days)],
            "us10y_real": 2.0,
            "vix": 20.0,
            "hy_oas": 3.0,
            "transmission_phase": "neutral",
        }
    )


def test_audit_outputs_one_row_per_feature() -> None:
    features = _features()
    audit = build_feature_audit(features)

    assert len(audit) == len(features.columns) - 1
    assert set(["feature", "null_ratio"]).issubset(audit.columns)


def test_audit_contains_valid_dates() -> None:
    audit = build_feature_audit(_features())

    assert "first_valid_date" in audit.columns
    assert "last_valid_date" in audit.columns


def test_latest_snapshot_contains_one_latest_row() -> None:
    latest = build_latest_snapshot(_features())

    assert len(latest) == 1
    assert latest.iloc[0]["date"] == pd.Timestamp("2024-04-29")


def test_update_macro_snapshot_keeps_existing_notes(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")

    updated = update_macro_snapshot(snapshot, _features(), warnings=[])

    assert "existing note" in updated["notes"]
    assert "macro_features_daily.csv is the consolidated feature table" in updated["notes"][-1]


def test_validate_macro_features_rejects_duplicate_date() -> None:
    features = _features()
    features.loc[1, "date"] = features.loc[0, "date"]

    with pytest.raises(MacroFeatureConsolidationError, match="unique"):
        validate_macro_features(features)


def test_validate_macro_features_rejects_suffix_columns() -> None:
    features = _features()
    features["net_liquidity_x"] = features["net_liquidity"]

    with pytest.raises(MacroFeatureConsolidationError, match="suffix"):
        validate_macro_features(features)
