from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import select

from app.core.broker import OrderDirection
from app.models.domain_event import DomainEvent
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Position, TradeIntentState
from app.services.audit_event_recorder import AuditEventPersistenceError
from app.services.domain_event_service import domain_event_service
from app.services.runtime_recovery_service import RuntimeRecoveryService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position
from app.core.runtime import runtime_manager


def _domain_events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _non_decision_domain_events(session) -> list[DomainEvent]:
    return [
        event
        for event in _domain_events(session)
        if not event.event_type.startswith("trade_intent.")
    ]


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


def test_audit_test_002_runtime_recovery_resumed_runtime_persists_domain_event(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-audit",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RECOVERY_REQUIRED",
            current_position_broker_reference="recover-audit-pos-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="recover-audit-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    outcomes = RuntimeRecoveryService(session).recover()

    positions = TradeService(session).list_positions()
    events = _non_decision_domain_events(session)
    assert any(outcome["outcome"] == "resumed" for outcome in outcomes)
    assert len(positions) == 1
    assert len(events) == 1
    assert events[0].event_type == "strategy.runtime_started"
    assert events[0].category == "strategy"
    assert events[0].source == "runtime_recovery_service.recover"
    assert events[0].runtime_id == "runtime-recover-audit"
    assert events[0].strategy_name == "smoke_test_hold"
    assert events[0].instrument == "CS.D.EURUSD.MINI.IP"
    assert events[0].position_id == positions[0].id
    assert events[0].payload_json["previous_state"] == "RECOVERY_REQUIRED"
    assert events[0].payload_json["new_state"] == "RUNNING"
    assert events[0].payload_json["recovered"] is True


def test_audit_test_002_runtime_recovery_broker_mismatch_persists_domain_event(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-mismatch-audit",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            current_position_broker_reference="missing-broker-audit",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = []

    outcomes = RuntimeRecoveryService(session).recover()

    events = _non_decision_domain_events(session)
    assert any(outcome["outcome"] == "recovery_required" for outcome in outcomes)
    assert len(events) == 1
    assert events[0].event_type == "reconciliation.mismatch_detected"
    assert events[0].category == "reconciliation"
    assert events[0].severity == "warning"
    assert events[0].source == "runtime_recovery_service.recover"
    assert events[0].runtime_id == "runtime-recover-mismatch-audit"
    assert events[0].strategy_name == "smoke_test_hold"
    assert events[0].instrument == "CS.D.EURUSD.MINI.IP"
    assert events[0].payload_json["broker_reference"] == "missing-broker-audit"


def test_audit_test_002_runtime_recovery_broker_auth_failure_persists_domain_event(
    session, broker, fixed_now
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-auth-audit",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            current_position_broker_reference="missing-auth-audit",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()

    def raise_auth_error():
        raise RuntimeError("auth denied by broker")

    broker.get_positions = raise_auth_error

    outcomes = RuntimeRecoveryService(session).recover()

    events = _non_decision_domain_events(session)
    assert any(outcome["outcome"] == "recovery_required" for outcome in outcomes)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "health.broker_auth_failed"
    assert event.category == "health"
    assert event.severity == "error"
    assert event.error_type == "BrokerAuthenticationFailed"
    assert event.source == "runtime_recovery_service.recover"
    assert event.actor_type == "service"
    assert event.actor_id == "runtime_recovery_service"
    assert event.runtime_id == "runtime-recover-auth-audit"
    assert event.strategy_name == "smoke_test_hold"
    assert event.instrument == "CS.D.EURUSD.MINI.IP"
    assert event.payload_json["reason"] == "auth denied by broker"
    assert event.payload_json["previous_state"] == "RUNNING"
    assert event.payload_json["new_state"] == "RECOVERY_REQUIRED"


def test_audit_obs_001_runtime_recovery_resumed_runtime_audit_failure_raises(
    session, broker, fixed_now, monkeypatch
):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-audit-fail",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RECOVERY_REQUIRED",
            current_position_broker_reference="recover-audit-fail-pos-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="recover-audit-fail-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with pytest.raises(
        AuditEventPersistenceError,
        match="strategy.runtime_started",
    ):
        RuntimeRecoveryService(session).recover()

    assert _non_decision_domain_events(session) == []
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == "runtime-recover-audit-fail"
        )
    ).one()
    assert runtime.recovery_state == "RUNNING"
    assert runtime.status == "RUNNING"


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
