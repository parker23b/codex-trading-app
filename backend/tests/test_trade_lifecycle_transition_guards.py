from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.core.broker import OrderDirection
from app.models.domain_event import DomainEvent
from app.models.trade import (
    Execution,
    ExecutionPhase,
    ExecutionStatus,
    Position,
    TradeIntent,
    TradeIntentState,
)
from app.services.lifecycle_rules import (
    EXECUTION_IDEMPOTENT_STATUSES,
    EXECUTION_LEGACY_COMPATIBILITY_STATUSES,
    EXECUTION_TERMINAL_STATUSES,
    EXECUTION_TRANSITIONS,
    TRADE_INTENT_IDEMPOTENT_STATES,
    TRADE_INTENT_PROVENANCE_STATES,
    TRADE_INTENT_TERMINAL_STATES,
    TRADE_INTENT_TRANSITIONS,
)
from app.services.reconciliation_service import ReconciliationService
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position


pytestmark = pytest.mark.usefixtures("audit_critical_domain_events")


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _make_intent(
    session,
    *,
    state: TradeIntentState,
    signal_time: datetime | None = None,
) -> TradeIntent:
    trade_service = TradeService(session)
    at = signal_time or datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    return trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="smoke_test_hold",
            family_name="smoke_test",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            state=state.value,
            signal_time=at,
            proposed_size=0.2,
            allocated_size=0.2,
            broker_reference="guard-intent-ref"
            if state != TradeIntentState.PROPOSED
            else None,
            execution_client_request_id="guard-intent-request",
            opened_at=at if state in TRADE_INTENT_PROVENANCE_STATES else None,
        )
    )


def _make_execution(
    session,
    *,
    status: ExecutionStatus,
    phase: ExecutionPhase = ExecutionPhase.ENTRY,
    signal_time: datetime | None = None,
) -> Execution:
    trade_service = TradeService(session)
    at = signal_time or datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    return trade_service.create_execution(
        Execution(
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            phase=phase.value,
            status=status.value,
            client_request_id="guard-execution-request",
            broker_reference="guard-execution-ref",
            signal_time=at,
            requested_size=0.2,
            requested_price=100.0,
        )
    )


@pytest.mark.parametrize(
    ("state", "target"),
    [
        (state, target)
        for state, targets in TRADE_INTENT_TRANSITIONS.items()
        for target in targets
    ],
)
def test_trade_intent_transition_table_allows_classified_transitions(
    session, state, target
):
    trade_service = TradeService(session)
    intent = _make_intent(session, state=state)

    updated = trade_service.transition_trade_intent(
        intent,
        state=target,
        details={"table_test_target": target.value},
    )

    assert updated.state == target.value


@pytest.mark.parametrize(
    ("status", "target"),
    [
        (status, target)
        for status, targets in EXECUTION_TRANSITIONS.items()
        for target in targets
        if status not in EXECUTION_LEGACY_COMPATIBILITY_STATUSES
    ],
)
def test_execution_transition_table_allows_classified_transitions(
    session, status, target
):
    trade_service = TradeService(session)
    execution = _make_execution(session, status=status)

    updated = trade_service.transition_execution(
        execution,
        status=target,
        details={"table_test_target": target.value},
    )

    assert updated.status == target.value


@pytest.mark.parametrize(
    ("state", "target"),
    [
        (TradeIntentState.PROPOSED, TradeIntentState.POSITION_OPENED),
        (TradeIntentState.CLOSED, TradeIntentState.POSITION_OPENED),
        (
            TradeIntentState.RECOVERED_POSITION_ATTACHED,
            TradeIntentState.POSITION_OPENED,
        ),
        (TradeIntentState.EXTERNAL_POSITION_ADOPTED, TradeIntentState.POSITION_OPENED),
        (TradeIntentState.APPROVED, TradeIntentState.CLOSED),
    ],
)
def test_trade_intent_invalid_transition_rejects_without_mutation_or_audit(
    session, state, target
):
    trade_service = TradeService(session)
    intent = _make_intent(session, state=state)
    event_count = len(_events(session))

    with pytest.raises(ValueError, match=f"{state.value} to {target.value}"):
        trade_service.transition_trade_intent(
            intent,
            state=target,
            details={"invalid_transition": True},
        )

    refreshed = session.get(TradeIntent, intent.id)
    assert refreshed is not None
    assert refreshed.state == state.value
    assert len(_events(session)) == event_count


@pytest.mark.parametrize(
    ("status", "target"),
    [
        (ExecutionStatus.ORDER_SUBMITTED, ExecutionStatus.POSITION_OPENED),
        (ExecutionStatus.POSITION_OPENED, ExecutionStatus.NEEDS_MANUAL_REVIEW),
        (ExecutionStatus.FAILED, ExecutionStatus.ORDER_SUBMITTED),
        (ExecutionStatus.CLOSE_CONFIRMED, ExecutionStatus.ORDER_SUBMITTED),
    ],
)
def test_execution_invalid_transition_rejects_without_mutation_or_audit(
    session, status, target
):
    trade_service = TradeService(session)
    execution = _make_execution(session, status=status)
    event_count = len(_events(session))

    with pytest.raises(ValueError, match=f"{status.value} to {target.value}"):
        trade_service.transition_execution(
            execution,
            status=target,
            details={"invalid_transition": True},
        )

    refreshed = session.get(Execution, execution.id)
    assert refreshed is not None
    assert refreshed.status == status.value
    assert len(_events(session)) == event_count


def test_trade_intent_same_state_idempotent_update_preserves_row_without_audit(session):
    trade_service = TradeService(session)
    intent = _make_intent(session, state=TradeIntentState.ACKNOWLEDGED)
    event_count = len(_events(session))

    updated = trade_service.transition_trade_intent(
        intent,
        state=TradeIntentState.ACKNOWLEDGED,
        decision_reason_code="broker_confirmation_ambiguous",
        details={"ambiguous_confirmation": True},
    )

    assert TradeIntentState.ACKNOWLEDGED in TRADE_INTENT_IDEMPOTENT_STATES
    assert updated.state == TradeIntentState.ACKNOWLEDGED.value
    assert updated.details["ambiguous_confirmation"] is True
    assert len(_events(session)) == event_count


def test_execution_same_state_idempotent_update_preserves_row_without_audit(session):
    trade_service = TradeService(session)
    execution = _make_execution(session, status=ExecutionStatus.SUBMISSION_PENDING)
    event_count = len(_events(session))

    updated = trade_service.transition_execution(
        execution,
        status=ExecutionStatus.SUBMISSION_PENDING,
        details={"duplicate_attempt_count": 1},
    )

    assert ExecutionStatus.SUBMISSION_PENDING in EXECUTION_IDEMPOTENT_STATUSES
    assert updated.status == ExecutionStatus.SUBMISSION_PENDING.value
    assert updated.details["duplicate_attempt_count"] == 1
    assert len(_events(session)) == event_count


def test_create_execution_rejects_new_legacy_status_write(session):
    trade_service = TradeService(session)

    with pytest.raises(ValueError, match="compatibility-only"):
        trade_service.create_execution(
            Execution(
                strategy_name="smoke_test_hold",
                instrument="CS.D.EURUSD.MINI.IP",
                phase=ExecutionPhase.ENTRY.value,
                status=ExecutionStatus.SIGNAL_GENERATED.value,
                client_request_id="legacy-write-create",
                signal_time=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
            )
        )


def test_transition_execution_rejects_new_legacy_status_write(session):
    trade_service = TradeService(session)
    execution = _make_execution(session, status=ExecutionStatus.SUBMISSION_PENDING)
    event_count = len(_events(session))

    with pytest.raises(ValueError, match="compatibility-only"):
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.SIGNAL_GENERATED,
        )

    refreshed = session.get(Execution, execution.id)
    assert refreshed is not None
    assert refreshed.status == ExecutionStatus.SUBMISSION_PENDING.value
    assert len(_events(session)) == event_count


def test_failed_execution_retry_creates_new_attempt_instead_of_reactivating_terminal_row(
    session, fixed_now
):
    trade_service = TradeService(session)
    failed = _make_execution(
        session,
        status=ExecutionStatus.FAILED,
        signal_time=fixed_now,
    )

    execution, should_submit = StrategyService._prepare_execution(
        trade_service=trade_service,
        strategy_name="smoke_test_hold",
        instrument="CS.D.EURUSD.MINI.IP",
        phase=ExecutionPhase.ENTRY.value,
        signal_time=fixed_now + timedelta(seconds=5),
        requested_size=0.2,
        requested_price=100.2,
        reason="Retry after terminal failure",
        details={"action_key": "entry:smoke_test_hold:CS.D.EURUSD.MINI.IP:BUY"},
    )

    executions = trade_service.list_executions(limit=10)
    assert should_submit is True
    assert execution.id != failed.id
    assert execution.status == ExecutionStatus.SUBMISSION_PENDING.value
    assert failed.status == ExecutionStatus.FAILED.value
    assert len(executions) == 2


def test_reconciliation_preserves_recovered_trade_intent_provenance(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    intent = _make_intent(
        session,
        state=TradeIntentState.RECOVERED_POSITION_ATTACHED,
        signal_time=fixed_now - timedelta(minutes=2),
    )
    position = trade_service.record_broker_position(
        Position(
            trade_intent_id=intent.id,
            strategy_name="smoke_test_hold",
            family_name="smoke_test",
            broker_reference="recover-preserve-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            size=0.2,
            open_price=100.0,
            open_time=fixed_now - timedelta(minutes=2),
            current_price=100.1,
            unrealized_pnl=0.02,
            account_type="DEMO",
            is_open=True,
            broker_sync_status="PENDING",
        )
    )
    intent = trade_service.transition_trade_intent(
        intent,
        state=TradeIntentState.RECOVERED_POSITION_ATTACHED,
        broker_reference=position.broker_reference,
        position_id=position.id,
    )
    broker.remote_positions = [
        make_broker_position(
            broker_reference="recover-preserve-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.2,
            open_price=100.0,
            opened_at=fixed_now - timedelta(minutes=2),
        )
    ]

    ReconciliationService(trade_service).reconcile_open_positions()

    refreshed = session.get(TradeIntent, intent.id)
    assert refreshed is not None
    assert refreshed.state == TradeIntentState.RECOVERED_POSITION_ATTACHED.value


def test_transition_tables_cover_every_lifecycle_enum_value():
    assert set(TRADE_INTENT_TRANSITIONS) == set(TradeIntentState)
    assert set(EXECUTION_TRANSITIONS) == set(ExecutionStatus)
    assert TRADE_INTENT_TERMINAL_STATES <= set(TradeIntentState)
    assert TRADE_INTENT_PROVENANCE_STATES <= set(TradeIntentState)
    assert EXECUTION_TERMINAL_STATUSES <= set(ExecutionStatus)
    assert EXECUTION_LEGACY_COMPATIBILITY_STATUSES <= set(ExecutionStatus)
