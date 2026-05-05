from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from market_mining_data_mining.schemas import BaseRecord


def _get_value(record: BaseRecord | dict[str, Any], field_name: str) -> Any:
    if isinstance(record, BaseRecord):
        return getattr(record, field_name)
    return record.get(field_name)


def validate_required_fields(
    records: Iterable[BaseRecord | dict[str, Any]],
    required_fields: Sequence[str] = ("date", "source"),
) -> None:
    """Validate that each record contains required non-empty fields."""

    for index, record in enumerate(records):
        for field_name in required_fields:
            value = _get_value(record, field_name)
            if value is None or value == "":
                msg = f"record at index {index} is missing required field: {field_name}"
                raise ValueError(msg)


def validate_no_duplicate_dates(records: Iterable[BaseRecord | dict[str, Any]]) -> None:
    """Validate that no two records share the same date."""

    seen_dates: set[date] = set()
    for index, record in enumerate(records):
        record_date = _get_value(record, "date")
        if record_date in seen_dates:
            msg = f"duplicate date at index {index}: {record_date}"
            raise ValueError(msg)
        seen_dates.add(record_date)


def validate_sorted_by_date(records: Iterable[BaseRecord | dict[str, Any]]) -> None:
    """Validate that records are sorted by date in ascending order."""

    previous_date: date | None = None
    for index, record in enumerate(records):
        current_date = _get_value(record, "date")
        if previous_date is not None and current_date < previous_date:
            msg = f"records are not sorted by date at index {index}: {current_date}"
            raise ValueError(msg)
        previous_date = current_date


def validate_time_series(records: Sequence[BaseRecord | dict[str, Any]]) -> None:
    """Run the base Step 1 data contract checks for a daily time series."""

    validate_required_fields(records)
    validate_no_duplicate_dates(records)
    validate_sorted_by_date(records)
