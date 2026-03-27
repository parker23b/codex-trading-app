from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
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


class ExecutionPhase(str, Enum):
    ENTRY = "ENTRY"
    CLOSE = "CLOSE"


class ExecutionStatus(str, Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    FILL_PARTIAL = "FILL_PARTIAL"
    FILL_FULL = "FILL_FULL"
    POSITION_OPENED = "POSITION_OPENED"
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"


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


class Execution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str = Field(index=True)
    instrument: str = Field(index=True)
    phase: str = Field(index=True)
    status: str = Field(index=True)
    broker_reference: str | None = Field(default=None, index=True)
    local_position_id: int | None = Field(default=None, index=True)
    local_trade_id: int | None = Field(default=None, index=True)
    signal_time: datetime
    submitted_at: datetime | None = None
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    last_transition_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    requested_size: float | None = None
    filled_size: float | None = None
    requested_price: float | None = None
    average_fill_price: float | None = None
    reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    requires_manual_review: bool = False
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


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
    return Position(
        id=position.id,
        strategy_name=position.strategy_name,
        broker_reference=position.broker_reference,
        instrument=position.instrument,
        direction=position.direction,
        size=position.size,
        open_price=position.open_price,
        close_price=position.close_price,
        open_time=position.open_time,
        close_time=position.close_time,
        pnl=position.pnl,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        risk_percent=position.risk_percent,
        reason=position.reason,
        manual_override=position.manual_override,
        account_type=position.account_type,
        is_open=position.is_open,
        broker_sync_status=position.broker_sync_status,
        broker_open_confirmed_at=position.broker_open_confirmed_at,
        broker_closed_confirmed_at=position.broker_closed_confirmed_at,
        last_reconciled_at=position.last_reconciled_at,
        created_at=position.created_at,
    )
