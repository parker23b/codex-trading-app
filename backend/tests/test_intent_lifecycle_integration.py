from __future__ import annotations

from datetime import timedelta

from sqlmodel import select

from app.core.broker import OrderDirection
from app.models.trade import Execution, ExecutionStatus, Position, ReconciliationEvent, Trade, TradeIntent, TradeIntentState
from app.services.reconciliation_service import ReconciliationService
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService
from tests.fakes import make_order_result


INSTRUMENT = "CS.D.EURUSD.MINI.IP"
STRATEGY = "smoke_test_hold"


def test_intent_first_happy_path_persists_coherent_trade_lifecycle(session, broker, fixed_now, monkeypatch):
    service = StrategyService(session)
    trade_service = TradeService(session)
    service.start_strategy(STRATEGY, INSTRUMENT)

    intent_state_history: list[str] = []
    execution_creation_statuses: list[str] = []

    original_create_trade_intent = TradeService.create_trade_intent
    original_transition_trade_intent = TradeService.transition_trade_intent
    original_create_execution = TradeService.create_execution

    def recording_create_trade_intent(self, intent: TradeIntent) -> TradeIntent:
        created = original_create_trade_intent(self, intent)
        intent_state_history.append(created.state)
        return created

    def recording_transition_trade_intent(self, intent: TradeIntent, **kwargs) -> TradeIntent:
        transitioned = original_transition_trade_intent(self, intent, **kwargs)
        intent_state_history.append(transitioned.state)
        return transitioned

    def recording_create_execution(self, execution: Execution) -> Execution:
        execution_creation_statuses.append(execution.status)
        return original_create_execution(self, execution)

    monkeypatch.setattr(TradeService, "create_trade_intent", recording_create_trade_intent)
    monkeypatch.setattr(TradeService, "transition_trade_intent", recording_transition_trade_intent)
    monkeypatch.setattr(TradeService, "create_execution", recording_create_execution)

    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="integration-entry-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            client_request_id="ent-integration-1",
            price=101.0,
            average_fill_price=101.25,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        make_order_result(
            broker_reference="integration-close-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            client_request_id="cls-integration-1",
            price=103.0,
            average_fill_price=102.75,
            executed_at=fixed_now + timedelta(seconds=40),
        )
    )

    service.process_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )
    service.process_price_update(
        INSTRUMENT,
        103.0,
        bid=102.8,
        ask=103.2,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    intents = session.exec(select(TradeIntent)).all()
    executions = session.exec(select(Execution).order_by(Execution.id)).all()
    positions = session.exec(select(Position).order_by(Position.id)).all()
    trades = session.exec(select(Trade).order_by(Trade.id)).all()

    assert len(intents) == 1
    assert len(executions) == 2
    assert len(positions) == 1
    assert len(trades) == 1

    intent = intents[0]
    entry_execution, close_execution = executions
    position = positions[0]
    trade = trades[0]

    assert TradeIntentState.PROPOSED.value in intent_state_history
    assert TradeIntentState.APPROVED.value in intent_state_history
    assert TradeIntentState.POSITION_OPENED.value in intent_state_history
    assert TradeIntentState.CLOSE_REQUESTED.value in intent_state_history
    assert intent.state == TradeIntentState.CLOSED.value

    assert execution_creation_statuses == [
        ExecutionStatus.SUBMISSION_PENDING.value,
        ExecutionStatus.SUBMISSION_PENDING.value,
    ]
    assert entry_execution.phase == "ENTRY"
    assert entry_execution.status == ExecutionStatus.POSITION_OPENED.value
    assert close_execution.phase == "CLOSE"
    assert close_execution.status == ExecutionStatus.CLOSE_CONFIRMED.value

    assert position.trade_intent_id == intent.id
    assert position.is_open is False
    assert position.broker_reference == "integration-entry-1"
    assert position.close_price == 102.75
    assert position.close_time == trade.close_time

    assert trade.trade_intent_id == intent.id
    assert trade.broker_reference == "integration-entry-1"
    assert trade.close_broker_reference == "integration-close-1"
    assert trade.open_price == 101.25
    assert trade.close_price == 102.75

    assert intent.position_id == position.id
    assert intent.trade_id == trade.id
    assert intent.broker_reference == "integration-entry-1"
    assert intent.close_broker_reference == "integration-close-1"
    assert intent.execution_client_request_id == close_execution.client_request_id
    assert intent.opened_at == position.open_time
    assert intent.closed_at == trade.close_time


def test_forced_reconciliation_close_creates_explicit_out_of_band_lifecycle_records(session, fixed_now):
    trade_service = TradeService(session)
    open_time = fixed_now - timedelta(minutes=5)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            direction="BUY",
            state=TradeIntentState.POSITION_OPENED.value,
            signal_time=open_time,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            broker_reference="reconcile-missing-1",
            decision_reason_code="approved",
            decision_reason="Opened earlier.",
            opened_at=open_time,
        )
    )
    position = trade_service.record_broker_position(
        Position(
            trade_intent_id=intent.id,
            strategy_name=STRATEGY,
            broker_reference="reconcile-missing-1",
            instrument=INSTRUMENT,
            direction="BUY",
            size=0.2,
            open_price=100.0,
            open_time=open_time,
            current_price=99.5,
            unrealized_pnl=-0.1,
            risk_percent=0.1,
            account_type="DEMO",
            is_open=True,
            broker_sync_status="CONFIRMED",
        )
    )

    ReconciliationService(trade_service).reconcile_open_positions()

    refreshed_intent = session.get(TradeIntent, intent.id)
    refreshed_position = session.get(Position, position.id)
    trades = session.exec(select(Trade)).all()
    reconciliation_events = session.exec(
        select(ReconciliationEvent).order_by(ReconciliationEvent.id)
    ).all()
    executions = session.exec(select(Execution)).all()

    assert refreshed_intent is not None
    assert refreshed_position is not None
    assert len(trades) == 1
    assert len(executions) == 0
    assert refreshed_position.is_open is False
    assert refreshed_position.broker_sync_status == "MISSING_AT_BROKER"

    forced_trade = trades[0]
    assert forced_trade.trade_intent_id == intent.id
    assert forced_trade.reason == "Forced reconciliation close"
    assert forced_trade.outcome == "reconciled"

    assert refreshed_intent.state == TradeIntentState.FORCED_RECONCILIATION_CLOSE.value
    assert refreshed_intent.position_id == position.id
    assert refreshed_intent.trade_id == forced_trade.id
    assert refreshed_intent.close_reason_code == "FORCED_RECONCILIATION_CLOSE"
    assert refreshed_intent.close_reason is not None
    assert refreshed_intent.closed_at == forced_trade.close_time

    assert [event.event_type for event in reconciliation_events] == [
        "LOCAL_POSITION_CLOSED_AFTER_BROKER_MISS"
    ]
    assert reconciliation_events[0].trade_intent_id == intent.id
    assert reconciliation_events[0].local_position_id == position.id
