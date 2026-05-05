"""Compatibility exports for the FRED HTML visualization report."""

from market_mining_visualization.reports.fred_html import (
    FredSeriesSummary,
    build_fred_html_report,
)

__all__ = [
    "FredSeriesSummary",
    "build_fred_html_report",
]
