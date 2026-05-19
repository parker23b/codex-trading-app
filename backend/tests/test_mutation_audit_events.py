from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import select

from app.api.routes.allocation import (
    AlertActionRequest,
    acknowledge_allocation_alert,
    resolve_allocation_alert,
)
from app.api.routes.control_plane import (
    GovernanceUpdateRequest,
    OperatorControlUpdateRequest,
    reconcile_control_plane,
    update_operator_control_state,
    update_strategy_governance,
)
from app.api.routes.strategies import (
    StartStrategyRequest,
    StopStrategyRequest,
    start_strategy,
    start_strategy_by_name,
    stop_strategy,
    stop_strategy_by_name,
)
from app.models.allocation_alert import AllocationAlert
from app.models.domain_event import DomainEvent
from app.models.strategy_governance import StrategyFamilyGovernance
from app.services.domain_event_service import domain_event_service


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _seed_allocation_alert(session, *, state: str = "OPEN") -> AllocationAlert:
    alert = AllocationAlert(
        alert_key=f"audit-alert-{state.lower()}",
        alert_type="material_execution_drift",
        severity="error",
        state=state,
        escalation_level="critical",
        title="Material execution drift",
        message="Submitted risk drift needs operator attention.",
        count=1,
        recurrence_count=2,
        related_intent_ids=[7],
        related_cycle_ids=["cycle-1"],
        related_execution_ids=[42],
        details={"risk_delta": "material"},
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def test_audit_api_008_operator_control_mutation_persists_domain_event(session):
    response = update_operator_control_state(
        OperatorControlUpdateRequest(
            autonomous_control_enabled=False,
            reason="maintenance window",
        ),
        session,
    )

    events = _events(session)
    assert response.override_active is True
    assert response.override_value is False
    assert [event.event_type for event in events] == [
        "operator.autonomy_override_updated"
    ]
    assert events[0].source == "api.control_plane.update_operator_state"
    assert events[0].actor_type == "operator"
    assert events[0].payload_json["override_reason"] == "maintenance window"


def test_audit_api_008_operator_control_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        update_operator_control_state(
            OperatorControlUpdateRequest(autonomous_control_enabled=True),
            session,
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Operator control was updated, but durable audit persistence failed."
        )
    else:
        raise AssertionError("Expected mutation audit failure to block clean success")


def test_audit_api_008_governance_mutation_persists_domain_event(session):
    response = update_strategy_governance(
        "mean_reversion",
        GovernanceUpdateRequest(
            approval_state="DISABLED",
            autonomous_operation_allowed=False,
            emergency_stop=True,
            notes="disable during audit",
        ),
        session,
    )

    events = _events(session)
    assert response["approval_state"] == "DISABLED"
    assert [event.event_type for event in events] == ["operator.governance_updated"]
    assert events[0].strategy_name == "mean_reversion"
    assert events[0].payload_json["approval_state"] == "DISABLED"
    assert events[0].payload_json["emergency_stop"] is True


def test_audit_api_008_control_plane_reconcile_persists_domain_event(session):
    response = reconcile_control_plane(session)

    events = _events(session)
    assert set(response) == {
        "deployed",
        "paused",
        "blocked",
        "degraded",
        "emergency_stopped",
    }
    assert [event.event_type for event in events] == ["control_plane.reconciled"]
    assert events[0].source == "api.control_plane.reconcile"
    assert "deployed" in events[0].payload_json


def test_audit_api_008_strategy_start_stop_mutations_persist_domain_events(session):
    start_strategy(
        StartStrategyRequest(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
        ),
        session,
    )
    stop_strategy(
        StopStrategyRequest(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
        ),
        session,
    )

    events = _events(session)
    assert [event.event_type for event in events] == [
        "operator.runtime_started",
        "operator.runtime_stopped",
    ]
    assert events[0].runtime_id is not None
    assert events[0].strategy_name == "mean_reversion"
    assert events[1].payload_json == {
        "strategy_name": "mean_reversion",
        "instrument": "CS.D.EURUSD.CFD.IP",
    }


def test_audit_api_008_strategy_by_name_mutations_persist_domain_events(session):
    start_response = start_strategy_by_name("mean_reversion", session)
    stop_response = stop_strategy_by_name("mean_reversion", session)

    events = _events(session)
    assert start_response.status == "started"
    assert stop_response.status == "stopped"
    assert [event.event_type for event in events] == [
        "operator.runtime_started",
        "operator.runtime_stopped",
    ]
    assert events[0].source == "api.strategies.start_by_name"
    assert events[1].source == "api.strategies.stop_by_name"


def test_audit_api_008_allocation_alert_mutations_persist_domain_events(session):
    open_alert = _seed_allocation_alert(session)
    acknowledged_response = acknowledge_allocation_alert(
        open_alert.id or 0,
        AlertActionRequest(actor_id="risk-operator"),
        session,
    )
    resolved_response = resolve_allocation_alert(
        open_alert.id or 0,
        AlertActionRequest(actor_id="risk-operator"),
        session,
    )

    events = _events(session)
    assert acknowledged_response["state"] == "ACKNOWLEDGED"
    assert resolved_response["state"] == "RESOLVED"
    assert [event.event_type for event in events] == [
        "operator.allocation_alert_acknowledged",
        "operator.allocation_alert_resolved",
    ]
    assert [event.source for event in events] == [
        "api.allocation.alerts.acknowledge",
        "api.allocation.alerts.resolve",
    ]
    assert events[0].actor_type == "operator"
    assert events[0].actor_id == "risk-operator"
    assert events[0].payload_json["alert_id"] == open_alert.id
    assert events[0].payload_json["previous_state"] == "OPEN"
    assert events[0].payload_json["state"] == "ACKNOWLEDGED"
    assert events[0].payload_json["related_execution_ids"] == [42]
    assert events[1].payload_json["previous_state"] == "ACKNOWLEDGED"
    assert events[1].payload_json["state"] == "RESOLVED"


def test_audit_api_008_allocation_alert_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    alert = _seed_allocation_alert(session)
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        acknowledge_allocation_alert(
            alert.id or 0,
            AlertActionRequest(actor_id="risk-operator"),
            session,
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Allocation alert was acknowledged, but durable audit persistence failed."
        )
    else:
        raise AssertionError(
            "Expected allocation alert audit failure to block clean success"
        )


def test_audit_test_002_default_fixture_still_allows_required_route_audit_events(
    session,
):
    update_strategy_governance(
        "mean_reversion",
        GovernanceUpdateRequest(approval_state="APPROVED"),
        session,
    )

    events = _events(session)
    governance_rows = session.exec(select(StrategyFamilyGovernance)).all()
    assert len(events) == 1
    assert events[0].event_type == "operator.governance_updated"
    assert governance_rows
