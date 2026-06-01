from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import select

from app.core.broker import OrderDirection
from app.core.runtime import runtime_manager
from app.models.domain_event import DomainEvent
from app.models.trade import (
    Execution,
    ExecutionPhase,
    ExecutionStatus,
    Position,
    TradeIntent,
    TradeIntentState,
)
from app.services.audit_event_recorder import AuditEventPersistenceError
from app.services.domain_event_service import domain_event_service
from app.services.reconciliation_service import ReconciliationService
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position


pytestmark = pytest.mark.usefixtures("audit_critical_domain_events")


def _domain_events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _reconciliation_domain_events(session) -> list[DomainEvent]:
    return [
        event
        for event in _domain_events(session)
        if event.event_type.startswith("reconciliation.")
    ]


def test_reconciliation_corrects_local_position_from_broker_truth(
    session, broker, fixed_now
):
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

    reconciled_positions = ReconciliationService(
        trade_service
    ).reconcile_open_positions()

    assert len(reconciled_positions) == 1
    reconciled = reconciled_positions[0]
    assert reconciled.size == 0.5
    assert reconciled.open_price == 101.5
    assert reconciled.broker_sync_status == "CONFIRMED"
    assert (
        runtime_manager.get_engine(
            "smoke_test_hold", "CS.D.EURUSD.MINI.IP"
        ).current_position.open_price
        == 101.5
    )
    assert (
        trade_service.list_reconciliation_events(limit=10)[0].event_type
        == "POSITION_SYNCED_FROM_BROKER"
    )


def test_audit_test_002_reconciliation_correction_persists_domain_event(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            state=TradeIntentState.POSITION_OPENED.value,
            signal_time=fixed_now - timedelta(minutes=10),
            proposed_size=0.2,
            allocated_size=0.2,
            allocation_cycle_id="alloc-reconcile-correct-1",
            broker_reference="broker-correct-audit",
            execution_client_request_id="reconcile-correct-request-1",
            opened_at=fixed_now - timedelta(minutes=10),
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
            client_request_id="reconcile-correct-request-1",
            broker_reference="broker-correct-audit",
            signal_time=fixed_now - timedelta(minutes=10),
            requested_size=0.2,
            requested_price=100.0,
            requires_manual_review=True,
        )
    )
    local_position = trade_service.record_broker_position(
        Position(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            broker_reference="broker-correct-audit",
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
        )
    )
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-correct-audit",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.5,
            open_price=101.5,
            opened_at=fixed_now - timedelta(minutes=10),
        )
    ]

    ReconciliationService(trade_service).reconcile_open_positions()

    events = _reconciliation_domain_events(session)
    corrected_events = [
        event
        for event in events
        if event.event_type == "reconciliation.position_corrected"
    ]
    assert len(corrected_events) == 1
    event = corrected_events[0]
    assert event.category == "reconciliation"
    assert event.severity == "info"
    assert event.source == "reconciliation_service.reconcile_open_positions"
    assert event.actor_type == "service"
    assert event.actor_id == "reconciliation_service"
    assert event.strategy_name == "smoke_test_hold"
    assert event.instrument == "CS.D.EURUSD.MINI.IP"
    assert event.position_id == local_position.id
    assert event.correlation_id == "reconcile-correct-request-1"
    assert event.execution_id == execution.id
    assert event.payload_json["broker_reference"].startswith("[REDACTED_BROKER_REF:")
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["execution_id"] == execution.id
    assert event.payload_json["execution_client_request_id"].startswith(
        "[REDACTED_REQUEST_ID:"
    )
    assert event.payload_json["allocation_cycle_id"] == "alloc-reconcile-correct-1"
    assert event.payload_json["matched_local_position"] is True
    assert event.payload_json["previous_state"] == "LOCAL_POSITION_STALE"
    assert event.payload_json["new_state"] == "LOCAL_POSITION_BROKER_CONFIRMED"


def test_audit_broker_002_reconciliation_uses_strict_fake_position_outcome(
    session, broker, fixed_now
):
    broker.require_explicit_positions = True
    trade_service = TradeService(session)
    engine = runtime_manager.start(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        current_position=Position(
            strategy_name="smoke_test_hold",
            broker_reference="broker-strict-pos-1",
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
    RuntimeStateService(session).sync_engine_state(
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        status="RUNNING",
        recovery_state="RUNNING",
        current_position=local_position,
    )
    broker.position_outcomes.append(
        [
            make_broker_position(
                broker_reference="broker-strict-pos-1",
                instrument="CS.D.EURUSD.MINI.IP",
                direction=OrderDirection.BUY,
                size=0.5,
                open_price=101.5,
                opened_at=fixed_now - timedelta(minutes=10),
            )
        ]
    )

    reconciled_positions = ReconciliationService(
        trade_service
    ).reconcile_open_positions()

    assert broker.position_outcomes == []
    assert len(reconciled_positions) == 1
    assert reconciled_positions[0].size == 0.5
    assert reconciled_positions[0].open_price == 101.5
    assert reconciled_positions[0].broker_sync_status == "CONFIRMED"
    assert (
        trade_service.list_reconciliation_events(limit=10)[0].event_type
        == "POSITION_SYNCED_FROM_BROKER"
    )


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

    reconciled_positions = ReconciliationService(
        trade_service
    ).reconcile_open_positions()
    runtime = RuntimeStateService(session).get_runtime(
        "smoke_test_hold", "CS.D.EURUSD.MINI.IP"
    )

    assert len(reconciled_positions) == 1
    adopted = reconciled_positions[0]
    assert adopted.strategy_name == "broker_sync"
    assert adopted.broker_reference == "broker-adopt-1"
    assert adopted.open_price == 102.25
    assert adopted.reason == "Reconciled from broker"
    assert adopted.broker_sync_status == "CONFIRMED"
    assert runtime.current_position_broker_reference is None
    assert (
        trade_service.list_reconciliation_events(limit=10)[0].event_type
        == "POSITION_ADOPTED_FROM_BROKER"
    )


def test_audit_life_001_reconciliation_links_ambiguous_entry_by_broker_reference(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            state=TradeIntentState.ACKNOWLEDGED.value,
            signal_time=fixed_now - timedelta(minutes=2),
            proposed_size=0.2,
            allocated_size=0.2,
            broker_reference="entry-ambiguous-1",
            execution_client_request_id="ent-ambiguous-1",
            decision_reason_code="broker_confirmation_ambiguous",
            decision_reason="Broker confirmation was ambiguous.",
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
            client_request_id="ent-ambiguous-1",
            broker_reference="entry-ambiguous-1",
            signal_time=fixed_now - timedelta(minutes=2),
            requested_size=0.2,
            requested_price=100.0,
            requires_manual_review=True,
            details={
                "broker_result": {
                    "status": "AMBIGUOUS",
                    "client_request_id": "ent-ambiguous-1",
                    "broker_reference": "entry-ambiguous-1",
                }
            },
        )
    )
    broker.remote_positions = [
        make_broker_position(
            broker_reference="entry-ambiguous-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.2,
            open_price=100.25,
            opened_at=fixed_now - timedelta(minutes=1),
        )
    ]

    reconciled_positions = ReconciliationService(
        trade_service
    ).reconcile_open_positions()

    refreshed_intent = trade_service.get_trade_intent(intent.id)
    refreshed_execution = trade_service.find_execution_by_client_request_id(
        "ent-ambiguous-1"
    )
    events = trade_service.list_reconciliation_events(limit=10)
    intents = trade_service.list_trade_intents(limit=10)

    assert len(reconciled_positions) == 1
    assert len(intents) == 1
    assert refreshed_intent is not None
    assert refreshed_intent.id == intent.id
    assert refreshed_intent.state == TradeIntentState.POSITION_OPENED.value
    assert refreshed_intent.position_id == reconciled_positions[0].id
    assert refreshed_intent.execution_client_request_id == "ent-ambiguous-1"
    assert refreshed_intent.details["reconciliation_linked_ambiguous_entry"] is True
    assert refreshed_execution is not None
    assert refreshed_execution.id == execution.id
    assert refreshed_execution.status == ExecutionStatus.POSITION_OPENED.value
    assert refreshed_execution.requires_manual_review is False
    assert refreshed_execution.local_position_id == reconciled_positions[0].id
    assert refreshed_execution.details["reconciliation_linked_open_position"] is True
    assert events[0].event_type == "POSITION_SYNCED_FROM_BROKER"
    assert events[0].trade_intent_id == intent.id
    assert (
        events[0]
        .details["execution_client_request_id"]
        .startswith("[REDACTED_REQUEST_ID:")
    )


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

    reconciled_positions = ReconciliationService(
        trade_service
    ).reconcile_open_positions()
    runtime_state = RuntimeStateService(session).get_runtime(
        "smoke_test_hold", "CS.D.EURUSD.MINI.IP"
    )
    closed_position = session.get(Position, persisted.id)

    assert reconciled_positions == []
    assert closed_position.is_open is False
    assert closed_position.broker_sync_status == "MISSING_AT_BROKER"
    assert (
        runtime_manager.get_engine(
            "smoke_test_hold", "CS.D.EURUSD.MINI.IP"
        ).current_position
        is None
    )
    assert runtime_state.current_position_broker_reference is None
    assert (
        trade_service.list_reconciliation_events(limit=10)[0].event_type
        == "LOCAL_POSITION_CLOSED_AFTER_BROKER_MISS"
    )


def test_reconciliation_creates_explicit_adopted_trade_intent(
    session, broker, fixed_now
):
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


def test_audit_test_002_reconciliation_adoption_persists_domain_event(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-adopt-audit",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=103.0,
            opened_at=fixed_now - timedelta(minutes=2),
        )
    ]

    ReconciliationService(trade_service).reconcile_open_positions()

    positions = trade_service.list_positions()
    intents = trade_service.list_trade_intents(limit=10)
    events = _reconciliation_domain_events(session)
    assert len(positions) == 1
    assert len(intents) == 1
    assert len(events) == 1
    assert events[0].event_type == "reconciliation.unmatched_remote_position"
    assert events[0].category == "reconciliation"
    assert events[0].severity == "warning"
    assert events[0].source == "reconciliation_service.reconcile_open_positions"
    assert events[0].strategy_name == "broker_sync"
    assert events[0].instrument == "CS.D.EURUSD.MINI.IP"
    assert events[0].position_id == positions[0].id
    assert (
        events[0].payload_json["broker_reference"].startswith("[REDACTED_BROKER_REF:")
    )
    assert events[0].payload_json["trade_intent_id"] == intents[0].id
    assert events[0].payload_json["previous_state"] == "BROKER_ONLY"
    assert events[0].payload_json["new_state"] == "LOCAL_POSITION_ADOPTED"


def test_audit_obs_001_reconciliation_adoption_audit_failure_raises(
    session, broker, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    broker.remote_positions = [
        make_broker_position(
            broker_reference="broker-adopt-audit-fail",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=103.0,
            opened_at=fixed_now - timedelta(minutes=2),
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
        match="reconciliation.unmatched_remote_position",
    ):
        ReconciliationService(trade_service).reconcile_open_positions()

    assert _reconciliation_domain_events(session) == []
    assert len(trade_service.list_positions()) == 1
    assert (
        trade_service.list_reconciliation_events(limit=10)[0].event_type
        == "POSITION_ADOPTED_FROM_BROKER"
    )


def test_reconciliation_forced_close_creates_trade_and_intent_record(
    session, fixed_now
):
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


def test_audit_test_002_reconciliation_forced_close_persists_domain_events(
    session, fixed_now
):
    trade_service = TradeService(session)
    current_position = Position(
        strategy_name="smoke_test_hold",
        broker_reference="missing-audit",
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
            allocation_cycle_id="alloc-reconcile-force-1",
            broker_reference="missing-audit",
            execution_client_request_id="reconcile-force-request-1",
            decision_reason_code="approved",
            decision_reason="Opened earlier.",
            opened_at=current_position.open_time,
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.POSITION_OPENED.value,
            client_request_id="reconcile-force-request-1",
            broker_reference="missing-audit",
            signal_time=current_position.open_time,
            requested_size=0.2,
            filled_size=0.2,
            requested_price=100.0,
            average_fill_price=100.0,
        )
    )
    current_position.trade_intent_id = intent.id
    persisted = trade_service.record_broker_position(current_position)

    ReconciliationService(trade_service).reconcile_open_positions()

    refreshed_intent = trade_service.get_trade_intent(intent.id)
    trades = trade_service.list_trades()
    events = _reconciliation_domain_events(session)
    assert refreshed_intent is not None
    assert len(trades) == 1
    assert [event.event_type for event in events] == [
        "reconciliation.unmatched_local_position",
        "reconciliation.position_corrected",
    ]
    for event in events:
        assert event.category == "reconciliation"
        assert event.source == "reconciliation_service.reconcile_open_positions"
        assert event.strategy_name == "smoke_test_hold"
        assert event.instrument == "CS.D.EURUSD.MINI.IP"
        assert event.position_id == persisted.id
        assert event.trade_id == trades[0].id
        assert event.execution_id == execution.id
        assert event.correlation_id == "reconcile-force-request-1"
        assert event.payload_json["broker_reference"].startswith(
            "[REDACTED_BROKER_REF:"
        )
        assert event.payload_json["trade_intent_id"] == intent.id
        assert event.payload_json["execution_id"] == execution.id
        assert event.payload_json["execution_client_request_id"].startswith(
            "[REDACTED_REQUEST_ID:"
        )
        assert event.payload_json["forced_trade_id"] == trades[0].id
        assert event.payload_json["trade_id"] == trades[0].id
        assert event.payload_json["allocation_cycle_id"] == "alloc-reconcile-force-1"
        assert event.payload_json["previous_state"] == "LOCAL_POSITION_OPEN"
        assert event.payload_json["new_state"] == "LOCAL_POSITION_FORCED_CLOSED"
    assert events[0].severity == "warning"
    assert events[1].severity == "info"


def test_audit_obs_001_reconciliation_forced_close_audit_failure_raises(
    session, fixed_now, monkeypatch
):
    trade_service = TradeService(session)
    current_position = Position(
        strategy_name="smoke_test_hold",
        broker_reference="missing-audit-fail",
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
            broker_reference="missing-audit-fail",
            execution_client_request_id="reconcile-force-fail-request-1",
            opened_at=current_position.open_time,
        )
    )
    trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.POSITION_OPENED.value,
            client_request_id="reconcile-force-fail-request-1",
            broker_reference="missing-audit-fail",
            signal_time=current_position.open_time,
            requested_size=0.2,
            filled_size=0.2,
            requested_price=100.0,
            average_fill_price=100.0,
        )
    )
    current_position.trade_intent_id = intent.id
    trade_service.record_broker_position(current_position)
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with pytest.raises(
        AuditEventPersistenceError,
        match="reconciliation.unmatched_local_position",
    ):
        ReconciliationService(trade_service).reconcile_open_positions()

    events = _reconciliation_domain_events(session)
    trades = trade_service.list_trades()
    refreshed_intent = trade_service.get_trade_intent(intent.id)
    assert events == []
    assert len(trades) == 1
    assert refreshed_intent is not None
    assert refreshed_intent.state == TradeIntentState.FORCED_RECONCILIATION_CLOSE.value
