from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import requests

TREASURY_TGA_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
    "accounting/dts/operating_cash_balance"
)
TREASURY_SOURCE = "treasury_fiscaldata_dts_operating_cash_balance"
TGA_ACCOUNT_KEYWORDS = [
    "Treasury General Account",
    "TGA",
    "Total Operating Balance",
    "Federal Reserve Account",
]


class TreasuryTgaError(ValueError):
    """Raised when Treasury TGA data cannot be fetched or standardized."""


def fetch_tga_operating_cash_balance(
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    page_size: int = 10000,
) -> pd.DataFrame:
    """Fetch Daily Treasury Statement operating cash balance data."""

    filters = [f"record_date:gte:{start_date}"]
    if end_date:
        filters.append(f"record_date:lte:{end_date}")

    rows: list[dict[str, Any]] = []
    # FiscalData can behave inconsistently with very large page sizes on this endpoint.
    # Keep the public argument, but use a conservative page size internally for reliable pagination.
    effective_page_size = min(page_size, 1000)
    page_number = 1
    while True:
        params = {
            "fields": "record_date,account_type,close_today_bal,open_today_bal",
            "filter": ",".join(filters),
            "sort": "record_date",
            "format": "json",
            "page[size]": effective_page_size,
            "page[number]": page_number,
        }
        try:
            response = requests.get(TREASURY_TGA_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            msg = f"Treasury FiscalData request failed: {exc.__class__.__name__}"
            raise TreasuryTgaError(msg) from None
        if response.status_code != 200:
            msg = f"Treasury FiscalData request failed: HTTP {response.status_code}"
            raise TreasuryTgaError(msg)

        payload = response.json()
        data = payload.get("data", [])
        if not data:
            break

        rows.extend(data)
        total_pages = _parse_total_pages(payload.get("meta", {}))
        if total_pages is not None:
            if page_number >= total_pages:
                break
        elif len(data) < effective_page_size:
            break
        page_number += 1

    raw = pd.DataFrame(rows)
    if raw.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "account_type",
                "close_today_bal_million",
                "open_today_bal_million",
                "source",
            ]
        )

    output = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["record_date"], errors="coerce"),
            "account_type": raw["account_type"].astype("string"),
            "close_today_bal_million": raw["close_today_bal"].map(_parse_amount),
            "open_today_bal_million": raw["open_today_bal"].map(_parse_amount),
            "source": TREASURY_SOURCE,
        }
    )
    output = output.dropna(subset=["date"])
    output = output.sort_values(["date", "account_type"])
    output = output.drop_duplicates(
        subset=["date", "account_type", "close_today_bal_million"], keep="last"
    )
    return output.reset_index(drop=True)


def build_tga_daily(raw_tga: pd.DataFrame) -> pd.DataFrame:
    """Select the best TGA candidate per date and standardize to billion USD."""

    data = _normalize_raw_tga(raw_tga)
    if data.empty:
        raise TreasuryTgaError("TGA data is empty after date parsing.")

    data["account_type_priority"] = data["account_type"].map(_account_type_priority)
    candidates = data.dropna(subset=["account_type_priority"]).copy()
    if candidates.empty:
        account_types = sorted(data["account_type"].dropna().unique())
        msg = (
            "Unable to identify TGA candidate account_type. "
            f"Available account_type values: {account_types}"
        )
        raise TreasuryTgaError(msg)

    selected_rows: list[pd.Series] = []
    for _, group in candidates.groupby("date", sort=True):
        selected_rows.append(_select_daily_tga_row(group))

    selected = pd.DataFrame(selected_rows).sort_values("date")
    selected["tga_million"] = _effective_balance_million(selected)
    selected["tga_billion"] = selected["tga_million"] / 1000

    if selected["tga_billion"].isna().all():
        raise TreasuryTgaError("tga_billion is entirely empty.")
    if (selected["tga_billion"].dropna() < 0).any():
        raise TreasuryTgaError("tga_billion contains negative values.")

    return selected[["date", "tga_million", "tga_billion", "account_type", "source"]].reset_index(
        drop=True
    )


def inspect_tga_account_types(raw_tga: pd.DataFrame) -> pd.DataFrame:
    """Summarize available FiscalData account_type coverage."""

    data = _normalize_raw_tga(raw_tga)
    if data.empty:
        return pd.DataFrame(
            columns=[
                "account_type",
                "first_date",
                "last_date",
                "count",
                "latest_value_million",
                "latest_value_billion",
            ]
        )

    rows: list[dict[str, Any]] = []
    data["effective_balance_million"] = _effective_balance_million(data)
    for account_type, group in data.sort_values("date").groupby("account_type", dropna=False):
        latest = group.dropna(subset=["effective_balance_million"]).tail(1)
        latest_value = None if latest.empty else float(latest.iloc[0]["effective_balance_million"])
        rows.append(
            {
                "account_type": account_type,
                "first_date": group["date"].min().strftime("%Y-%m-%d"),
                "last_date": group["date"].max().strftime("%Y-%m-%d"),
                "count": int(len(group)),
                "latest_value_million": latest_value,
                "latest_value_billion": None if latest_value is None else latest_value / 1000,
            }
        )
    return pd.DataFrame(rows).sort_values(["last_date", "account_type"]).reset_index(drop=True)


def validate_tga_daily(raw_tga: pd.DataFrame, tga_daily: pd.DataFrame) -> pd.DataFrame:
    """Validate selected TGA daily output and return selected account_type distribution."""

    raw = _normalize_raw_tga(raw_tga)
    daily = tga_daily.copy()
    if raw.empty:
        raise TreasuryTgaError("raw_tga is empty.")
    if daily.empty:
        raise TreasuryTgaError("tga_daily is empty.")

    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["tga_billion"] = pd.to_numeric(daily["tga_billion"], errors="coerce")
    if daily["tga_billion"].isna().all():
        raise TreasuryTgaError("tga_billion is entirely empty.")
    if (daily["tga_billion"].dropna() < 0).any():
        raise TreasuryTgaError("tga_billion contains negative values.")

    raw_latest = raw["date"].max()
    daily_latest = daily["date"].max()
    if (raw_latest - daily_latest).days > 10:
        raise TreasuryTgaError(
            f"tga_daily latest date {daily_latest.date()} is more than 10 days older than "
            f"raw_tga latest date {raw_latest.date()}."
        )
    if daily_latest <= pd.Timestamp("2021-09-30"):
        raise TreasuryTgaError(
            "TGA selection likely failed: output ends at 2021-09-30 or earlier."
        )

    selected_types = set(daily["account_type"].dropna().astype(str).unique())
    raw_types = set(raw["account_type"].dropna().astype(str).unique())
    raw_has_tga = any(_contains_tga_keyword(account_type) for account_type in raw_types)
    selected_only_fed = selected_types == {"Federal Reserve Account"}
    if selected_only_fed and raw_has_tga:
        raise TreasuryTgaError("Treasury General Account exists but was not selected.")

    return _account_type_distribution(daily)


def save_tga_raw(data: pd.DataFrame, output: Path) -> Path:
    """Write complete raw Treasury operating cash balance data to CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output, index=False)
    return output


def save_tga_account_type_summary(data: pd.DataFrame, output: Path) -> Path:
    """Write account_type coverage summary to CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output, index=False)
    return output


def save_tga_daily(data: pd.DataFrame, output: Path) -> Path:
    """Write standardized TGA daily data to CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output, index=False)
    return output


def _normalize_raw_tga(raw_tga: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"date", "account_type", "close_today_bal_million", "source"}
    missing_columns = required_columns - set(raw_tga.columns)
    if missing_columns:
        msg = f"TGA data missing required columns: {sorted(missing_columns)}"
        raise TreasuryTgaError(msg)

    data = raw_tga.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["account_type"] = data["account_type"].astype("string")
    data["close_today_bal_million"] = data["close_today_bal_million"].map(_parse_amount)
    if "open_today_bal_million" in data.columns:
        data["open_today_bal_million"] = data["open_today_bal_million"].map(_parse_amount)
    data = data.dropna(subset=["date"])
    data = data.sort_values(["date", "account_type", "close_today_bal_million"])
    return data.drop_duplicates().reset_index(drop=True)


def _account_type_priority(account_type: Any) -> int | None:
    text = str(account_type).lower()
    if "treasury general account" in text and "closing balance" in text:
        return 1
    if "tga" in text and "closing balance" in text:
        return 2
    if "treasury general account" in text:
        return 3
    if "total operating balance" in text:
        return 4
    if "federal reserve account" in text:
        return 5
    return None


def _select_daily_tga_row(group: pd.DataFrame) -> pd.Series:
    best_priority = group["account_type_priority"].min()
    best = group[group["account_type_priority"] == best_priority].copy()
    if len(best) > 1:
        non_missing = best.dropna(subset=["close_today_bal_million"])
        if not non_missing.empty:
            best = non_missing
    if len(best) > 1:
        account_types = sorted(best["account_type"].dropna().astype(str).unique())
        print(
            "Warning: multiple TGA candidates for "
            f"{pd.Timestamp(group['date'].iloc[0]).date()} at priority {best_priority}: "
            f"{account_types}. Keeping first row."
        )
    return best.iloc[0]


def _account_type_distribution(tga_daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for account_type, group in tga_daily.sort_values("date").groupby("account_type", dropna=False):
        rows.append(
            {
                "account_type": account_type,
                "first_date": group["date"].min().strftime("%Y-%m-%d"),
                "last_date": group["date"].max().strftime("%Y-%m-%d"),
                "count": int(len(group)),
            }
        )
    return pd.DataFrame(rows).sort_values(["first_date", "account_type"]).reset_index(drop=True)


def _effective_balance_million(data: pd.DataFrame) -> pd.Series:
    balance = pd.to_numeric(data["close_today_bal_million"], errors="coerce")
    if "open_today_bal_million" in data.columns:
        # New FiscalData DTS rows label the account_type as "Closing Balance" but often
        # publish the usable balance in open_today_bal while close_today_bal is blank.
        balance = balance.combine_first(pd.to_numeric(data["open_today_bal_million"], errors="coerce"))
    return balance


def _contains_tga_keyword(account_type: str) -> bool:
    text = account_type.lower()
    return "treasury general account" in text or "tga" in text


def _parse_amount(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.lower() in {"", "na", "nan", "null", "none"}:
            return None
        return float(cleaned)
    return float(value)


def _parse_total_pages(meta: dict[str, Any]) -> int | None:
    value = meta.get("total-pages")
    if value is None:
        return None
    return int(value)
