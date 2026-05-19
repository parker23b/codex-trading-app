from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, select

from app.models.allocation_alert import AllocationAlert
from app.models.trade import (
    ACTIVE_INSTRUMENT_OWNERSHIP_STATES,
    AllocationCycle,
    Execution,
    ExecutionStatus,
    Position,
    ReconciliationEvent,
    Trade,
    TradeIntent,
    TradeIntentState,
    utc_now,
)
from app.services.domain_event_service import domain_event_service


class ActiveTradeIntentConflictError(RuntimeError):
    def __init__(
        self, *, instrument: str, conflicting_intent_id: int | None = None
    ) -> None:
        self.instrument = instrument
        self.conflicting_intent_id = conflicting_intent_id
        message = f"Instrument {instrument} already has an active trade intent."
        if conflicting_intent_id is not None:
            message = f"{message} Conflicting intent id: {conflicting_intent_id}."
        super().__init__(message)


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
        statement = (
            select(Position)
            .where(Position.is_open.is_(True))
            .order_by(desc(Position.open_time))
        )
        return list(self.session.exec(statement).all())

    def list_executions(self, *, limit: int = 100) -> list[Execution]:
        statement = (
            select(Execution).order_by(desc(Execution.last_transition_at)).limit(limit)
        )
        return list(self.session.exec(statement).all())

    def list_executions_for_trade_intent(self, trade_intent_id: int) -> list[Execution]:
        statement = (
            select(Execution)
            .where(Execution.trade_intent_id == trade_intent_id)
            .order_by(desc(Execution.last_transition_at), desc(Execution.id))
        )
        return list(self.session.exec(statement).all())

    def get_latest_execution_for_trade_intent(
        self, trade_intent_id: int
    ) -> Execution | None:
        statement = (
            select(Execution)
            .where(Execution.trade_intent_id == trade_intent_id)
            .order_by(desc(Execution.last_transition_at), desc(Execution.id))
            .limit(1)
        )
        return self.session.exec(statement).first()

    def list_trade_intents(
        self,
        *,
        limit: int = 250,
        allocation_cycle_id: str | None = None,
        strategy_name: str | None = None,
        instrument: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        states: set[str] | tuple[str, ...] | list[str] | None = None,
    ) -> list[TradeIntent]:
        statement = select(TradeIntent)
        if allocation_cycle_id is not None:
            statement = statement.where(
                TradeIntent.allocation_cycle_id == allocation_cycle_id
            )
        if strategy_name is not None:
            statement = statement.where(TradeIntent.strategy_name == strategy_name)
        if instrument is not None:
            statement = statement.where(TradeIntent.instrument == instrument)
        if date_from is not None:
            statement = statement.where(TradeIntent.updated_at >= date_from)
        if date_to is not None:
            statement = statement.where(TradeIntent.updated_at <= date_to)
        if states:
            statement = statement.where(TradeIntent.state.in_(tuple(states)))
        statement = statement.order_by(desc(TradeIntent.updated_at)).limit(limit)
        return list(self.session.exec(statement).all())

    def list_reconciliation_events(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 250,
    ) -> list[ReconciliationEvent]:
        statement = (
            select(ReconciliationEvent)
            .order_by(desc(ReconciliationEvent.created_at))
            .limit(limit)
        )
        if date_from:
            statement = statement.where(ReconciliationEvent.created_at >= date_from)
        if date_to:
            statement = statement.where(ReconciliationEvent.created_at <= date_to)
        return list(self.session.exec(statement).all())

    def get_trade(self, trade_id: int) -> Trade | None:
        statement = select(Trade).where(Trade.id == trade_id)
        return self.session.exec(statement).first()

    def get_position_by_id(self, position_id: int) -> Position | None:
        statement = select(Position).where(Position.id == position_id)
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

    def create_trade_intent(self, intent: TradeIntent) -> TradeIntent:
        try:
            self.session.add(intent)
            self.session.commit()
            self.session.refresh(intent)
            return intent
        except IntegrityError as exc:
            self.session.rollback()
            if intent.state in ACTIVE_INSTRUMENT_OWNERSHIP_STATES:
                conflicting = self.find_active_trade_intent_for_instrument_excluding(
                    intent.instrument,
                    exclude_intent_id=intent.id,
                )
                raise ActiveTradeIntentConflictError(
                    instrument=intent.instrument,
                    conflicting_intent_id=conflicting.id
                    if conflicting is not None
                    else None,
                ) from exc
            raise

    def get_trade_intent(self, trade_intent_id: int) -> TradeIntent | None:
        statement = select(TradeIntent).where(TradeIntent.id == trade_intent_id)
        return self.session.exec(statement).first()

    def list_allocation_cycles(self, *, limit: int = 100) -> list[AllocationCycle]:
        statement = (
            select(AllocationCycle)
            .order_by(desc(AllocationCycle.received_at), desc(AllocationCycle.id))
            .limit(limit)
        )
        return list(self.session.exec(statement).all())

    def get_allocation_cycle(self, cycle_id: str) -> AllocationCycle | None:
        statement = select(AllocationCycle).where(AllocationCycle.cycle_id == cycle_id)
        return self.session.exec(statement).first()

    def record_allocation_cycle(
        self, allocation_cycle: AllocationCycle
    ) -> AllocationCycle:
        self.session.add(allocation_cycle)
        self.session.commit()
        self.session.refresh(allocation_cycle)
        return allocation_cycle

    def list_allocation_alerts(
        self,
        *,
        limit: int = 100,
        states: set[str] | tuple[str, ...] | list[str] | None = None,
    ) -> list[AllocationAlert]:
        statement = select(AllocationAlert)
        if states:
            statement = statement.where(AllocationAlert.state.in_(tuple(states)))
        statement = statement.order_by(
            desc(AllocationAlert.updated_at), desc(AllocationAlert.id)
        ).limit(limit)
        return list(self.session.exec(statement).all())

    def get_allocation_alert(self, alert_id: int) -> AllocationAlert | None:
        statement = select(AllocationAlert).where(AllocationAlert.id == alert_id)
        return self.session.exec(statement).first()

    def get_allocation_alert_by_key(self, alert_key: str) -> AllocationAlert | None:
        statement = select(AllocationAlert).where(
            AllocationAlert.alert_key == alert_key
        )
        return self.session.exec(statement).first()

    def upsert_allocation_alert(self, alert: AllocationAlert) -> AllocationAlert:
        self.session.add(alert)
        self.session.commit()
        self.session.refresh(alert)
        return alert

    def find_active_trade_intent_for_instrument(
        self, instrument: str
    ) -> TradeIntent | None:
        return self.find_active_trade_intent_for_instrument_excluding(
            instrument, exclude_intent_id=None
        )

    def find_active_trade_intent_for_instrument_excluding(
        self,
        instrument: str,
        *,
        exclude_intent_id: int | None,
    ) -> TradeIntent | None:
        statement = (
            select(TradeIntent)
            .where(TradeIntent.instrument == instrument)
            .where(TradeIntent.state.in_(ACTIVE_INSTRUMENT_OWNERSHIP_STATES))
            .order_by(desc(TradeIntent.updated_at))
        )
        if exclude_intent_id is not None:
            statement = statement.where(TradeIntent.id != exclude_intent_id)
        return self.session.exec(statement).first()

    def find_active_trade_intent_by_broker_reference(
        self, *, instrument: str, broker_reference: str
    ) -> TradeIntent | None:
        statement = (
            select(TradeIntent)
            .where(TradeIntent.instrument == instrument)
            .where(TradeIntent.broker_reference == broker_reference)
            .where(TradeIntent.state.in_(ACTIVE_INSTRUMENT_OWNERSHIP_STATES))
            .order_by(desc(TradeIntent.updated_at))
        )
        return self.session.exec(statement).first()

    def find_open_trade_intent(
        self,
        *,
        strategy_name: str | None = None,
        instrument: str | None = None,
        broker_reference: str | None = None,
        position_id: int | None = None,
    ) -> TradeIntent | None:
        statement = select(TradeIntent).where(
            TradeIntent.state.in_(
                {
                    TradeIntentState.PARTIALLY_FILLED.value,
                    TradeIntentState.POSITION_OPENED.value,
                    TradeIntentState.CLOSE_REQUESTED.value,
                    TradeIntentState.EXTERNAL_POSITION_ADOPTED.value,
                    TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
                }
            )
        )
        if strategy_name is not None:
            statement = statement.where(TradeIntent.strategy_name == strategy_name)
        if instrument is not None:
            statement = statement.where(TradeIntent.instrument == instrument)
        if broker_reference is not None:
            statement = statement.where(
                TradeIntent.broker_reference == broker_reference
            )
        if position_id is not None:
            statement = statement.where(TradeIntent.position_id == position_id)
        statement = statement.order_by(desc(TradeIntent.updated_at))
        return self.session.exec(statement).first()

    def find_close_admissible_trade_intent(
        self,
        *,
        strategy_name: str,
        instrument: str,
        broker_reference: str | None = None,
        position_id: int | None = None,
    ) -> TradeIntent | None:
        statement = select(TradeIntent).where(
            TradeIntent.strategy_name == strategy_name,
            TradeIntent.instrument == instrument,
            TradeIntent.state.in_(
                {
                    TradeIntentState.PARTIALLY_FILLED.value,
                    TradeIntentState.POSITION_OPENED.value,
                    TradeIntentState.CLOSE_REQUESTED.value,
                    TradeIntentState.SUBMITTED.value,
                    TradeIntentState.ACKNOWLEDGED.value,
                    TradeIntentState.EXTERNAL_POSITION_ADOPTED.value,
                    TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
                }
            ),
        )
        if broker_reference is not None:
            statement = statement.where(
                TradeIntent.broker_reference == broker_reference
            )
        if position_id is not None:
            statement = statement.where(TradeIntent.position_id == position_id)
        statement = statement.order_by(desc(TradeIntent.updated_at))
        return self.session.exec(statement).first()

    def list_recent_trade_intents(
        self,
        *,
        signal_time_from: datetime,
        strategy_name: str | None = None,
        instrument: str | None = None,
    ) -> list[TradeIntent]:
        statement = (
            select(TradeIntent)
            .where(TradeIntent.signal_time >= signal_time_from)
            .order_by(desc(TradeIntent.signal_time))
        )
        if strategy_name is not None:
            statement = statement.where(TradeIntent.strategy_name == strategy_name)
        if instrument is not None:
            statement = statement.where(TradeIntent.instrument == instrument)
        return list(self.session.exec(statement).all())

    def has_pending_trade_intents(self) -> bool:
        pending_states = (
            TradeIntentState.PROPOSED.value,
            TradeIntentState.APPROVED.value,
            TradeIntentState.SUBMITTED.value,
            TradeIntentState.ACKNOWLEDGED.value,
            TradeIntentState.PARTIALLY_FILLED.value,
            TradeIntentState.CLOSE_REQUESTED.value,
            TradeIntentState.EXTERNAL_POSITION_ADOPTED.value,
            TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
        )
        record = self.session.exec(
            select(TradeIntent.id).where(TradeIntent.state.in_(pending_states)).limit(1)
        ).first()
        return record is not None

    def transition_trade_intent(
        self,
        intent: TradeIntent,
        *,
        state: TradeIntentState | str,
        allocation_cycle_id: str | None = None,
        allocated_size: float | None = None,
        allocated_risk_percent: float | None = None,
        estimated_risk_amount: float | None = None,
        submitted_risk_amount: float | None = None,
        fill_derived_risk_amount: float | None = None,
        risk_truth_confidence: str | None = None,
        risk_currency: str | None = None,
        average_fill_price: float | None = None,
        filled_size: float | None = None,
        broker_reference: str | None = None,
        close_broker_reference: str | None = None,
        position_id: int | None = None,
        trade_id: int | None = None,
        decision_reason_code: str | None = None,
        decision_reason: str | None = None,
        close_reason_code: str | None = None,
        close_reason: str | None = None,
        execution_client_request_id: str | None = None,
        details: dict[str, object] | None = None,
        submitted_at: datetime | None = None,
        acknowledged_at: datetime | None = None,
        completed_at: datetime | None = None,
        opened_at: datetime | None = None,
        closed_at: datetime | None = None,
    ) -> TradeIntent:
        intent.state = state.value if isinstance(state, TradeIntentState) else state
        intent.updated_at = utc_now()
        if allocation_cycle_id is not None:
            intent.allocation_cycle_id = allocation_cycle_id
        if allocated_size is not None:
            intent.allocated_size = allocated_size
        if allocated_risk_percent is not None:
            intent.allocated_risk_percent = allocated_risk_percent
        if estimated_risk_amount is not None:
            intent.estimated_risk_amount = estimated_risk_amount
        if submitted_risk_amount is not None:
            intent.submitted_risk_amount = submitted_risk_amount
        if fill_derived_risk_amount is not None:
            intent.fill_derived_risk_amount = fill_derived_risk_amount
        if risk_truth_confidence is not None:
            intent.risk_truth_confidence = risk_truth_confidence
        if risk_currency is not None:
            intent.risk_currency = risk_currency
        if average_fill_price is not None:
            intent.average_fill_price = average_fill_price
        if filled_size is not None:
            intent.filled_size = filled_size
        if broker_reference is not None:
            intent.broker_reference = broker_reference
        if close_broker_reference is not None:
            intent.close_broker_reference = close_broker_reference
        if position_id is not None:
            intent.position_id = position_id
        if trade_id is not None:
            intent.trade_id = trade_id
        if decision_reason_code is not None:
            intent.decision_reason_code = decision_reason_code
        if decision_reason is not None:
            intent.decision_reason = decision_reason
        if close_reason_code is not None:
            intent.close_reason_code = close_reason_code
        if close_reason is not None:
            intent.close_reason = close_reason
        if execution_client_request_id is not None:
            intent.execution_client_request_id = execution_client_request_id
        if details:
            intent.details = {**(intent.details or {}), **details}
        if submitted_at is not None:
            intent.submitted_at = submitted_at
        if acknowledged_at is not None:
            intent.acknowledged_at = acknowledged_at
        if completed_at is not None:
            intent.completed_at = completed_at
        if opened_at is not None:
            intent.opened_at = opened_at
        if closed_at is not None:
            intent.closed_at = closed_at
        try:
            self.session.add(intent)
            self.session.commit()
            self.session.refresh(intent)
            return intent
        except IntegrityError as exc:
            self.session.rollback()
            if intent.state in ACTIVE_INSTRUMENT_OWNERSHIP_STATES:
                conflicting = self.find_active_trade_intent_for_instrument_excluding(
                    intent.instrument,
                    exclude_intent_id=intent.id,
                )
                raise ActiveTradeIntentConflictError(
                    instrument=intent.instrument,
                    conflicting_intent_id=conflicting.id
                    if conflicting is not None
                    else None,
                ) from exc
            raise

    def create_execution(self, execution: Execution) -> Execution:
        if (
            execution.status == ExecutionStatus.SUBMISSION_PENDING.value
            and execution.submitted_at is None
            and execution.acknowledged_at is None
            and execution.completed_at is None
        ):
            execution.last_transition_at = execution.signal_time
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
        self._record_execution_created_domain_event(execution)
        return execution

    def find_execution_by_client_request_id(
        self, client_request_id: str
    ) -> Execution | None:
        statement = select(Execution).where(
            Execution.client_request_id == client_request_id
        )
        return self.session.exec(statement).first()

    def find_latest_execution_for_action(
        self,
        *,
        strategy_name: str,
        instrument: str,
        phase: str,
        action_key: str,
    ) -> Execution | None:
        statement = (
            select(Execution)
            .where(Execution.strategy_name == strategy_name)
            .where(Execution.instrument == instrument)
            .where(Execution.phase == phase)
            .order_by(desc(Execution.created_at))
        )
        executions = self.session.exec(statement).all()
        for execution in executions:
            if (execution.details or {}).get("action_key") == action_key:
                return execution
        return None

    def transition_execution(
        self,
        execution: Execution,
        *,
        status: ExecutionStatus | str,
        trade_intent_id: int | None = None,
        client_request_id: str | None = None,
        broker_reference: str | None = None,
        local_position_id: int | None = None,
        local_trade_id: int | None = None,
        submitted_at: datetime | None = None,
        acknowledged_at: datetime | None = None,
        completed_at: datetime | None = None,
        filled_size: float | None = None,
        average_fill_price: float | None = None,
        intended_risk_amount: float | None = None,
        submitted_risk_amount: float | None = None,
        fill_derived_risk_amount: float | None = None,
        risk_truth_confidence: str | None = None,
        reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        requires_manual_review: bool | None = None,
        details: dict[str, object] | None = None,
    ) -> Execution:
        previous_status = execution.status
        execution.status = (
            status.value if isinstance(status, ExecutionStatus) else status
        )
        execution.last_transition_at = (
            completed_at or acknowledged_at or submitted_at or utc_now()
        )
        execution.updated_at = utc_now()
        if trade_intent_id is not None:
            execution.trade_intent_id = trade_intent_id
        if client_request_id is not None:
            execution.client_request_id = client_request_id
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
        if intended_risk_amount is not None:
            execution.intended_risk_amount = intended_risk_amount
        if submitted_risk_amount is not None:
            execution.submitted_risk_amount = submitted_risk_amount
        if fill_derived_risk_amount is not None:
            execution.fill_derived_risk_amount = fill_derived_risk_amount
        if risk_truth_confidence is not None:
            execution.risk_truth_confidence = risk_truth_confidence
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
        self._record_execution_domain_event(execution, previous_status=previous_status)
        return execution

    def record_broker_position(self, position: Position) -> Position:
        if position.broker_sync_status in {"PENDING", "CONFIRMED"}:
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
                "trade_intent_id",
                "strategy_name",
                "family_name",
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
                "entry_risk_amount",
                "risk_truth_confidence",
                "reason",
                "manual_override",
                "account_type",
                "is_open",
                "broker_sync_status",
                "close_execution_source",
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
        close_execution_source: str | None = None,
        close_reason: str | None = None,
        broker_confirmed_at: datetime | None = None,
    ) -> Position:
        position.is_open = False
        position.close_price = (
            close_price if close_price is not None else position.close_price
        )
        position.close_time = (
            close_time if close_time is not None else position.close_time
        )
        position.pnl = pnl if pnl is not None else position.pnl
        position.current_price = (
            position.close_price
            if position.close_price is not None
            else position.current_price
        )
        position.unrealized_pnl = 0.0
        position.broker_sync_status = broker_sync_status
        if close_execution_source is not None:
            position.close_execution_source = close_execution_source
        position.broker_closed_confirmed_at = (
            broker_confirmed_at or position.close_time or utc_now()
        )
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
        trade_intent_id: int | None,
        strategy_name: str | None,
        instrument: str | None,
        broker_reference: str | None,
        local_position_id: int | None,
        details: dict[str, object] | None = None,
    ) -> ReconciliationEvent:
        event = ReconciliationEvent(
            event_type=event_type,
            trade_intent_id=trade_intent_id,
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

    def _record_execution_domain_event(
        self, execution: Execution, *, previous_status: str | None
    ) -> None:
        if previous_status == execution.status:
            return

        # Decision ownership lives on TradeIntent. Execution events begin once an
        # admitted intent enters broker-attempt orchestration.
        event_metadata = {
            ExecutionStatus.ORDER_SUBMITTED.value: {
                "event_type": "execution.order_submitted",
                "category": "execution",
                "severity": "info",
                "title": "Order submitted",
            },
            ExecutionStatus.ORDER_ACKNOWLEDGED.value: {
                "event_type": "execution.order_acknowledged",
                "category": "execution",
                "severity": "info",
                "title": "Broker acknowledged order",
            },
            ExecutionStatus.FILL_PARTIAL.value: {
                "event_type": "execution.fill_received",
                "category": "execution",
                "severity": "warning",
                "title": "Partial fill received",
            },
            ExecutionStatus.FILL_FULL.value: {
                "event_type": "execution.fill_received",
                "category": "execution",
                "severity": "info",
                "title": "Fill received",
            },
            ExecutionStatus.POSITION_OPENED.value: {
                "event_type": "execution.position_opened",
                "category": "execution",
                "severity": "info",
                "title": "Position opened",
            },
            ExecutionStatus.CLOSE_CONFIRMED.value: {
                "event_type": "execution.position_closed",
                "category": "execution",
                "severity": "info",
                "title": "Position closed",
            },
            ExecutionStatus.FAILED.value: {
                "event_type": "execution.order_rejected",
                "category": "execution",
                "severity": "error",
                "title": "Order failed",
            },
            ExecutionStatus.CANCELLED.value: {
                "event_type": "execution.order_rejected",
                "category": "execution",
                "severity": "warning",
                "title": "Order cancelled",
            },
            ExecutionStatus.NEEDS_MANUAL_REVIEW.value: {
                "event_type": "execution.order_rejected",
                "category": "execution",
                "severity": "error",
                "title": "Execution needs manual review",
            },
        }.get(execution.status)
        if event_metadata is None:
            return

        source = "trade_service.transition_execution"
        event_type = str(event_metadata["event_type"])
        event = domain_event_service.record_event_in_session(
            session=self.session,
            event_type=event_type,
            category=str(event_metadata["category"]),
            severity=str(event_metadata["severity"]),
            error_type=(
                execution.error_code
                or (
                    "ManualReviewRequired"
                    if execution.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
                    else None
                )
                or (
                    "ExecutionFailed"
                    if execution.status == ExecutionStatus.FAILED.value
                    else None
                )
            ),
            source=source,
            title=str(event_metadata["title"]),
            message=execution.error_message or execution.reason,
            correlation_id=execution.client_request_id,
            strategy_name=execution.strategy_name,
            instrument=execution.instrument,
            position_id=execution.local_position_id,
            trade_id=execution.local_trade_id,
            execution_id=execution.id,
            actor_type="service",
            actor_id="trade_service",
            payload_json=self._execution_event_payload(
                execution,
                previous_state=previous_status,
                new_state=execution.status,
            ),
            created_at=execution.last_transition_at,
        )
        if event is None:
            self._mark_execution_audit_persistence_failure(
                execution,
                event_type=event_type,
                source=source,
                previous_status=previous_status,
            )

    def _record_execution_created_domain_event(self, execution: Execution) -> None:
        if execution.status != ExecutionStatus.SUBMISSION_PENDING.value:
            return
        source = "trade_service.create_execution"
        event_type = "execution.submission_pending_created"
        event = domain_event_service.record_event_in_session(
            session=self.session,
            event_type=event_type,
            category="execution",
            severity="info",
            source=source,
            title="Execution attempt created",
            message=execution.reason,
            correlation_id=execution.client_request_id,
            strategy_name=execution.strategy_name,
            instrument=execution.instrument,
            position_id=execution.local_position_id,
            trade_id=execution.local_trade_id,
            execution_id=execution.id,
            actor_type="service",
            actor_id="trade_service",
            payload_json=self._execution_event_payload(
                execution,
                previous_state="NOT_CREATED",
                new_state=execution.status,
            ),
            created_at=execution.last_transition_at,
        )
        if event is None:
            self._mark_execution_audit_persistence_failure(
                execution,
                event_type=event_type,
                source=source,
                previous_status="NOT_CREATED",
            )

    @staticmethod
    def _execution_event_payload(
        execution: Execution,
        *,
        previous_state: str | None,
        new_state: str,
    ) -> dict[str, Any]:
        return {
            "trade_intent_id": execution.trade_intent_id,
            "phase": execution.phase,
            "previous_state": previous_state,
            "new_state": new_state,
            "status": execution.status,
            "reason": execution.reason,
            "error_code": execution.error_code,
            "error_message": execution.error_message,
            "broker_reference": execution.broker_reference,
            "requested_size": execution.requested_size,
            "filled_size": execution.filled_size,
            "requested_price": execution.requested_price,
            "average_fill_price": execution.average_fill_price,
            "intended_risk_amount": execution.intended_risk_amount,
            "submitted_risk_amount": execution.submitted_risk_amount,
            "fill_derived_risk_amount": execution.fill_derived_risk_amount,
            "risk_truth_confidence": execution.risk_truth_confidence,
            "requires_manual_review": execution.requires_manual_review,
            "details": execution.details or {},
        }

    def _mark_execution_audit_persistence_failure(
        self,
        execution: Execution,
        *,
        event_type: str,
        source: str,
        previous_status: str | None,
    ) -> None:
        details: dict[str, Any] = dict(execution.details or {})
        failures = list(details.get("audit_event_failures") or [])
        failures.append(
            {
                "event_type": event_type,
                "source": source,
                "previous_state": previous_status,
                "new_state": execution.status,
                "correlation_id": execution.client_request_id,
            }
        )
        details["domain_event_persistence_failed"] = True
        details["audit_event_failures"] = failures
        execution.details = details
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
