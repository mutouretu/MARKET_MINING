from datetime import date

import pytest
from pydantic import ValidationError

from market_mining_data_mining.schemas import (
    CryptoConfirmationRecord,
    InstitutionalFlowRecord,
    MacroPolicyRecord,
    MarketStateRecord,
    RiskAppetiteRecord,
    StablecoinLiquidityRecord,
    UsdLiquidityRecord,
)
from market_mining_data_mining.validators import (
    validate_no_duplicate_dates,
    validate_required_fields,
    validate_sorted_by_date,
    validate_time_series,
)


def test_all_record_types_can_be_created() -> None:
    record_types = [
        MacroPolicyRecord,
        UsdLiquidityRecord,
        StablecoinLiquidityRecord,
        RiskAppetiteRecord,
        InstitutionalFlowRecord,
        CryptoConfirmationRecord,
        MarketStateRecord,
    ]

    for record_type in record_types:
        record = record_type(date=date(2026, 1, 1), source="unit_test")

        assert record.date == date(2026, 1, 1)
        assert record.source == "unit_test"
        assert record.created_at is not None


def test_record_requires_date_and_source() -> None:
    with pytest.raises(ValidationError):
        MacroPolicyRecord(source="unit_test")

    with pytest.raises(ValidationError):
        MacroPolicyRecord(date=date(2026, 1, 1))

    with pytest.raises(ValidationError):
        MacroPolicyRecord(date=date(2026, 1, 1), source="")


def test_validate_required_fields() -> None:
    records = [{"date": date(2026, 1, 1), "source": ""}]

    with pytest.raises(ValueError, match="source"):
        validate_required_fields(records)


def test_validate_no_duplicate_dates() -> None:
    records = [
        MacroPolicyRecord(date=date(2026, 1, 1), source="unit_test"),
        MacroPolicyRecord(date=date(2026, 1, 1), source="unit_test"),
    ]

    with pytest.raises(ValueError, match="duplicate date"):
        validate_no_duplicate_dates(records)


def test_validate_sorted_by_date() -> None:
    records = [
        MacroPolicyRecord(date=date(2026, 1, 2), source="unit_test"),
        MacroPolicyRecord(date=date(2026, 1, 1), source="unit_test"),
    ]

    with pytest.raises(ValueError, match="not sorted"):
        validate_sorted_by_date(records)


def test_validate_time_series_accepts_valid_records() -> None:
    records = [
        MacroPolicyRecord(date=date(2026, 1, 1), source="unit_test"),
        MacroPolicyRecord(date=date(2026, 1, 2), source="unit_test"),
    ]

    validate_time_series(records)
