from __future__ import annotations

from datetime import timedelta

from app.core.broker import OrderDirection
from app.core.runtime import runtime_manager
from app.models.trade import Position, TradeIntent, TradeIntentState
from app.services.reconciliation_service import ReconciliationService
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position


def test_reconciliation_corrects_local_position_from_broker_truth(session, broker, fixed_now):
    trade_service = TradeService(session)
    engine = runtime_manager.start(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        current_position=Position(
            strategy_name="smoke_test_hold",
            broker_reference="broker-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            size=0.2,
            open_price=100.0,
            open_time=fixed_now - timedelta(minutes=10),
            current_price=100.0,
            unrealized_pnl=0.0,
            account_type="DEMO",
            is_open=True,
            broker_sync_status="PENDING",
        ),
    )
    local_position = trade_service.record_broker_position(engine.current_position)
    local_position.size = 0.2
    local_position.open_price = 100.0
    local_position.broker_sync_status = "PENDING"
    session.add(local_position)
    session.commit()
    RuntimeStateService(session).sync_engine_state(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        status="RUNNING",
        recovery_state="RUNNING",
        current_position=local_position,
    )
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.5,
            open_price=101.5,
            opened_at=fixed_now - timedelta(minutes=10),
        )
    ]

    reconciled_positions = ReconciliationService(trade_service).reconcile_open_positions()

    assert len(reconciled_positions) == 1
    reconciled = reconciled_positions[0]
    assert reconciled.size == 0.5
    assert reconciled.open_price == 101.5
    assert reconciled.broker_sync_status == "CONFIRMED"
    assert runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP").current_position.open_price == 101.5
    assert trade_service.list_reconciliation_events(limit=10)[0].event_type == "POSITION_SYNCED_FROM_BROKER"


def test_reconciliation_adopts_unmatched_broker_position(session, broker, fixed_now):
    trade_service = TradeService(session)
    runtime_manager.start(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
    )
    RuntimeStateService(session).sync_engine_state(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        status="RUNNING",
        recovery_state="RUNNING",
        current_position=None,
    )
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-adopt-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.3,
            open_price=102.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    reconciled_positions = ReconciliationService(trade_service).reconcile_open_positions()
    runtime = RuntimeStateService(session).get_runtime("smoke_test_hold", "CS.D.EURUSD.MINI.IP")

    assert len(reconciled_positions) == 1
    adopted = reconciled_positions[0]
    assert adopted.strategy_name == "broker_sync"
    assert adopted.broker_reference == "broker-adopt-1"
    assert adopted.open_price == 102.25
    assert adopted.reason == "Reconciled from broker"
    assert adopted.broker_sync_status == "CONFIRMED"
    assert runtime.current_position_broker_reference is None
    assert trade_service.list_reconciliation_events(limit=10)[0].event_type == "POSITION_ADOPTED_FROM_BROKER"


def test_reconciliation_closes_local_position_missing_at_broker(session, fixed_now):
    trade_service = TradeService(session)
    current_position = Position(
        strategy_name="smoke_test_hold",
        broker_reference="missing-1",
        instrument="CS.D.EURUSD.MINI.IP",
        direction="BUY",
        size=0.2,
        open_price=100.0,
        open_time=fixed_now - timedelta(minutes=5),
        current_price=99.5,
        unrealized_pnl=-0.1,
        account_type="DEMO",
        is_open=True,
        broker_sync_status="CONFIRMED",
    )
    runtime_manager.start(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        current_position=current_position,
    )
    persisted = trade_service.record_broker_position(current_position)
    RuntimeStateService(session).sync_engine_state(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        status="RUNNING",
        recovery_state="RUNNING",
        current_position=persisted,
    )

    reconciled_positions = ReconciliationService(trade_service).reconcile_open_positions()
    runtime_state = RuntimeStateService(session).get_runtime("smoke_test_hold", "CS.D.EURUSD.MINI.IP")
    closed_position = session.get(Position, persisted.id)

    assert reconciled_positions == []
    assert closed_position.is_open is False
    assert closed_position.broker_sync_status == "MISSING_AT_BROKER"
    assert runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP").current_position is None
    assert runtime_state.current_position_broker_reference is None
    assert trade_service.list_reconciliation_events(limit=10)[0].event_type == "LOCAL_POSITION_CLOSED_AFTER_BROKER_MISS"


def test_reconciliation_creates_explicit_adopted_trade_intent(session, broker, fixed_now):
    trade_service = TradeService(session)
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-adopt-2",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=103.0,
            opened_at=fixed_now - timedelta(minutes=2),
        )
    ]

    ReconciliationService(trade_service).reconcile_open_positions()

    intents = trade_service.list_trade_intents(limit=10)
    assert len(intents) == 1
    assert intents[0].state == TradeIntentState.EXTERNAL_POSITION_ADOPTED.value
    assert intents[0].decision_reason_code == "UNPLANNED_POSITION_DETECTED"


def test_reconciliation_forced_close_creates_trade_and_intent_record(session, fixed_now):
    trade_service = TradeService(session)
    current_position = Position(
        strategy_name="smoke_test_hold",
        broker_reference="missing-2",
        instrument="CS.D.EURUSD.MINI.IP",
        direction="BUY",
        size=0.2,
        open_price=100.0,
        open_time=fixed_now - timedelta(minutes=5),
        current_price=99.5,
        unrealized_pnl=-0.1,
        account_type="DEMO",
        is_open=True,
        broker_sync_status="CONFIRMED",
    )
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            state=TradeIntentState.POSITION_OPENED.value,
            signal_time=current_position.open_time,
            proposed_size=0.2,
            allocated_size=0.2,
            proposed_risk_percent=0.1,
            allocated_risk_percent=0.1,
            broker_reference="missing-2",
            decision_reason_code="approved",
            decision_reason="Opened earlier.",
            opened_at=current_position.open_time,
        )
    )
    current_position.trade_intent_id = intent.id
    trade_service.record_broker_position(current_position)

    ReconciliationService(trade_service).reconcile_open_positions()

    refreshed_intent = trade_service.get_trade_intent(intent.id)
    trades = trade_service.list_trades()
    assert len(trades) == 1
    assert trades[0].trade_intent_id == intent.id
    assert refreshed_intent is not None
    assert refreshed_intent.state == TradeIntentState.FORCED_RECONCILIATION_CLOSE.value
    assert refreshed_intent.trade_id == trades[0].id
