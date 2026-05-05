from __future__ import annotations

from market_mining_data_mining.defillama_stablecoins import (
    build_stablecoin_current_summary,
    extract_pegged_usd,
    parse_stablecoin_charts_all,
    parse_stablecoins_current,
)


def test_extract_pegged_usd_handles_number() -> None:
    assert extract_pegged_usd(123.0) == 123.0


def test_extract_pegged_usd_handles_pegged_usd_dict() -> None:
    assert extract_pegged_usd({"peggedUSD": 456.0}) == 456.0


def test_parse_stablecoins_current_identifies_usdt_usdc() -> None:
    raw = {
        "peggedAssets": [
            {
                "id": 1,
                "name": "Tether",
                "symbol": "USDT",
                "pegType": "peggedUSD",
                "pegMechanism": "fiat-backed",
                "price": 1,
                "circulating": {"peggedUSD": 100.0},
            },
            {
                "id": 2,
                "name": "USD Coin",
                "symbol": "USDC",
                "pegType": "peggedUSD",
                "pegMechanism": "fiat-backed",
                "price": 1,
                "circulating": {"peggedUSD": 50.0},
            },
        ]
    }

    current = parse_stablecoins_current(raw)
    summary = build_stablecoin_current_summary(current)
    metrics = dict(zip(summary["metric"], summary["value"]))

    assert metrics["usdt_supply_current"] == 100.0
    assert metrics["usdc_supply_current"] == 50.0
    assert metrics["total_stablecoin_supply_current"] == 150.0


def test_build_stablecoin_current_summary_calculates_dominance() -> None:
    current = parse_stablecoins_current(
        {
            "peggedAssets": [
                {
                    "name": "Tether",
                    "symbol": "USDT",
                    "pegType": "peggedUSD",
                    "circulating": 75.0,
                },
                {
                    "name": "USDC",
                    "symbol": "USDC",
                    "pegType": "peggedUSD",
                    "circulating": 25.0,
                },
            ]
        }
    )

    summary = build_stablecoin_current_summary(current)
    metrics = dict(zip(summary["metric"], summary["value"]))

    assert metrics["usdt_dominance_current"] == 0.75
    assert metrics["usdc_dominance_current"] == 0.25


def test_parse_stablecoin_charts_all_handles_list_structure() -> None:
    parsed = parse_stablecoin_charts_all(
        [{"date": 1609459200, "totalCirculating": {"peggedUSD": 123456.0}}]
    )

    assert parsed.loc[0, "date"].strftime("%Y-%m-%d") == "2021-01-01"
    assert parsed.loc[0, "total_stablecoin_supply"] == 123456.0


def test_parse_stablecoin_charts_all_handles_dict_structure() -> None:
    parsed = parse_stablecoin_charts_all(
        {"peggedUSD": [{"date": 1609459200, "totalCirculating": 123456.0}]}
    )

    assert parsed.loc[0, "date"].strftime("%Y-%m-%d") == "2021-01-01"
    assert parsed.loc[0, "total_stablecoin_supply"] == 123456.0
