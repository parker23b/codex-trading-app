from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from app.models.trade import Position, Trade


class TradeResponse(BaseModel):
    id: int
    strategy_name: str
    broker_reference: str | None
    close_broker_reference: str | None
    close_execution_source: str | None
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    pnl: float
    entry_risk_amount: float | None
    risk_truth_confidence: str | None
    account_type: str
    r_multiple: float | None
    reason: str | None
    outcome: str


class OpenPositionResponse(BaseModel):
    id: int
    strategy_name: str
    broker_reference: str | None
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float | None
    open_time: datetime
    close_time: datetime | None
    pnl: float | None
    account_type: str
    is_open: bool
    current_price: float | None
    unrealized_pnl: float | None
    risk_percent: float | None
    entry_risk_amount: float | None
    risk_truth_confidence: str | None
    broker_sync_status: str | None
    close_execution_source: str | None
    reason: str | None
    manual_override: bool
    time_in_trade_seconds: int


def serialize_trade(trade: Trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id or 0,
        strategy_name=trade.strategy_name,
        broker_reference=trade.broker_reference,
        close_broker_reference=trade.close_broker_reference,
        close_execution_source=trade.close_execution_source,
        instrument=trade.instrument,
        direction=trade.direction,
        size=trade.size,
        open_price=trade.open_price,
        close_price=trade.close_price,
        open_time=trade.open_time,
        close_time=trade.close_time,
        pnl=trade.pnl,
        entry_risk_amount=trade.entry_risk_amount,
        risk_truth_confidence=trade.risk_truth_confidence,
        account_type=trade.account_type,
        r_multiple=trade.r_multiple,
        reason=trade.reason,
        outcome=trade.outcome or ("win" if trade.pnl > 0 else "loss"),
    )


def serialize_open_position(
    position: Position, *, now: datetime | None = None
) -> OpenPositionResponse:
    current_time = now or datetime.now(UTC)
    return OpenPositionResponse(
        id=position.id or 0,
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
        account_type=position.account_type,
        is_open=position.is_open,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        risk_percent=position.risk_percent,
        entry_risk_amount=position.entry_risk_amount,
        risk_truth_confidence=position.risk_truth_confidence,
        broker_sync_status=position.broker_sync_status,
        close_execution_source=position.close_execution_source,
        reason=position.reason,
        manual_override=position.manual_override,
        time_in_trade_seconds=max(
            int((current_time - position.open_time.astimezone(UTC)).total_seconds()), 0
        ),
    )
