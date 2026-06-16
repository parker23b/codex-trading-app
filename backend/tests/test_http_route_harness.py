from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Any

import pytest
from sqlmodel import Session, select

from app.models.allocation_alert import AllocationAlert
from app.models.backtest import (
    BacktestEquityPoint,
    BacktestMetric,
    BacktestRun,
    BacktestRunInstrument,
    BacktestTrade,
    BacktestWarning,
    HistoricalDataset,
    HistoricalDatasetPartition,
)
from app.models.domain_event import DomainEvent
from app.models.operator_control import OperatorControlState
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import (
    AllocationCycle,
    Execution,
    ExecutionPhase,
    ExecutionStatus,
    Position,
    ReconciliationEvent,
    Trade,
    TradeIntent,
    TradeIntentState,
)
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry
from app.services.allocation_alert_service import AllocationAlertService
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service


TRACKED_MODELS = (
    AllocationAlert,
    AllocationCycle,
    BacktestEquityPoint,
    BacktestMetric,
    BacktestRun,
    BacktestRunInstrument,
    BacktestTrade,
    BacktestWarning,
    DomainEvent,
    Execution,
    GeneratedReviewRecord,
    HistoricalDataset,
    HistoricalDatasetPartition,
    OperatorControlState,
    OperatorShortlistEntry,
    Position,
    ReconciliationEvent,
    StrategyDeployment,
    StrategyFamilyGovernance,
    StrategyRuntimeState,
    Trade,
    TradeIntent,
    WatchlistEntry,
)

AUTH_HEADER = {"Authorization": "Bearer expected-token"}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _snapshot_rows(session: Session) -> dict[str, list[dict[str, Any]]]:
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for model in TRACKED_MODELS:
        rows = session.exec(select(model)).all()
        serialized = [
            {
                column.name: _normalize_value(getattr(row, column.name))
                for column in model.__table__.columns
            }
            for row in rows
        ]
        snapshot[model.__name__] = sorted(
            serialized, key=lambda item: json.dumps(item, sort_keys=True)
        )
    return snapshot


def _seed_http_read_state(session: Session) -> dict[str, Any]:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)

    governance = StrategyFamilyGovernance(
        strategy_name="mean_reversion",
        approval_state="APPROVED",
        autonomous_operation_allowed=True,
        approved_asset_classes=["forex"],
        approved_instruments=["CS.D.EURUSD.CFD.IP"],
        approved_profile_names=["default"],
        updated_at=now,
    )
    deployment = StrategyDeployment(
        strategy_name="mean_reversion",
        governance_id=1,
        deployment_key="mean_reversion:CS.D.EURUSD.CFD.IP",
        state="AUTO_DEPLOYED",
        selected_profile="default",
        selected_instrument="CS.D.EURUSD.CFD.IP",
        selected_asset_class="forex",
        open_risk_management_state="MANAGED",
        last_evaluated_at=now,
        last_deployed_at=now,
        updated_at=now,
    )
    runtime = StrategyRuntimeState(
        runtime_id="runtime-http-1",
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        status="RUNNING",
        recovery_state="HEALTHY",
        control_mode="AUTO",
        runtime_mode="NORMAL",
        started_at=now,
        last_heartbeat_at=now,
        last_price_seen=1.101,
        last_price_seen_at=now,
        updated_at=now,
    )
    operator_state = OperatorControlState(
        autonomous_control_override=None,
        updated_at=now,
    )
    cycle = AllocationCycle(
        cycle_id="cycle-http-1",
        received_at=now,
        completed_at=now,
        candidate_count=1,
        approved_count=1,
        total_requested_risk_percent=0.5,
        total_allocated_risk_percent=0.5,
        remaining_portfolio_risk_percent=3.5,
    )
    intent = TradeIntent(
        strategy_name="mean_reversion",
        family_name="mean_reversion",
        allocation_cycle_id="cycle-http-1",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        state=TradeIntentState.POSITION_OPENED.value,
        signal_time=now,
        proposed_size=1.0,
        allocated_size=1.0,
        proposed_risk_percent=0.5,
        allocated_risk_percent=0.5,
        estimated_risk_amount=50.0,
        submitted_risk_amount=50.0,
        fill_derived_risk_amount=50.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        decision_reason_code="APPROVED",
        decision_reason="Approved for route harness.",
        observed_price=1.1,
        average_fill_price=1.101,
        filled_size=1.0,
        broker_reference="deal-http-1",
        execution_client_request_id="entry-http-1",
        opened_at=now,
        updated_at=now,
    )
    position = Position(
        trade_intent_id=1,
        strategy_name="mean_reversion",
        family_name="mean_reversion",
        broker_reference="deal-http-1",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=1.0,
        open_price=1.101,
        open_time=now,
        current_price=1.102,
        unrealized_pnl=10.0,
        risk_percent=0.5,
        entry_risk_amount=50.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        account_type="DEMO",
        is_open=True,
        broker_sync_status="CONFIRMED",
    )
    execution = Execution(
        trade_intent_id=1,
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        phase=ExecutionPhase.ENTRY.value,
        status=ExecutionStatus.POSITION_OPENED.value,
        client_request_id="entry-http-1",
        broker_reference="deal-http-1",
        local_position_id=1,
        signal_time=now,
        submitted_at=now,
        acknowledged_at=now,
        completed_at=now,
        requested_size=1.0,
        filled_size=1.0,
        requested_price=1.1,
        average_fill_price=1.101,
        intended_risk_amount=50.0,
        submitted_risk_amount=50.0,
        fill_derived_risk_amount=50.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        reason="Filled for HTTP harness.",
        updated_at=now,
    )
    trade = Trade(
        trade_intent_id=1,
        strategy_name="mean_reversion",
        family_name="mean_reversion",
        broker_reference="deal-http-0",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=1.0,
        open_price=1.09,
        close_price=1.11,
        open_time=now,
        close_time=now,
        pnl=20.0,
        entry_risk_amount=45.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        account_type="DEMO",
    )
    alert = AllocationAlert(
        alert_key="alert-http-1",
        alert_type="material_execution_drift",
        severity="error",
        state="OPEN",
        escalation_level="critical",
        title="Material execution drift",
        message="Existing persisted alert",
        count=1,
        recurrence_count=1,
        related_intent_ids=[1],
        related_cycle_ids=["cycle-http-1"],
        related_execution_ids=[1],
        details={"name": "execution_drift"},
        updated_at=now,
    )
    domain_event = DomainEvent(
        created_at=now,
        event_type="strategy.runtime_started",
        category="runtime",
        severity="info",
        source="tests.http_harness",
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        title="Runtime started",
        payload_json={"runtime_id": "runtime-http-1"},
    )
    reconciliation_event = ReconciliationEvent(
        event_type="execution.reconciled",
        trade_intent_id=1,
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        broker_reference="deal-http-1",
        local_position_id=1,
        details={"status": "matched"},
        created_at=now,
    )
    watchlist_entry = WatchlistEntry(
        instrument="CS.D.EURUSD.CFD.IP",
        tier="TIER1",
        status="ACTIVE",
        asset_class="forex",
        pinned=True,
        reason="http-test",
        priority_score=80.0,
        assigned_at=now,
        last_streamed_at=now,
        last_refreshed_at=now,
        updated_at=now,
    )
    shortlist_entry = OperatorShortlistEntry(
        instrument="IX.D.FTSE.CFD.IP",
        actor_id="operator",
        note="Keep visible for route harness.",
        created_at=now,
        updated_at=now,
    )
    review_record = GeneratedReviewRecord(
        review_type="operator_summary",
        scope={"window": "24h"},
        generated_at=now,
        facts_payload={"open_risk_percent": 0.5},
        derived_observations=[
            {
                "code": "open_risk_ok",
                "severity": "info",
                "label": "Open risk stable",
                "detail": "Route harness review",
                "confidence": 0.8,
                "rank": 1,
                "time_scope": "24h",
                "supporting_metrics": [],
            }
        ],
        possible_contributors=[],
        warnings=[],
        supporting_metrics=[],
        generation_mode="deterministic_only",
    )

    session.add(governance)
    session.commit()
    session.refresh(governance)

    deployment.governance_id = governance.id
    session.add_all(
        [
            deployment,
            runtime,
            operator_state,
            cycle,
            intent,
            position,
            execution,
            trade,
            alert,
            domain_event,
            reconciliation_event,
            watchlist_entry,
            shortlist_entry,
            review_record,
        ]
    )
    session.commit()
    session.refresh(intent)
    session.refresh(trade)
    session.refresh(review_record)

    get_health_service().heartbeat(now)
    get_health_service().record_price_update(now)

    return {
        "alert_id": alert.id,
        "cycle_id": cycle.cycle_id,
        "domain_event_id": domain_event.id,
        "execution_id": execution.id,
        "instrument": watchlist_entry.instrument,
        "review_id": review_record.id,
        "trade_id": trade.id,
        "trade_intent_id": intent.id,
    }


@pytest.mark.parametrize(
    ("path_template", "query_params"),
    [
        ("/health", None),
        ("/health/stream", None),
        ("/system/health", None),
        ("/system/telemetry", None),
        ("/system/limits", None),
        ("/control-plane/summary", None),
        ("/control-plane/operator-state", None),
        ("/control-plane/strategies/mean_reversion", None),
        ("/coverage/summary", None),
        ("/dashboard", None),
        ("/events", None),
        ("/events/{domain_event_id}", None),
        ("/allocation/cycles", None),
        ("/allocation/cycles/{cycle_id}", None),
        ("/allocation/intents", None),
        ("/allocation/intents/{trade_intent_id}", None),
        ("/allocation/drift", None),
        ("/allocation/alerts", None),
        ("/allocation/alerts/unresolved-critical", None),
        ("/allocation/exposure", None),
        ("/market-status/{instrument}", None),
        ("/markets/overview", None),
        ("/markets/catalogue", None),
        ("/watchlist/shortlist", None),
        ("/strategy-watchlist", None),
        ("/market-data/feed-state", None),
        ("/market-data/feed-state/{instrument}", None),
        ("/charts/risk-allocation", None),
        ("/positions", None),
        ("/executions", None),
        ("/trades", None),
        ("/trades/positions", None),
        ("/strategies", None),
        ("/aimee/snapshot", None),
        ("/reviews/operator-summary", None),
        ("/reviews/daily", None),
        ("/reviews/strategies/mean_reversion", None),
        ("/reviews/runtime-health", None),
        ("/reviews/trades/{trade_id}/postmortem", None),
        ("/reviews/history", None),
        ("/reviews/history/{review_id}", None),
        ("/historical-data/providers", None),
        ("/historical-data/datasets", None),
        ("/backtests", None),
    ],
)
def test_audit_test_001_passive_get_routes_do_not_write_state(
    session, client_factory, path_template, query_params
):
    seeded = _seed_http_read_state(session)
    before = _snapshot_rows(session)
    path = path_template.format(**seeded)

    with client_factory(testing_routes_enabled=True) as client:
        response = client.get(path, params=query_params)

    if path == "/health":
        assert response.status_code in {200, 503}, response.text
    else:
        assert response.status_code == 200, response.text
    assert _snapshot_rows(session) == before


@pytest.mark.parametrize(
    "path",
    [
        "/reviews/operator-summary?persist=true",
        "/reviews/daily?persist=true&date=2026-04-10",
        "/reviews/strategies/mean_reversion?persist=true",
        "/reviews/runtime-health?persist=true",
    ],
)
def test_audit_test_001_review_active_reads_require_operator_auth(client_factory, path):
    with client_factory(
        app_env="production", operator_api_token="expected-token"
    ) as client:
        response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Operator authentication is required."}


def test_audit_test_001_trade_postmortem_persist_requires_operator_auth(
    session, client_factory
):
    seeded = _seed_http_read_state(session)

    with client_factory(
        app_env="production", operator_api_token="expected-token"
    ) as client:
        response = client.get(
            f"/reviews/trades/{seeded['trade_id']}/postmortem",
            params={"persist": "true"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Operator authentication is required."}


def test_audit_test_001_review_active_read_persist_true_writes_review_history(
    session, client_factory
):
    _seed_http_read_state(session)
    before_count = len(session.exec(select(GeneratedReviewRecord)).all())

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.get(
            "/reviews/operator-summary",
            params={"persist": "true"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200, response.text
    records = session.exec(
        select(GeneratedReviewRecord).order_by(GeneratedReviewRecord.id)
    ).all()
    assert len(records) == before_count + 1
    assert records[-1].review_type == "operator_summary"


def test_audit_test_001_allocation_alert_refresh_true_requires_operator_auth(
    client_factory,
):
    with client_factory(
        app_env="production", operator_api_token="expected-token"
    ) as client:
        response = client.get("/allocation/alerts", params={"refresh": "true"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Operator authentication is required."}


def test_audit_test_001_allocation_alert_refresh_true_is_documented_write_on_read(
    session, client_factory, monkeypatch
):
    before = _snapshot_rows(session)

    def create_refreshed_alert(self, *, window_minutes=None):
        alert = AllocationAlert(
            alert_key=f"refreshed-{window_minutes}",
            alert_type="material_execution_drift",
            severity="warning",
            state="OPEN",
            escalation_level="warning",
            title="Refreshed allocation alert",
            message="Alert was refreshed by active read.",
            count=1,
            details={"window_minutes": window_minutes},
        )
        self.session.add(alert)
        self.session.commit()
        self.session.refresh(alert)
        return [alert]

    monkeypatch.setattr(
        AllocationAlertService,
        "refresh_alerts",
        create_refreshed_alert,
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.get(
            "/allocation/alerts",
            params={"refresh": "true", "window_minutes": 240},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200, response.text
    after = _snapshot_rows(session)
    assert after != before
    alerts = session.exec(select(AllocationAlert)).all()
    assert len(alerts) == 1
    assert alerts[0].alert_key == "refreshed-240"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("PUT", "/control-plane/operator-state", {"autonomous_control_enabled": False}),
        ("POST", "/reviews/questions", {"question": "What needs attention?"}),
        ("POST", "/testing/reset-history", None),
    ],
)
def test_audit_test_001_mutation_routes_reject_missing_operator_token(
    session, client_factory, method, path, payload
):
    _seed_http_read_state(session)

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
        testing_routes_enabled=True,
    ) as client:
        response = client.request(method, path, json=payload)

    if path == "/testing/reset-history":
        assert response.status_code == 404
    else:
        assert response.status_code == 401
        assert response.json() == {"detail": "Operator authentication is required."}


def test_audit_test_001_mutation_routes_reject_invalid_operator_token(
    session, client_factory
):
    _seed_http_read_state(session)

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.put(
            "/control-plane/operator-state",
            json={"autonomous_control_enabled": False},
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Operator authentication failed."}


def test_audit_test_001_mutation_routes_require_configured_token_in_production(
    client_factory,
):
    with client_factory(app_env="production", operator_api_token=None) as client:
        response = client.put(
            "/control-plane/operator-state",
            json={"autonomous_control_enabled": False},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Operator authentication is not configured."}


def test_audit_api_004_testing_reset_history_route_not_registered_when_disabled(
    session, client_factory, fixed_now
):
    session.add(
        DomainEvent(
            created_at=fixed_now,
            event_type="execution.position_closed",
            category="execution",
            severity="info",
            source="tests.http_harness",
            title="Position closed",
        )
    )
    session.commit()

    with client_factory(testing_routes_enabled=False) as client:
        response = client.post("/testing/reset-history")

    assert response.status_code == 404
    assert len(session.exec(select(DomainEvent)).all()) == 1


def test_audit_api_004_testing_reset_history_route_resets_history_when_enabled(
    session, client_factory, fixed_now
):
    session.add(
        DomainEvent(
            created_at=fixed_now,
            event_type="execution.position_closed",
            category="execution",
            severity="info",
            source="tests.http_harness",
            title="Position closed",
        )
    )
    session.commit()

    with client_factory(testing_routes_enabled=True) as client:
        response = client.post("/testing/reset-history")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert response.json()["summary"]["domain_events_deleted"] == 1
    assert session.exec(select(DomainEvent)).all() == []


def test_testing_reset_history_route_not_registered_in_production_like_posture(
    client_factory,
):
    with client_factory(
        app_env="demo",
        testing_routes_enabled=True,
    ) as client:
        response = client.post("/testing/reset-history")

    assert response.status_code == 404


def test_testing_reset_history_route_not_registered_when_dealing_enabled(
    client_factory,
):
    with client_factory(
        testing_routes_enabled=True,
        ig_trading_enabled=True,
    ) as client:
        response = client.post("/testing/reset-history")

    assert response.status_code == 404


def test_audit_test_016_operator_control_http_error_preserves_mutation_state(
    session, client_factory, monkeypatch
):
    _seed_http_read_state(session)
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.put(
            "/control-plane/operator-state",
            json={
                "autonomous_control_enabled": False,
                "reason": "maintenance window",
            },
            headers=AUTH_HEADER,
        )

    state = session.exec(select(OperatorControlState)).one()
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Operator control was updated, but durable audit persistence failed."
    }
    assert state.autonomous_control_override is False
    assert state.override_reason == "maintenance window"
    assert len(session.exec(select(DomainEvent)).all()) == 1


def test_audit_test_016_review_active_read_http_error_preserves_persisted_record(
    session, client_factory, monkeypatch
):
    _seed_http_read_state(session)
    before_count = len(session.exec(select(GeneratedReviewRecord)).all())
    before_event_count = len(session.exec(select(DomainEvent)).all())
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.get(
            "/reviews/operator-summary",
            params={"persist": "true"},
            headers=AUTH_HEADER,
        )

    records = session.exec(select(GeneratedReviewRecord)).all()
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Review was persisted, but durable audit persistence failed."
    }
    assert len(records) == before_count + 1
    assert len(session.exec(select(DomainEvent)).all()) == before_event_count


def test_audit_test_016_allocation_alert_http_error_preserves_alert_transition(
    session, client_factory, monkeypatch
):
    seeded = _seed_http_read_state(session)
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            f"/allocation/alerts/{seeded['alert_id']}/acknowledge",
            json={"actor_id": "risk-operator"},
            headers=AUTH_HEADER,
        )

    alert = session.exec(select(AllocationAlert)).one()
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Allocation alert was acknowledged, but durable audit persistence failed."
    }
    assert alert.state == "ACKNOWLEDGED"
    assert alert.acknowledged_by == "operator"
