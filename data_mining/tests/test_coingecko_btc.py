from __future__ import annotations

from market_mining_data_mining.coingecko_btc import parse_btc_market_chart


def test_parse_btc_market_chart_parses_prices() -> None:
    output = parse_btc_market_chart({"prices": [[1609459200000, 29000.0]]})

    assert output.loc[0, "btc_price"] == 29000.0


def test_parse_btc_market_chart_parses_market_caps() -> None:
    output = parse_btc_market_chart({"market_caps": [[1609459200000, 540_000_000_000.0]]})

    assert output.loc[0, "btc_market_cap"] == 540_000_000_000.0


def test_parse_btc_market_chart_keeps_last_row_per_day() -> None:
    output = parse_btc_market_chart(
        {"prices": [[1609459200000, 29000.0], [1609462800000, 29100.0]]}
    )

    assert len(output) == 1
    assert output.loc[0, "btc_price"] == 29100.0


def test_parse_btc_market_chart_outputs_required_columns() -> None:
    output = parse_btc_market_chart(
        {
            "prices": [[1609459200000, 29000.0]],
            "market_caps": [[1609459200000, 540_000_000_000.0]],
            "total_volumes": [[1609459200000, 50_000_000_000.0]],
        }
    )

    assert list(output.columns) == ["date", "btc_price", "btc_market_cap", "btc_volume"]
