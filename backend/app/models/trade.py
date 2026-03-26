from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str
    broker_reference: str | None = Field(default=None, index=True)
    close_broker_reference: str | None = Field(default=None, index=True)
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    pnl: float = 0.0
    r_multiple: float | None = None
    outcome: str | None = None
    reason: str | None = None
    account_type: str
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str
    broker_reference: str | None = Field(default=None, index=True)
    instrument: str = Field(index=True)
    direction: str
    size: float
    open_price: float
    close_price: float | None = None
    open_time: datetime
    close_time: datetime | None = None
    pnl: float | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None
    risk_percent: float | None = None
    reason: str | None = None
    manual_override: bool = False
    account_type: str
    is_open: bool = True
    broker_sync_status: str = Field(default="PENDING", index=True)
    broker_open_confirmed_at: datetime | None = None
    broker_closed_confirmed_at: datetime | None = None
    last_reconciled_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class ReconciliationEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_type: str = Field(index=True)
    strategy_name: str | None = Field(default=None, index=True)
    instrument: str | None = Field(default=None, index=True)
    broker_reference: str | None = Field(default=None, index=True)
    local_position_id: int | None = Field(default=None, index=True)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


def clone_position(position: Position | None) -> Position | None:
    if position is None:
        return None
    return Position.model_validate(position.model_dump())
