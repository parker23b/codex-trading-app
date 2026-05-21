from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Column, Index, text
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_intent_id: int | None = Field(default=None, index=True)
    strategy_name: str
    family_name: str | None = Field(default=None, index=True)
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
    entry_risk_amount: float | None = None
    risk_truth_confidence: str | None = None
    close_execution_source: str | None = Field(default=None, index=True)
    r_multiple: float | None = None
    outcome: str | None = None
    reason: str | None = None
    account_type: str
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class ExecutionPhase(str, Enum):
    ENTRY = "ENTRY"
    CLOSE = "CLOSE"


class ExecutionStatus(str, Enum):
    """
    Execution-attempt lifecycle states.

    New execution rows are written only with execution-oriented states, starting
    at `SUBMISSION_PENDING`. Legacy decision-style values remain only for
    backward compatibility with older persisted rows and should not be written
    by new code paths.
    """

    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    # Deprecated legacy decision states; retained for old rows only.
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    FILL_PARTIAL = "FILL_PARTIAL"
    FILL_FULL = "FILL_FULL"
    POSITION_OPENED = "POSITION_OPENED"
    # Deprecated legacy bridge state; close intent authority lives on TradeIntent.
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"


class TradeIntentState(str, Enum):
    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    POSITION_OPENED = "POSITION_OPENED"
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXTERNAL_POSITION_ADOPTED = "EXTERNAL_POSITION_ADOPTED"
    RECOVERED_POSITION_ATTACHED = "RECOVERED_POSITION_ATTACHED"
    FORCED_RECONCILIATION_CLOSE = "FORCED_RECONCILIATION_CLOSE"


ACTIVE_INSTRUMENT_OWNERSHIP_STATES = (
    TradeIntentState.PROPOSED.value,
    TradeIntentState.APPROVED.value,
    TradeIntentState.SUBMITTED.value,
    TradeIntentState.ACKNOWLEDGED.value,
    TradeIntentState.PARTIALLY_FILLED.value,
    TradeIntentState.FILLED.value,
    TradeIntentState.POSITION_OPENED.value,
    TradeIntentState.CLOSE_REQUESTED.value,
    TradeIntentState.EXTERNAL_POSITION_ADOPTED.value,
    TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
)

_ACTIVE_INSTRUMENT_OWNERSHIP_SQL = ", ".join(
    f"'{state}'" for state in ACTIVE_INSTRUMENT_OWNERSHIP_STATES
)


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_intent_id: int | None = Field(default=None, index=True)
    strategy_name: str
    family_name: str | None = Field(default=None, index=True)
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
    entry_risk_amount: float | None = None
    risk_truth_confidence: str | None = None
    reason: str | None = None
    manual_override: bool = False
    account_type: str
    is_open: bool = True
    broker_sync_status: str = Field(default="PENDING", index=True)
    close_execution_source: str | None = Field(default=None, index=True)
    broker_open_confirmed_at: datetime | None = None
    broker_closed_confirmed_at: datetime | None = None
    last_reconciled_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Execution(SQLModel, table=True):
    """
    Broker-attempt audit record linked to a TradeIntent.

    New writes begin at `SUBMISSION_PENDING` once an intent has already been
    admitted. Legacy decision-style statuses may still exist in older rows, but
    TradeIntent is the authoritative source of decision truth.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    trade_intent_id: int | None = Field(default=None, index=True)
    strategy_name: str = Field(index=True)
    instrument: str = Field(index=True)
    phase: str = Field(index=True)
    status: str = Field(index=True)
    client_request_id: str | None = Field(default=None, index=True)
    broker_reference: str | None = Field(default=None, index=True)
    local_position_id: int | None = Field(default=None, index=True)
    local_trade_id: int | None = Field(default=None, index=True)
    signal_time: datetime
    submitted_at: datetime | None = None
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    last_transition_at: datetime = Field(
        default_factory=utc_now, nullable=False, index=True
    )
    requested_size: float | None = None
    filled_size: float | None = None
    requested_price: float | None = None
    average_fill_price: float | None = None
    intended_risk_amount: float | None = None
    submitted_risk_amount: float | None = None
    fill_derived_risk_amount: float | None = None
    risk_truth_confidence: str | None = None
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
    trade_intent_id: int | None = Field(default=None, index=True)
    strategy_name: str | None = Field(default=None, index=True)
    instrument: str | None = Field(default=None, index=True)
    broker_reference: str | None = Field(default=None, index=True)
    local_position_id: int | None = Field(default=None, index=True)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class TradeIntent(SQLModel, table=True):
    """
    Authoritative lifecycle record for a trade decision.

    A raw strategy signal becomes durable when it is persisted here as
    `PROPOSED`. Only intents transitioned to `APPROVED` may become execution
    attempts. Broker submission, fills, position-open events, closes, and
    reconciliation-only outcomes all attach back to this record.
    """

    __table_args__ = (
        Index(
            "uq_trade_intent_active_instrument",
            "instrument",
            unique=True,
            sqlite_where=text(f"state IN ({_ACTIVE_INSTRUMENT_OWNERSHIP_SQL})"),
            postgresql_where=text(f"state IN ({_ACTIVE_INSTRUMENT_OWNERSHIP_SQL})"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_name: str = Field(index=True)
    family_name: str | None = Field(default=None, index=True)
    allocation_cycle_id: str | None = Field(default=None, index=True)
    instrument: str = Field(index=True)
    direction: str = Field(index=True)
    state: str = Field(default=TradeIntentState.PROPOSED.value, index=True)
    signal_time: datetime
    proposed_size: float | None = None
    allocated_size: float | None = None
    proposed_risk_percent: float | None = None
    allocated_risk_percent: float | None = None
    estimated_risk_amount: float | None = None
    submitted_risk_amount: float | None = None
    fill_derived_risk_amount: float | None = None
    risk_truth_confidence: str | None = None
    risk_currency: str | None = None
    confidence: float | None = None
    observed_price: float | None = None
    average_fill_price: float | None = None
    filled_size: float | None = None
    broker_reference: str | None = Field(default=None, index=True)
    close_broker_reference: str | None = Field(default=None, index=True)
    position_id: int | None = Field(default=None, index=True)
    trade_id: int | None = Field(default=None, index=True)
    decision_reason_code: str | None = Field(default=None, index=True)
    decision_reason: str | None = None
    close_reason_code: str | None = Field(default=None, index=True)
    close_reason: str | None = None
    execution_client_request_id: str | None = Field(default=None, index=True)
    market_status: str | None = None
    tradable: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    submitted_at: datetime | None = None
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class AllocationCycle(SQLModel, table=True):
    __table_args__ = (
        Index("ix_allocationcycle_received_at_desc", text("received_at DESC")),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cycle_id: str = Field(index=True, unique=True)
    received_at: datetime = Field(index=True)
    completed_at: datetime = Field(default_factory=utc_now, index=True)
    candidate_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    total_requested_risk_percent: float = 0.0
    total_allocated_risk_percent: float = 0.0
    remaining_portfolio_risk_percent: float = 0.0
    resized_candidate_count: int = 0
    degraded_candidate_count: int = 0
    blocked_unsupported_sizing_count: int = 0
    blocked_approximate_live_count: int = 0
    blocked_under_minimum_size_count: int = 0
    blocked_budget_count: int = 0
    blocked_conflict_count: int = 0
    binding_budget_counts: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    rejection_reason_counts: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


def clone_position(position: Position | None) -> Position | None:
    if position is None:
        return None
    return Position(
        id=position.id,
        trade_intent_id=position.trade_intent_id,
        strategy_name=position.strategy_name,
        family_name=position.family_name,
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
        entry_risk_amount=position.entry_risk_amount,
        risk_truth_confidence=position.risk_truth_confidence,
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
