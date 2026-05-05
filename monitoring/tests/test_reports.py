from pathlib import Path

import pandas as pd
import pytest

from market_mining_visualization.reports.fred_html import build_fred_html_report


def test_build_fred_html_report(tmp_path: Path) -> None:
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    pd.DataFrame(
        [
            {"date": "2020-01-01", "series_id": "DFF", "value": 1.5, "source": "fred"},
            {"date": "2020-01-02", "series_id": "DFF", "value": 1.6, "source": "fred"},
        ]
    ).to_csv(fred_dir / "DFF.csv", index=False)

    output = build_fred_html_report(fred_dir=fred_dir, output=tmp_path / "report.html")

    html = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "FRED Macro Snapshot" in html
    assert "Liquidity &amp; Policy" in html
    assert "DFF" in html
    assert "1.6" in html
    assert "<svg" in html
    assert 'viewBox="0 0 640 220"' in html


def test_build_fred_html_report_requires_csv_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No FRED CSV"):
        build_fred_html_report(fred_dir=tmp_path, output=tmp_path / "report.html")


def test_build_fred_html_report_requires_columns(tmp_path: Path) -> None:
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    pd.DataFrame([{"date": "2020-01-01", "value": 1.5}]).to_csv(
        fred_dir / "bad.csv", index=False
    )

    with pytest.raises(ValueError, match="missing required columns"):
        build_fred_html_report(fred_dir=fred_dir, output=tmp_path / "report.html")
