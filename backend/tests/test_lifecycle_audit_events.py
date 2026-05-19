from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select

from app.models.domain_event import DomainEvent
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus, TradeIntent
from app.services.domain_event_service import domain_event_service
from app.services.trade_service import TradeService


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _execution_events(session) -> list[DomainEvent]:
    return [
        event for event in _events(session) if event.event_type.startswith("execution.")
    ]


def _seed_execution(session) -> tuple[TradeIntent, Execution]:
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            signal_time=datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
            proposed_size=1.0,
            proposed_risk_percent=0.5,
            decision_reason_code="APPROVED",
            decision_reason="Approved by allocator.",
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="entry-audit-client-1",
            signal_time=intent.signal_time,
            requested_size=1.0,
            requested_price=1.1,
            intended_risk_amount=50.0,
            details={"action_key": "entry:mean_reversion:CS.D.EURUSD.CFD.IP"},
        )
    )
    return intent, execution


def test_audit_test_002_execution_creation_persists_submission_pending_domain_event(
    session,
):
    intent, execution = _seed_execution(session)

    events = _execution_events(session)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "execution.submission_pending_created"
    assert event.category == "execution"
    assert event.severity == "info"
    assert event.source == "trade_service.create_execution"
    assert event.actor_type == "service"
    assert event.actor_id == "trade_service"
    assert event.correlation_id == "entry-audit-client-1"
    assert event.strategy_name == "mean_reversion"
    assert event.instrument == "CS.D.EURUSD.CFD.IP"
    assert event.execution_id == execution.id
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["previous_state"] == "NOT_CREATED"
    assert event.payload_json["new_state"] == "SUBMISSION_PENDING"
    assert event.payload_json["phase"] == "ENTRY"
    assert event.payload_json["requested_size"] == 1.0
    assert event.payload_json["requested_price"] == 1.1
    assert event.payload_json["intended_risk_amount"] == 50.0


def test_audit_test_002_execution_transition_persists_domain_event_despite_global_noop(
    session,
):
    intent, execution = _seed_execution(session)

    updated = TradeService(session).transition_execution(
        execution,
        status=ExecutionStatus.ORDER_SUBMITTED,
        submitted_at=datetime(2026, 4, 10, 9, 1, tzinfo=UTC),
        broker_reference="deal-ref-audit-1",
        reason="Submitted to broker.",
    )

    events = _execution_events(session)
    assert updated.status == ExecutionStatus.ORDER_SUBMITTED.value
    assert [event.event_type for event in events] == [
        "execution.submission_pending_created",
        "execution.order_submitted",
    ]
    event = events[1]
    assert event.event_type == "execution.order_submitted"
    assert event.category == "execution"
    assert event.severity == "info"
    assert event.source == "trade_service.transition_execution"
    assert event.actor_type == "service"
    assert event.actor_id == "trade_service"
    assert event.correlation_id == "entry-audit-client-1"
    assert event.strategy_name == "mean_reversion"
    assert event.instrument == "CS.D.EURUSD.CFD.IP"
    assert event.execution_id == execution.id
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["previous_state"] == "SUBMISSION_PENDING"
    assert event.payload_json["new_state"] == "ORDER_SUBMITTED"
    assert event.payload_json["broker_reference"] == "deal-ref-audit-1"
    assert event.payload_json["requested_size"] == 1.0
    assert event.payload_json["intended_risk_amount"] == 50.0


def test_audit_test_002_execution_transition_records_related_domain_ids(session):
    intent, execution = _seed_execution(session)

    TradeService(session).transition_execution(
        execution,
        status=ExecutionStatus.CLOSE_CONFIRMED,
        local_position_id=17,
        local_trade_id=23,
        completed_at=datetime(2026, 4, 10, 9, 5, tzinfo=UTC),
        broker_reference="close-ref-audit-1",
        filled_size=1.0,
        average_fill_price=1.12,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        reason="Broker close confirmed.",
    )

    events = _execution_events(session)
    assert [event.event_type for event in events] == [
        "execution.submission_pending_created",
        "execution.position_closed",
    ]
    event = events[1]
    assert event.event_type == "execution.position_closed"
    assert event.position_id == 17
    assert event.trade_id == 23
    assert event.execution_id == execution.id
    assert event.payload_json["trade_intent_id"] == intent.id
    assert event.payload_json["previous_state"] == "SUBMISSION_PENDING"
    assert event.payload_json["new_state"] == "CLOSE_CONFIRMED"
    assert event.payload_json["filled_size"] == 1.0
    assert event.payload_json["average_fill_price"] == 1.12
    assert (
        event.payload_json["risk_truth_confidence"]
        == "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
    )


def test_audit_obs_001_execution_transition_marks_audit_persistence_failure(
    session, monkeypatch
):
    _, execution = _seed_execution(session)
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    updated = TradeService(session).transition_execution(
        execution,
        status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
        error_code="BrokerTimeout",
        error_message="Broker confirmation timed out.",
        requires_manual_review=True,
        reason="Broker outcome is ambiguous.",
    )

    events = _execution_events(session)
    assert [event.event_type for event in events] == [
        "execution.submission_pending_created"
    ]
    assert updated.status == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
    assert updated.requires_manual_review is True
    assert updated.details["domain_event_persistence_failed"] is True
    assert updated.details["audit_event_failures"] == [
        {
            "event_type": "execution.order_rejected",
            "source": "trade_service.transition_execution",
            "previous_state": "SUBMISSION_PENDING",
            "new_state": "NEEDS_MANUAL_REVIEW",
            "correlation_id": "entry-audit-client-1",
        }
    ]
