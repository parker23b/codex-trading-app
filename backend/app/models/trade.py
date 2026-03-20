from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    pnl: float = 0.0
    account_type: str
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str
    instrument: str = Field(index=True)
    direction: str
    size: float
    open_price: float
    close_price: float | None = None
    open_time: datetime
    close_time: datetime | None = None
    pnl: float | None = None
    account_type: str
    is_open: bool = True
    created_at: datetime = Field(default_factory=utc_now, nullable=False)

