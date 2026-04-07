from datetime import datetime

from sqlmodel import Session, desc, select

from app.models.trade import Execution, ExecutionStatus, Position, ReconciliationEvent, Trade, utc_now


class TradeService:
    def __init__(self, session: Session):
        self.session = session

    def list_trades(
        self,
        *,
        strategy_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Trade]:
        statement = select(Trade)
        if strategy_name:
            statement = statement.where(Trade.strategy_name == strategy_name)
        if date_from:
            statement = statement.where(Trade.close_time >= date_from)
        if date_to:
            statement = statement.where(Trade.close_time <= date_to)
        statement = statement.order_by(desc(Trade.close_time))
        return list(self.session.exec(statement).all())

    def list_positions(self) -> list[Position]:
        statement = select(Position).where(Position.is_open.is_(True)).order_by(desc(Position.open_time))
        return list(self.session.exec(statement).all())

    def list_executions(self, *, limit: int = 100) -> list[Execution]:
        statement = select(Execution).order_by(desc(Execution.last_transition_at)).limit(limit)
        return list(self.session.exec(statement).all())

    def list_reconciliation_events(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 250,
    ) -> list[ReconciliationEvent]:
        statement = select(ReconciliationEvent).order_by(desc(ReconciliationEvent.created_at)).limit(limit)
        if date_from:
            statement = statement.where(ReconciliationEvent.created_at >= date_from)
        if date_to:
            statement = statement.where(ReconciliationEvent.created_at <= date_to)
        return list(self.session.exec(statement).all())

    def get_trade(self, trade_id: int) -> Trade | None:
        statement = select(Trade).where(Trade.id == trade_id)
        return self.session.exec(statement).first()

    def list_all_open_positions(self) -> list[Position]:
        statement = select(Position).where(Position.is_open.is_(True))
        return list(self.session.exec(statement).all())

    def get_open_position(
        self,
        instrument: str,
        strategy_name: str | None = None,
        broker_reference: str | None = None,
    ) -> Position | None:
        statement = select(Position).where(Position.is_open.is_(True))
        if broker_reference is not None:
            statement = statement.where(Position.broker_reference == broker_reference)
        else:
            statement = statement.where(Position.instrument == instrument)
        if strategy_name is not None:
            statement = statement.where(Position.strategy_name == strategy_name)
        return self.session.exec(statement).first()

    def record_trade(self, trade: Trade) -> Trade:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def create_execution(self, execution: Execution) -> Execution:
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
        return execution

    def transition_execution(
        self,
        execution: Execution,
        *,
        status: ExecutionStatus | str,
        broker_reference: str | None = None,
        local_position_id: int | None = None,
        local_trade_id: int | None = None,
        submitted_at: datetime | None = None,
        acknowledged_at: datetime | None = None,
        completed_at: datetime | None = None,
        filled_size: float | None = None,
        average_fill_price: float | None = None,
        reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        requires_manual_review: bool | None = None,
        details: dict[str, object] | None = None,
    ) -> Execution:
        execution.status = status.value if isinstance(status, ExecutionStatus) else status
        execution.last_transition_at = completed_at or acknowledged_at or submitted_at or utc_now()
        execution.updated_at = utc_now()
        if broker_reference is not None:
            execution.broker_reference = broker_reference
        if local_position_id is not None:
            execution.local_position_id = local_position_id
        if local_trade_id is not None:
            execution.local_trade_id = local_trade_id
        if submitted_at is not None:
            execution.submitted_at = submitted_at
        if acknowledged_at is not None:
            execution.acknowledged_at = acknowledged_at
        if completed_at is not None:
            execution.completed_at = completed_at
        if filled_size is not None:
            execution.filled_size = filled_size
        if average_fill_price is not None:
            execution.average_fill_price = average_fill_price
        if reason is not None:
            execution.reason = reason
        if error_code is not None:
            execution.error_code = error_code
        if error_message is not None:
            execution.error_message = error_message
        if requires_manual_review is not None:
            execution.requires_manual_review = requires_manual_review
        if details:
            execution.details = {**(execution.details or {}), **details}
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
        return execution

    def record_broker_position(self, position: Position) -> Position:
        if position.broker_open_confirmed_at is None:
            position.broker_open_confirmed_at = position.open_time
        position.broker_sync_status = "CONFIRMED"
        position.last_reconciled_at = utc_now()
        return self.upsert_position(position)

    def update_position_analytics(
        self,
        position: Position,
        *,
        current_price: float,
        unrealized_pnl: float,
        risk_percent: float | None = None,
        pnl: float | None = None,
        reason: str | None = None,
    ) -> Position:
        position.current_price = current_price
        position.unrealized_pnl = round(unrealized_pnl, 2)
        if risk_percent is not None:
            position.risk_percent = risk_percent
        if pnl is not None:
            position.pnl = round(pnl, 2)
        if reason is not None:
            position.reason = reason
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def upsert_position(self, position: Position) -> Position:
        existing = self.get_open_position(
            position.instrument,
            strategy_name=position.strategy_name,
            broker_reference=position.broker_reference,
        )
        if existing is not None:
            for field_name in (
                "strategy_name",
                "broker_reference",
                "direction",
                "size",
                "open_price",
                "close_price",
                "open_time",
                "close_time",
                "pnl",
                "current_price",
                "unrealized_pnl",
                "risk_percent",
                "reason",
                "manual_override",
                "account_type",
                "is_open",
                "broker_sync_status",
                "broker_open_confirmed_at",
                "broker_closed_confirmed_at",
                "last_reconciled_at",
            ):
                setattr(existing, field_name, getattr(position, field_name))
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def close_position(
        self,
        position: Position,
        *,
        close_price: float | None = None,
        close_time: datetime | None = None,
        pnl: float | None = None,
        broker_sync_status: str = "CONFIRMED",
        close_reason: str | None = None,
        broker_confirmed_at: datetime | None = None,
    ) -> Position:
        position.is_open = False
        position.close_price = close_price if close_price is not None else position.close_price
        position.close_time = close_time if close_time is not None else position.close_time
        position.pnl = pnl if pnl is not None else position.pnl
        position.current_price = position.close_price if position.close_price is not None else position.current_price
        position.unrealized_pnl = 0.0
        position.broker_sync_status = broker_sync_status
        position.broker_closed_confirmed_at = broker_confirmed_at or position.close_time or utc_now()
        position.last_reconciled_at = utc_now()
        if close_reason is not None:
            position.reason = close_reason
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    def record_reconciliation_event(
        self,
        *,
        event_type: str,
        strategy_name: str | None,
        instrument: str | None,
        broker_reference: str | None,
        local_position_id: int | None,
        details: dict[str, object] | None = None,
    ) -> ReconciliationEvent:
        event = ReconciliationEvent(
            event_type=event_type,
            strategy_name=strategy_name,
            instrument=instrument,
            broker_reference=broker_reference,
            local_position_id=local_position_id,
            details=details or {},
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event
