from __future__ import annotations

import pandas as pd
import pytest

from market_mining_data_mining.treasury_tga import (
    TreasuryTgaError,
    _parse_amount,
    build_tga_daily,
    inspect_tga_account_types,
    validate_tga_daily,
)


def test_parse_amount_strips_commas() -> None:
    assert _parse_amount("1,234") == 1234.0


def test_build_tga_daily_handles_treasury_general_account() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01"],
            "account_type": ["Treasury General Account"],
            "close_today_bal_million": ["500,000"],
            "source": ["test"],
        }
    )

    daily = build_tga_daily(raw)

    assert daily.loc[0, "tga_million"] == 500000.0
    assert daily.loc[0, "tga_billion"] == 500.0


def test_build_tga_daily_handles_old_federal_reserve_account_format() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-01"],
            "account_type": ["Other Account", "Federal Reserve Account"],
            "close_today_bal_million": [100.0, 250000.0],
            "source": ["test", "test"],
        }
    )

    daily = build_tga_daily(raw)

    assert daily.loc[0, "account_type"] == "Federal Reserve Account"
    assert daily.loc[0, "tga_billion"] == 250.0


def test_build_tga_daily_handles_new_tga_closing_balance_format() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2022-01-03"],
            "account_type": ["Treasury General Account (TGA) Closing Balance"],
            "close_today_bal_million": [650000.0],
            "source": ["test"],
        }
    )

    daily = build_tga_daily(raw)

    assert daily.loc[0, "account_type"] == "Treasury General Account (TGA) Closing Balance"
    assert daily.loc[0, "tga_billion"] == 650.0


def test_build_tga_daily_uses_open_balance_when_close_is_missing() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2026-04-30"],
            "account_type": ["Treasury General Account (TGA) Closing Balance"],
            "close_today_bal_million": [None],
            "open_today_bal_million": [969383.0],
            "source": ["test"],
        }
    )

    daily = build_tga_daily(raw)

    assert daily.loc[0, "tga_billion"] == 969.383


def test_build_tga_daily_prefers_tga_closing_balance_over_federal_reserve() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2022-01-03", "2022-01-03"],
            "account_type": [
                "Federal Reserve Account",
                "Treasury General Account (TGA) Closing Balance",
            ],
            "close_today_bal_million": [250000.0, 650000.0],
            "source": ["test", "test"],
        }
    )

    daily = build_tga_daily(raw)

    assert daily.loc[0, "account_type"] == "Treasury General Account (TGA) Closing Balance"
    assert daily.loc[0, "tga_billion"] == 650.0


def test_build_tga_daily_rejects_unclear_multiple_account_types() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-01"],
            "account_type": ["Account A", "Account B"],
            "close_today_bal_million": [100.0, 200.0],
            "source": ["test", "test"],
        }
    )

    with pytest.raises(TreasuryTgaError, match="Unable to identify"):
        build_tga_daily(raw)


def test_build_tga_daily_rejects_negative_tga() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01"],
            "account_type": ["Treasury General Account"],
            "close_today_bal_million": [-100.0],
            "source": ["test"],
        }
    )

    with pytest.raises(TreasuryTgaError, match="negative"):
        build_tga_daily(raw)


def test_build_tga_daily_treats_string_null_as_missing() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02"],
            "account_type": ["Treasury General Account", "Treasury General Account"],
            "close_today_bal_million": ["null", "500,000"],
            "source": ["test", "test"],
        }
    )

    daily = build_tga_daily(raw)

    assert pd.isna(daily.loc[0, "tga_billion"])
    assert daily.loc[1, "tga_billion"] == 500.0


def test_inspect_tga_account_types_outputs_coverage() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2022-01-03"],
            "account_type": [
                "Federal Reserve Account",
                "Federal Reserve Account",
                "Treasury General Account (TGA) Closing Balance",
            ],
            "close_today_bal_million": [100.0, 110.0, 650000.0],
            "source": ["test", "test", "test"],
        }
    )

    summary = inspect_tga_account_types(raw)

    fed = summary[summary["account_type"] == "Federal Reserve Account"].iloc[0]
    tga = summary[
        summary["account_type"] == "Treasury General Account (TGA) Closing Balance"
    ].iloc[0]
    assert fed["first_date"] == "2020-01-01"
    assert fed["last_date"] == "2020-01-02"
    assert fed["count"] == 2
    assert tga["latest_value_billion"] == 650.0


def test_validate_tga_daily_rejects_output_ending_at_2021_09_30() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2021-09-30"],
            "account_type": ["Federal Reserve Account"],
            "close_today_bal_million": [250000.0],
            "source": ["test"],
        }
    )
    daily = build_tga_daily(raw)

    with pytest.raises(TreasuryTgaError, match="2021-09-30"):
        validate_tga_daily(raw, daily)


def test_validate_tga_daily_rejects_fed_only_when_raw_has_tga() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2022-01-03", "2022-01-04"],
            "account_type": [
                "Treasury General Account (TGA) Closing Balance",
                "Federal Reserve Account",
            ],
            "close_today_bal_million": [650000.0, 250000.0],
            "source": ["test", "test"],
        }
    )
    daily = pd.DataFrame(
        {
            "date": ["2022-01-04"],
            "tga_million": [250000.0],
            "tga_billion": [250.0],
            "account_type": ["Federal Reserve Account"],
            "source": ["test"],
        }
    )

    with pytest.raises(TreasuryTgaError, match="Treasury General Account exists"):
        validate_tga_daily(raw, daily)
