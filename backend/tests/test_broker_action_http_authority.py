from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import select

from app.core.broker import (
    BrokerOrderResult,
    BrokerOrderStatus,
    OrderDirection,
)
from app.core.runtime import runtime_manager
from app.models.domain_event import DomainEvent
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position, TradeIntent
from app.services.health_service import get_health_service
from app.services.market_status_service import MarketStatus
from app.services.regime_suitability_service import (
    DeploymentCandidate,
    RegimeSuitabilityService,
)
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.strategy_service import StrategyService
from app.services.domain_event_service import domain_event_service
from tests.fakes import make_order_result


AUTH_HEADER = {"Authorization": "Bearer expected-token"}
INSTRUMENT = "CS.D.EURUSD.MINI.IP"
STRATEGY = "smoke_test_hold"
ROUTE_STARTUP_PATHS = (
    "backend/app/api/routes/strategies.py",
    "backend/app/api/routes/control_plane.py",
)
APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _runtime(session, *, strategy_name: str = STRATEGY, instrument: str = INSTRUMENT):
    return session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == strategy_name)
        .where(StrategyRuntimeState.instrument == instrument)
    ).one()


def _latest_execution(session) -> Execution:
    return session.exec(select(Execution).order_by(Execution.id.desc())).first()


def _latest_intent(session) -> TradeIntent:
    return session.exec(select(TradeIntent).order_by(TradeIntent.id.desc())).first()


def _enable_live_operational_context(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now, stream_connected=True)
    stub = type(
        "StreamService",
        (),
        {
            "get_health": lambda self: type(
                "Health",
                (),
                {
                    "enabled": True,
                    "connected": True,
                    "subscribed_instruments": (),
                    "desired_instruments": (),
                    "last_tick_at": now,
                },
            )(),
            "get_last_tick_at": lambda self, instrument: now,
        },
    )()
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stub,
    )


def _force_deployable_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = DeploymentCandidate(
        instrument=INSTRUMENT,
        asset_class="FOREX",
        score=0.95,
        market_status=MarketStatus(
            instrument=INSTRUMENT,
            is_ok=True,
            market_open=True,
            tradable=True,
            quote_fresh=True,
            spread_ok=True,
            session_valid=True,
            dealing_allowed=True,
            last_price_age_ms=0.0,
            spread=0.5,
            reason=None,
        ),
        reason="Instrument cleared suitability checks.",
    )
    monkeypatch.setattr(
        RegimeSuitabilityService,
        "select_best_candidate",
        lambda self, **_: candidate,
    )


def _assert_runtime_authority(execution: Execution, expected_route_source: str) -> None:
    runtime_authority = (execution.details or {}).get("runtime_authority") or {}
    assert runtime_authority["authority_kind"] == "http_route"
    assert runtime_authority["route_source"] == expected_route_source
    assert runtime_authority["route_path"]
    assert runtime_authority["actor_type"] == "operator"
    assert runtime_authority["actor_id"] == "operator"
    assert runtime_authority["correlation_id"]


def _route_file(path: str) -> Path:
    return Path(__file__).resolve().parents[1] / Path(path).relative_to("backend")


def _call_names(path: str) -> set[str]:
    tree = ast.parse(_route_file(path).read_text())
    names: set[str] = set()

    def flatten(expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            prefix = flatten(expr.value)
            return f"{prefix}.{expr.attr}" if prefix else expr.attr
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = flatten(node.func)
            if name is not None:
                names.add(name)
    return names


def _app_call_sites(call_name: str) -> set[str]:
    matches: set[str] = set()

    def flatten(expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            prefix = flatten(expr.value)
            return f"{prefix}.{expr.attr}" if prefix else expr.attr
        return None

    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and flatten(node.func) == call_name:
                matches.add(path.relative_to(APP_ROOT.parent).as_posix())
                break
    return matches


def test_audit_api_008_strategy_start_http_route_reachable_entry_preserves_authority_and_audit(
    client_factory, session, broker, fixed_now, monkeypatch
):
    _enable_live_operational_context(monkeypatch)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-route-authority-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            "/strategy/start",
            headers={**AUTH_HEADER, "X-Request-ID": "route-start-entry-1"},
            json={"strategy_name": STRATEGY, "instrument": INSTRUMENT},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "started"

    service = StrategyService(session)
    service.process_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        INSTRUMENT,
        100.5,
        bid=100.49,
        ask=100.51,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    runtime = _runtime(session)
    execution = _latest_execution(session)
    events = _events(session)
    operator_started = next(
        event for event in events if event.event_type == "operator.runtime_started"
    )
    position_opened = next(
        event for event in events if event.event_type == "execution.position_opened"
    )

    assert broker.placed_orders
    assert execution.client_request_id == broker.placed_orders[0].client_request_id
    assert runtime.startup_context["route_source"] == "api.strategy.start"
    assert runtime.startup_context["correlation_id"] == "route-start-entry-1"
    assert operator_started.actor_id == "operator"
    assert operator_started.correlation_id == "route-start-entry-1"
    assert operator_started.runtime_id == runtime.runtime_id
    assert operator_started.payload_json["startup_context"] == runtime.startup_context
    _assert_runtime_authority(execution, "api.strategy.start")
    assert position_opened.execution_id == execution.id
    assert position_opened.position_id == execution.local_position_id
    assert position_opened.payload_json["trade_intent_id"] == execution.trade_intent_id
    assert position_opened.payload_json["previous_state"] == "FILL_FULL"
    assert position_opened.payload_json["new_state"] == "POSITION_OPENED"
    assert position_opened.payload_json["broker_reference"].startswith(
        "[REDACTED_BROKER_REF:"
    )
    assert (
        position_opened.payload_json["details"]["runtime_authority"]
        == runtime.startup_context
    )


def test_audit_api_008_strategy_start_by_name_route_reachable_close_preserves_manual_review(
    client_factory, session, broker, fixed_now, monkeypatch
):
    _enable_live_operational_context(monkeypatch)
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-route-close-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )
    broker.close_position_outcomes.append(
        BrokerOrderResult(
            broker_reference="close-route-manual-review-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=101.0,
            executed_at=fixed_now + timedelta(seconds=40),
            status=BrokerOrderStatus.AMBIGUOUS,
            submitted_at=fixed_now + timedelta(seconds=40),
            acknowledged_at=fixed_now + timedelta(seconds=40),
            reason="Close confirmation is ambiguous.",
            requires_manual_review=True,
        )
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            f"/strategies/{STRATEGY}/start",
            headers={**AUTH_HEADER, "X-Request-ID": "route-start-close-1"},
        )

    assert response.status_code == 200

    service = StrategyService(session)
    service.process_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        INSTRUMENT,
        100.5,
        bid=100.49,
        ask=100.51,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )
    service.process_price_update(
        INSTRUMENT,
        101.0,
        bid=100.99,
        ask=101.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=40),
    )

    runtime = _runtime(session)
    execution = _latest_execution(session)
    intent = _latest_intent(session)
    events = _events(session)
    manual_review_event = [
        event for event in events if event.event_type == "execution.order_rejected"
    ][-1]

    assert broker.close_requests == [
        {
            "instrument": INSTRUMENT,
            "broker_reference": "entry-route-close-1",
            "client_request_id": execution.client_request_id,
        }
    ]
    assert execution.status == "NEEDS_MANUAL_REVIEW"
    assert execution.requires_manual_review is True
    assert execution.broker_reference == "close-route-manual-review-1"
    assert intent.state == "CLOSE_REQUESTED"
    assert len(session.exec(select(Position)).all()) == 1
    _assert_runtime_authority(execution, "api.strategies.start_by_name")
    assert manual_review_event.execution_id == execution.id
    assert manual_review_event.position_id == execution.local_position_id
    assert manual_review_event.payload_json["trade_intent_id"] == intent.id
    assert manual_review_event.payload_json["broker_reference"].startswith(
        "[REDACTED_BROKER_REF:"
    )
    assert manual_review_event.payload_json["requires_manual_review"] is True
    assert (
        manual_review_event.payload_json["details"]["runtime_authority"]
        == runtime.startup_context
    )


def test_audit_test_002_control_plane_reconcile_http_route_reachable_entry_preserves_runtime_authority(
    client_factory, session, broker, fixed_now, monkeypatch
):
    _enable_live_operational_context(monkeypatch)
    _force_deployable_candidate(monkeypatch)
    StrategyGovernanceService(session).ensure_defaults()
    StrategyGovernanceService(session).upsert_strategy(
        strategy_name=STRATEGY,
        approval_state="APPROVED",
        autonomous_operation_allowed=True,
        approved_asset_classes=["FOREX"],
        approved_instruments=[INSTRUMENT],
        approved_profile_names=["default"],
    )
    broker.place_order_outcomes.append(
        make_order_result(
            broker_reference="entry-reconcile-authority-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
        )
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            "/control-plane/reconcile",
            headers={**AUTH_HEADER, "X-Request-ID": "route-reconcile-entry-1"},
        )

    assert response.status_code == 200
    assert response.json()["deployed"] >= 1

    service = StrategyService(session)
    service.process_price_update(
        INSTRUMENT,
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        INSTRUMENT,
        100.5,
        bid=100.49,
        ask=100.51,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    runtime = _runtime(session)
    execution = _latest_execution(session)
    events = _events(session)
    reconciled = next(
        event for event in events if event.event_type == "control_plane.reconciled"
    )

    assert runtime.control_mode == "AUTO"
    assert runtime.startup_context["route_source"] == "api.control_plane.reconcile"
    assert runtime.startup_context["correlation_id"] == "route-reconcile-entry-1"
    assert broker.placed_orders
    _assert_runtime_authority(execution, "api.control_plane.reconcile")
    assert reconciled.actor_id == "operator"
    assert reconciled.correlation_id == "route-reconcile-entry-1"
    assert (
        reconciled.payload_json["startup_context"]["route_source"]
        == "api.control_plane.reconcile"
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/strategy/start", {"strategy_name": STRATEGY, "instrument": INSTRUMENT}),
        ("/control-plane/reconcile", None),
    ],
)
def test_audit_api_008_unauthorized_scheduler_routes_cannot_reach_broker_mutations(
    client_factory, session, broker, monkeypatch, path, body
):
    _enable_live_operational_context(monkeypatch)

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Operator authentication is required."}
    assert broker.placed_orders == []
    assert broker.close_requests == []
    assert runtime_manager.get_engine(STRATEGY, INSTRUMENT) is None
    assert session.exec(select(StrategyRuntimeState)).all() == []


def test_audit_api_008_disabled_reconcile_route_cannot_schedule_broker_action_runtime(
    client_factory, session, broker, monkeypatch
):
    _enable_live_operational_context(monkeypatch)
    _force_deployable_candidate(monkeypatch)
    StrategyGovernanceService(session).ensure_defaults()
    StrategyGovernanceService(session).upsert_strategy(
        strategy_name=STRATEGY,
        approval_state="DISABLED",
        autonomous_operation_allowed=False,
        approved_asset_classes=["FOREX"],
        approved_instruments=[INSTRUMENT],
        approved_profile_names=["default"],
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            "/control-plane/reconcile",
            headers={**AUTH_HEADER, "X-Request-ID": "route-reconcile-disabled-1"},
        )

    assert response.status_code == 200
    assert broker.placed_orders == []
    assert runtime_manager.get_engine(STRATEGY, INSTRUMENT) is None
    assert (
        session.exec(
            select(StrategyRuntimeState).where(
                StrategyRuntimeState.strategy_name == STRATEGY
            )
        ).all()
        == []
    )


@pytest.mark.parametrize(
    ("path", "body", "failed_event_type"),
    [
        (
            "/strategy/start",
            {"strategy_name": STRATEGY, "instrument": INSTRUMENT},
            "operator.runtime_started",
        ),
        ("/control-plane/reconcile", None, "control_plane.reconciled"),
    ],
)
def test_audit_api_008_scheduler_route_audit_write_failure_is_not_clean_success(
    client_factory,
    session,
    monkeypatch,
    path,
    body,
    failed_event_type,
):
    original_record_event_in_session = domain_event_service.record_event_in_session

    def fail_selected_route_event(**kwargs):
        if kwargs.get("event_type") == failed_event_type:
            return None
        return original_record_event_in_session(**kwargs)

    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        fail_selected_route_event,
        raising=False,
    )
    _enable_live_operational_context(monkeypatch)
    if path == "/control-plane/reconcile":
        _force_deployable_candidate(monkeypatch)
        StrategyGovernanceService(session).ensure_defaults()
        StrategyGovernanceService(session).upsert_strategy(
            strategy_name=STRATEGY,
            approval_state="APPROVED",
            autonomous_operation_allowed=True,
            approved_asset_classes=["FOREX"],
            approved_instruments=[INSTRUMENT],
            approved_profile_names=["default"],
        )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            path,
            headers={**AUTH_HEADER, "X-Request-ID": "route-audit-failure-1"},
            json=body,
        )

    assert response.status_code == 503
    assert "durable audit persistence failed" in response.json()["detail"]


def test_audit_api_008_scheduler_routes_do_not_call_broker_mutations_directly():
    strategy_calls = _call_names(ROUTE_STARTUP_PATHS[0])
    control_plane_calls = _call_names(ROUTE_STARTUP_PATHS[1])

    assert any(call.endswith(".start_strategy") for call in strategy_calls)
    assert any("reconcile" in call for call in control_plane_calls)
    assert "runtime_manager.start" not in strategy_calls | control_plane_calls
    assert (
        "runtime_manager.process_price_update"
        not in strategy_calls | control_plane_calls
    )
    assert not any(
        call.endswith(".place_order") or call.endswith(".close_position")
        for call in strategy_calls | control_plane_calls
    )


def test_audit_test_002_broker_mutation_and_runtime_start_call_graph_is_constrained():
    assert _app_call_sites("engine.broker.place_order") == {
        "app/services/strategy_service.py"
    }
    assert _app_call_sites("engine.broker.close_position") == {
        "app/services/strategy_service.py"
    }
    assert _app_call_sites("runtime_manager.start") == {
        "app/services/runtime_recovery_service.py",
        "app/services/strategy_service.py",
    }
