from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import HTTPException
from starlette.requests import Request
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
from app.api.routes.ai_reviewer import (
    OperationalQuestionRequest,
    answer_operational_question,
    get_daily_review,
    get_operator_summary,
    get_runtime_health_review,
    get_strategy_review,
    get_trade_postmortem,
)
from app.api.routes.markets import (
    BulkStrategyWatchlistRequest,
    add_shortlist_item,
    add_strategy_watchlist_items,
    remove_shortlist_item,
    remove_strategy_watchlist_item,
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
from app.models.review import GeneratedReviewRecord
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import Trade
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry
from app.services.domain_event_service import domain_event_service


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _request(
    *,
    method: str = "POST",
    path: str = "/strategy/start",
    headers: dict[str, str] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "query_string": b"",
        }
    )


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


def _seed_closed_trade(session) -> Trade:
    trade = Trade(
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=1.0,
        open_price=1.1,
        close_price=1.2,
        open_time=datetime(2026, 4, 9, 9, 0, tzinfo=UTC),
        close_time=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
        pnl=100.0,
        account_type="DEMO",
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


def test_audit_api_008_operator_control_mutation_persists_domain_event(session):
    response = update_operator_control_state(
        OperatorControlUpdateRequest(
            autonomous_control_enabled=False,
            reason="maintenance window",
        ),
        _request(path="/control-plane/operator-state"),
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
            _request(path="/control-plane/operator-state"),
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
        _request(path="/control-plane/governance/mean_reversion"),
        session,
    )

    events = _events(session)
    assert response.approval_state == "DISABLED"
    assert [event.event_type for event in events] == ["operator.governance_updated"]
    assert events[0].strategy_name == "mean_reversion"
    assert events[0].payload_json["approval_state"] == "DISABLED"
    assert events[0].payload_json["emergency_stop"] is True


def test_audit_api_008_control_plane_reconcile_persists_domain_event(session):
    response = reconcile_control_plane(
        _request(path="/control-plane/reconcile"), session
    )

    events = _events(session)
    assert response.model_dump().keys() == {
        "deployed",
        "paused",
        "blocked",
        "degraded",
        "emergency_stopped",
    }
    reconciled_events = [
        event for event in events if event.event_type == "control_plane.reconciled"
    ]
    assert len(reconciled_events) == 1
    assert reconciled_events[0].source == "api.control_plane.reconcile"
    assert "deployed" in reconciled_events[0].payload_json


def test_audit_api_008_strategy_start_stop_mutations_persist_domain_events(session):
    start_strategy(
        StartStrategyRequest(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
        ),
        _request(path="/strategy/start"),
        session,
    )
    stop_strategy(
        StopStrategyRequest(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
        ),
        _request(path="/strategy/stop"),
        session,
    )

    events = _events(session)
    assert [event.event_type for event in events] == [
        "strategy.runtime_started",
        "operator.runtime_started",
        "strategy.runtime_stopped",
        "operator.runtime_stopped",
    ]
    assert events[0].runtime_id is not None
    assert events[0].strategy_name == "mean_reversion"
    assert events[1].source == "api.strategy.start"
    assert events[2].payload_json["previous_state"] == "RUNNING"
    assert events[2].payload_json["new_state"] == "STOPPED"
    assert events[3].payload_json == {
        "strategy_name": "mean_reversion",
        "instrument": "CS.D.EURUSD.CFD.IP",
    }


def test_audit_api_008_strategy_by_name_mutations_persist_domain_events(session):
    start_response = start_strategy_by_name(
        "mean_reversion",
        _request(path="/strategies/mean_reversion/start"),
        session,
    )
    stop_response = stop_strategy_by_name(
        "mean_reversion",
        _request(path="/strategies/mean_reversion/stop"),
        session,
    )

    events = _events(session)
    assert start_response.status == "started"
    assert stop_response.status == "stopped"
    assert [event.event_type for event in events] == [
        "strategy.runtime_started",
        "operator.runtime_started",
        "strategy.runtime_stopped",
        "operator.runtime_stopped",
    ]
    assert events[0].source == "strategy_service.start_strategy"
    assert events[1].source == "api.strategies.start_by_name"
    assert events[2].source == "strategy_service.stop_strategy"
    assert events[3].source == "api.strategies.stop_by_name"


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
    assert acknowledged_response.state == "ACKNOWLEDGED"
    assert resolved_response.state == "RESOLVED"
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
        _request(path="/control-plane/governance/mean_reversion"),
        session,
    )

    events = _events(session)
    governance_rows = session.exec(select(StrategyFamilyGovernance)).all()
    assert len(events) == 1
    assert events[0].event_type == "operator.governance_updated"
    assert governance_rows


def test_audit_api_008_review_persist_true_routes_persist_domain_events(session):
    trade = _seed_closed_trade(session)

    operator_response = get_operator_summary(session=session, persist=True)
    daily_response = get_daily_review(
        review_date=date(2026, 4, 9), session=session, persist=True
    )
    strategy_response = get_strategy_review(
        "mean_reversion", days=7, session=session, persist=True
    )
    runtime_response = get_runtime_health_review(
        hours=24, session=session, persist=True
    )
    postmortem_response = get_trade_postmortem(
        trade.id or 0, session=session, persist=True
    )

    records = session.exec(
        select(GeneratedReviewRecord).order_by(GeneratedReviewRecord.id)
    ).all()
    events = _events(session)
    assert [record.review_type for record in records] == [
        "operator_summary",
        "daily_review",
        "strategy_review",
        "runtime_health_review",
        "trade_postmortem",
    ]
    assert [
        operator_response.metadata.review_id,
        daily_response.metadata.review_id,
        strategy_response.metadata.review_id,
        runtime_response.metadata.review_id,
        postmortem_response.metadata.review_id,
    ] == [record.id for record in records]
    assert [event.event_type for event in events] == [
        "operator.review_persisted",
        "operator.review_persisted",
        "operator.review_persisted",
        "operator.review_persisted",
        "operator.review_persisted",
    ]
    assert [event.source for event in events] == [
        "api.reviews.operator_summary.persist",
        "api.reviews.daily.persist",
        "api.reviews.strategies.persist",
        "api.reviews.runtime_health.persist",
        "api.reviews.trades.postmortem.persist",
    ]
    assert {event.actor_type for event in events} == {"operator"}
    assert {event.actor_id for event in events} == {"operator"}
    assert [event.correlation_id for event in events] == [
        f"review:{record.review_type}:{record.id}" for record in records
    ]
    assert events[2].strategy_name == "mean_reversion"
    assert events[4].trade_id == trade.id
    assert events[4].strategy_name == "mean_reversion"
    assert events[4].instrument == "CS.D.EURUSD.CFD.IP"
    for event, record in zip(events, records, strict=True):
        assert event.category == "review"
        assert event.payload_json["review_id"] == record.id
        assert event.payload_json["review_type"] == record.review_type
        assert event.payload_json["previous_state"] == "NOT_PERSISTED"
        assert event.payload_json["new_state"] == "PERSISTED"
        assert event.payload_json["generation_mode"] == record.generation_mode
        assert "scope" in event.payload_json


def test_audit_api_008_review_advisory_question_persists_domain_event(session):
    response = answer_operational_question(
        OperationalQuestionRequest(
            question="What runtime risk needs attention?",
            strategy_name="mean_reversion",
            actor_id="desk-operator",
        ),
        session=session,
    )

    records = session.exec(select(GeneratedReviewRecord)).all()
    events = _events(session)
    assert len(records) == 1
    assert records[0].review_type == "operational_question"
    assert response.metadata.review_id == records[0].id
    assert len(events) == 1
    assert events[0].event_type == "operator.review_advisory_persisted"
    assert events[0].source == "api.reviews.questions"
    assert events[0].actor_type == "operator"
    assert events[0].actor_id == "desk-operator"
    assert events[0].strategy_name == "mean_reversion"
    assert events[0].correlation_id == f"review:operational_question:{records[0].id}"
    assert events[0].payload_json["review_id"] == records[0].id
    assert events[0].payload_json["review_type"] == "operational_question"
    assert events[0].payload_json["previous_state"] == "NOT_PERSISTED"
    assert events[0].payload_json["new_state"] == "PERSISTED"
    assert events[0].payload_json["question"] == "What runtime risk needs attention?"
    assert events[0].payload_json["routed_review_type"] == "runtime_health_review"


def test_audit_api_008_review_persist_true_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        get_operator_summary(session=session, persist=True)
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Review was persisted, but durable audit persistence failed."
        )
    else:
        raise AssertionError("Expected review audit failure to block clean success")

    records = session.exec(select(GeneratedReviewRecord)).all()
    assert len(records) == 1
    assert records[0].review_type == "operator_summary"
    assert _events(session) == []


def test_audit_api_008_review_advisory_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        answer_operational_question(
            OperationalQuestionRequest(question="What needs attention?"),
            session=session,
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Advisory review was persisted, but durable audit persistence failed."
        )
    else:
        raise AssertionError("Expected advisory audit failure to block clean success")

    records = session.exec(select(GeneratedReviewRecord)).all()
    assert len(records) == 1
    assert records[0].review_type == "operational_question"
    assert _events(session) == []


def test_audit_api_008_shortlist_mutations_persist_domain_events(session):
    added_response = add_shortlist_item("CS.D.EURUSD.CFD.IP", session)
    removed_response = remove_shortlist_item("CS.D.EURUSD.CFD.IP", session)

    entries = session.exec(select(OperatorShortlistEntry)).all()
    events = _events(session)
    assert added_response["status"] == "shortlisted"
    assert removed_response == {
        "status": "removed",
        "instrument": "CS.D.EURUSD.CFD.IP",
    }
    assert entries == []
    assert [event.event_type for event in events] == [
        "operator.shortlist_item_added",
        "operator.shortlist_item_removed",
    ]
    assert [event.source for event in events] == [
        "api.markets.shortlist.add",
        "api.markets.shortlist.remove",
    ]
    assert {event.actor_type for event in events} == {"operator"}
    assert {event.actor_id for event in events} == {"api"}
    assert [event.instrument for event in events] == [
        "CS.D.EURUSD.CFD.IP",
        "CS.D.EURUSD.CFD.IP",
    ]
    assert events[0].payload_json["previous_state"] == "NOT_SHORTLISTED"
    assert events[0].payload_json["new_state"] == "SHORTLISTED"
    assert events[0].payload_json["shortlist_entry_id"] is not None
    assert events[1].payload_json["previous_state"] == "SHORTLISTED"
    assert events[1].payload_json["new_state"] == "NOT_SHORTLISTED"
    assert (
        events[1].payload_json["shortlist_entry_id"]
        == events[0].payload_json["shortlist_entry_id"]
    )


def test_audit_api_008_strategy_watchlist_mutations_persist_domain_events(session):
    bulk_response = add_strategy_watchlist_items(
        BulkStrategyWatchlistRequest(
            instrument_ids=["CS.D.EURUSD.CFD.IP", "CS.D.GBPUSD.CFD.IP"]
        ),
        session,
    )
    remove_response = remove_strategy_watchlist_item("CS.D.EURUSD.CFD.IP", session)

    rows = session.exec(
        select(WatchlistEntry).order_by(WatchlistEntry.instrument)
    ).all()
    events = _events(session)
    assert [item["instrument"] for item in bulk_response["added"]] == [
        "CS.D.EURUSD.CFD.IP",
        "CS.D.GBPUSD.CFD.IP",
    ]
    assert remove_response == {
        "status": "removed",
        "instrument": "CS.D.EURUSD.CFD.IP",
    }
    assert [event.event_type for event in events] == [
        "operator.strategy_watchlist_bulk_added",
        "operator.strategy_watchlist_item_removed",
    ]
    assert events[0].source == "api.markets.strategy_watchlist.bulk_add"
    assert events[0].actor_type == "operator"
    assert events[0].actor_id == "api"
    assert events[0].payload_json["requested_instrument_ids"] == [
        "CS.D.EURUSD.CFD.IP",
        "CS.D.GBPUSD.CFD.IP",
    ]
    assert events[0].payload_json["previous_states"] == {
        "CS.D.EURUSD.CFD.IP": "NOT_IN_STRATEGY_WATCHLIST",
        "CS.D.GBPUSD.CFD.IP": "NOT_IN_STRATEGY_WATCHLIST",
    }
    assert events[0].payload_json["new_states"] == {
        "CS.D.EURUSD.CFD.IP": "ACTIVE",
        "CS.D.GBPUSD.CFD.IP": "ACTIVE",
    }
    assert events[0].payload_json["watchlist_entry_ids"]["CS.D.EURUSD.CFD.IP"]
    assert events[0].payload_json["added_count"] == 2
    assert events[0].payload_json["skipped_count"] == 0
    assert events[1].source == "api.markets.strategy_watchlist.remove"
    assert events[1].instrument == "CS.D.EURUSD.CFD.IP"
    assert events[1].payload_json["previous_state"] == "ACTIVE"
    assert events[1].payload_json["new_state"] == "COOLDOWN"
    assert (
        events[1].payload_json["watchlist_entry_id"]
        == events[0].payload_json["watchlist_entry_ids"]["CS.D.EURUSD.CFD.IP"]
    )
    assert {row.instrument: row.status for row in rows} == {
        "CS.D.EURUSD.CFD.IP": "COOLDOWN",
        "CS.D.GBPUSD.CFD.IP": "ACTIVE",
    }


def test_audit_api_008_watchlist_mutation_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        add_shortlist_item("CS.D.EURUSD.CFD.IP", session)
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Shortlist item was added, but durable audit persistence failed."
        )
    else:
        raise AssertionError("Expected shortlist audit failure to block clean success")

    entries = session.exec(select(OperatorShortlistEntry)).all()
    assert [entry.instrument for entry in entries] == ["CS.D.EURUSD.CFD.IP"]
    assert _events(session) == []


def test_audit_api_008_strategy_watchlist_returns_error_if_audit_persistence_fails(
    session, monkeypatch
):
    add_strategy_watchlist_items(
        BulkStrategyWatchlistRequest(instrument_ids=["CS.D.EURUSD.CFD.IP"]),
        session,
    )
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    try:
        remove_strategy_watchlist_item("CS.D.EURUSD.CFD.IP", session)
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == (
            "Strategy watchlist item was removed, but durable audit persistence failed."
        )
    else:
        raise AssertionError(
            "Expected strategy-watchlist audit failure to block clean success"
        )

    rows = session.exec(select(WatchlistEntry)).all()
    events = _events(session)
    assert [row.status for row in rows] == ["COOLDOWN"]
    assert [event.event_type for event in events] == [
        "operator.strategy_watchlist_bulk_added"
    ]
