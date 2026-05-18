from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import select

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
from app.models.domain_event import DomainEvent
from app.models.strategy_governance import StrategyFamilyGovernance
from app.services.domain_event_service import domain_event_service


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


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
