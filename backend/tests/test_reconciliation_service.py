from __future__ import annotations

from datetime import timedelta

from app.core.broker import OrderDirection
from app.core.runtime import runtime_manager
from app.models.trade import Position
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
