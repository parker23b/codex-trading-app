from __future__ import annotations

from datetime import timedelta

from sqlmodel import select

from app.core.broker import OrderDirection
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Position, TradeIntentState
from app.services.runtime_recovery_service import RuntimeRecoveryService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position
from app.core.runtime import runtime_manager


def test_runtime_recovery_creates_trade_intent_before_recreating_position(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-1",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            current_position_broker_reference="recover-pos-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="recover-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    RuntimeRecoveryService(session).recover()

    trade_service = TradeService(session)
    positions = trade_service.list_positions()
    intents = trade_service.list_trade_intents(limit=10)

    assert len(positions) == 1
    assert len(intents) == 1
    assert positions[0].trade_intent_id == intents[0].id
    assert intents[0].state == TradeIntentState.RECOVERED_POSITION_ATTACHED.value
    assert intents[0].position_id == positions[0].id


def test_runtime_recovery_restores_exits_only_mode_to_engine(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-exits-only",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            runtime_mode="EXITS_ONLY",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()

    RuntimeRecoveryService(session).recover()

    engine = runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP")
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == "runtime-recover-exits-only"
        )
    ).one()
    assert engine is not None
    assert engine.runtime_mode == "EXITS_ONLY"
    assert runtime.runtime_mode == "EXITS_ONLY"


def test_runtime_recovery_does_not_start_runtime_marked_stopped_mode(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-stopped-mode",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            runtime_mode="STOPPED",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()

    outcomes = RuntimeRecoveryService(session).recover()

    engine = runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP")
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == "runtime-recover-stopped-mode"
        )
    ).one()
    assert engine is None
    assert runtime.status == "STOPPED"
    assert runtime.runtime_mode == "STOPPED"
    assert any(outcome["outcome"] == "stopped" for outcome in outcomes)


def test_audit_life_003_stopped_runtime_recovers_remote_open_position(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-stopped-remote-risk",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            runtime_mode="STOPPED",
            current_position_broker_reference="stopped-remote-risk-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="stopped-remote-risk-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    outcomes = RuntimeRecoveryService(session).recover()

    engine = runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP")
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == "runtime-recover-stopped-remote-risk"
        )
    ).one()
    trade_service = TradeService(session)
    positions = trade_service.list_positions()
    intents = trade_service.list_trade_intents(limit=10)

    assert engine is None
    assert runtime.status == "STOPPED"
    assert runtime.runtime_mode == "STOPPED"
    assert runtime.current_position_broker_reference == "stopped-remote-risk-1"
    assert any(outcome["outcome"] == "stopped" for outcome in outcomes)
    assert len(positions) == 1
    assert positions[0].broker_reference == "stopped-remote-risk-1"
    assert positions[0].broker_sync_status == "CONFIRMED"
    assert len(intents) == 1
    assert intents[0].state == TradeIntentState.RECOVERED_POSITION_ATTACHED.value
    assert intents[0].position_id == positions[0].id
    assert positions[0].trade_intent_id == intents[0].id


def test_audit_life_003_stopped_runtime_attaches_intent_to_confirmed_local_position(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-stopped-local-risk",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            runtime_mode="STOPPED",
            current_position_broker_reference="stopped-local-risk-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.add(
        Position(
            strategy_name="smoke_test_hold",
            family_name="smoke_test_hold",
            broker_reference="stopped-local-risk-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY.value,
            size=0.4,
            open_price=101.25,
            open_time=fixed_now - timedelta(minutes=3),
            current_price=101.0,
            unrealized_pnl=0.0,
            account_type=broker.account_type.value,
            is_open=True,
            broker_sync_status="CONFIRMED",
            broker_open_confirmed_at=fixed_now - timedelta(minutes=3),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="stopped-local-risk-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    outcomes = RuntimeRecoveryService(session).recover()

    engine = runtime_manager.get_engine("smoke_test_hold", "CS.D.EURUSD.MINI.IP")
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == "runtime-recover-stopped-local-risk"
        )
    ).one()
    trade_service = TradeService(session)
    positions = trade_service.list_positions()
    intents = trade_service.list_trade_intents(limit=10)

    assert engine is None
    assert runtime.status == "STOPPED"
    assert runtime.runtime_mode == "STOPPED"
    assert runtime.current_position_broker_reference == "stopped-local-risk-1"
    assert any(outcome["outcome"] == "stopped" for outcome in outcomes)
    assert len(positions) == 1
    assert positions[0].broker_reference == "stopped-local-risk-1"
    assert len(intents) == 1
    assert intents[0].state == TradeIntentState.RECOVERED_POSITION_ATTACHED.value
    assert intents[0].position_id == positions[0].id
    assert positions[0].trade_intent_id == intents[0].id
