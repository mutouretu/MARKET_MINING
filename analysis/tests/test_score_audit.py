from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market_mining_analysis.scoring import (
    build_macro_scores,
    build_score_audit,
    run_macro_scoring,
    update_snapshot_with_scores,
)
from analysis.tests.test_scoring import _candidates, _features


def test_score_audit_contains_coverage_ratio() -> None:
    scores, contributions = build_macro_scores(_features(), _candidates(_features()))
    audit = build_score_audit(scores, contributions)

    assert "coverage_ratio" in audit.columns


def test_latest_snapshot_has_one_latest_date(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    candidates = tmp_path / "candidates.csv"
    output = tmp_path / "scores.csv"
    contributions = tmp_path / "contrib.csv"
    audit = tmp_path / "audit.csv"
    latest = tmp_path / "latest.csv"
    snapshot = tmp_path / "snapshot.json"
    _features().to_csv(features, index=False)
    _candidates(_features()).to_csv(candidates, index=False)
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")

    run_macro_scoring(features, candidates, output, contributions, audit, latest, snapshot)

    latest_df = pd.read_csv(latest)
    assert len(latest_df) == 1
    assert latest_df.iloc[0]["date"] == "2025-02-23"


def test_contributions_contain_expected_columns() -> None:
    _, contributions = build_macro_scores(_features(), _candidates(_features()))

    assert {"feature_score", "weight", "weighted_contribution"}.issubset(contributions.columns)


def test_snapshot_update_keeps_old_notes(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"notes": ["existing note"]}), encoding="utf-8")
    scores, _ = build_macro_scores(_features(), _candidates(_features()))

    updated = update_snapshot_with_scores(snapshot, scores)

    assert "existing note" in updated["notes"]
    assert "Macro scoring v0.1 uses rule-based directional scoring." in updated["notes"]


def test_missing_feature_enters_audit_notes() -> None:
    features = _features().drop(columns=["dff_change_90d"])
    scores, contributions = build_macro_scores(features, _candidates(features))
    audit = build_score_audit(scores, contributions)

    row = audit[audit["score_name"] == "fed_policy_score"].iloc[0]
    assert "missing feature" in row["notes"]
