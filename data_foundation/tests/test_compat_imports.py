def test_legacy_data_imports_remain_available() -> None:
    from market_mining.data.schemas import MacroPolicyRecord
    from market_mining.data.sources.fred import FredClient
    from market_mining.data.validators import validate_time_series
    from market_mining.reports.fred_html import build_fred_html_report

    assert MacroPolicyRecord is not None
    assert FredClient is not None
    assert validate_time_series is not None
    assert build_fred_html_report is not None


def test_physical_subproject_imports() -> None:
    from market_mining_analysis import __doc__ as analysis_doc
    from market_mining_data_mining.schemas import MacroPolicyRecord
    from market_mining_visualization.reports.fred_html import build_fred_html_report

    assert analysis_doc is not None
    assert MacroPolicyRecord is not None
    assert build_fred_html_report is not None
