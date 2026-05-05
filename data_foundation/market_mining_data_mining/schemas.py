from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseRecord(BaseModel):
    date: date
    source: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)


class MacroPolicyRecord(BaseRecord):
    pass


class UsdLiquidityRecord(BaseRecord):
    pass


class StablecoinLiquidityRecord(BaseRecord):
    pass


class RiskAppetiteRecord(BaseRecord):
    pass


class InstitutionalFlowRecord(BaseRecord):
    pass


class CryptoConfirmationRecord(BaseRecord):
    pass


class MarketStateRecord(BaseRecord):
    pass
