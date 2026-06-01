from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.core.broker import BrokerOrderResult, BrokerOrderStatus, OrderDirection
from app.core.runtime import runtime_manager
from app.models.domain_event import DomainEvent
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import Execution, Position, TradeIntent, TradeIntentState
from app.services.audit_event_recorder import AuditEventPersistenceError
from app.services.control_plane_service import ControlPlaneService
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.operator_control_service import OperatorControlService
from app.services.market_status_service import MarketStatus
from app.services.operational_state_service import (
    BrokerConnectivityState,
    ExecutionEligibilityState,
    FeedHealthState,
    FeedSourceState,
    OpenRiskManagementState,
    OperationalStateSnapshot,
)
from app.services.operational_telemetry_service import OperationalTelemetryService
from app.services.regime_suitability_service import DeploymentCandidate
from app.services.strategy_deployment_manager_service import (
    StrategyDeploymentManagerService,
)
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.strategy_service import StrategyService


def _domain_events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


def _force_deployable_candidate(
    manager: StrategyDeploymentManagerService, *, instrument: str
) -> None:
    manager.suitability_service.select_best_candidate = lambda **_: DeploymentCandidate(
        instrument=instrument,
        asset_class="INDICES",
        score=0.95,
        market_status=MarketStatus(
            instrument=instrument,
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


def _enable_live_exit_context(monkeypatch, at: datetime) -> None:
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
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


def _attach_open_position(
    session,
    *,
    strategy_name: str,
    instrument: str,
    at: datetime,
    broker_reference: str = "pos-open-1",
) -> Position:
    now = datetime.now(UTC)
    intent = TradeIntent(
        strategy_name=strategy_name,
        instrument=instrument,
        direction="BUY",
        state=TradeIntentState.POSITION_OPENED.value,
        signal_time=at,
        proposed_size=0.2,
        allocated_size=0.2,
        proposed_risk_percent=0.1,
        allocated_risk_percent=0.1,
        broker_reference=broker_reference,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    position = Position(
        trade_intent_id=intent.id,
        strategy_name=strategy_name,
        instrument=instrument,
        broker_reference=broker_reference,
        direction="BUY",
        size=0.2,
        open_price=100.0,
        current_price=101.0,
        unrealized_pnl=0.2,
        open_time=at,
        risk_percent=0.1,
        account_type="DEMO",
        is_open=True,
        broker_sync_status="CONFIRMED",
    )
    session.add(position)
    session.commit()
    session.refresh(position)
    engine = runtime_manager.get_engine(strategy_name, instrument)
    if engine is not None:
        engine.current_position = position
    runtime_manager.load_cached_price(
        instrument, price=position.current_price or position.open_price, updated_at=now
    )
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == strategy_name,
            StrategyRuntimeState.instrument == instrument,
        )
    ).first()
    if runtime is not None:
        runtime.current_position_broker_reference = broker_reference
        runtime.last_price_seen = position.current_price
        runtime.last_price_seen_at = now
        session.add(runtime)
        session.commit()
    return position


def test_governance_service_seeds_governance_defaults_explicitly(session):
    StrategyGovernanceService(session).ensure_defaults()
    summary = ControlPlaneService(session).get_summary()

    assert summary["families"]
    families_by_name = {item["strategy_name"]: item for item in summary["families"]}
    assert (
        families_by_name["mean_reversion"]["governance"]["approval_state"] == "APPROVED"
    )
    assert (
        families_by_name["mean_reversion"]["governance"]["autonomous_operation_allowed"]
        is True
    )
    assert (
        "default"
        in families_by_name["mean_reversion"]["governance"]["available_profile_names"]
    )
    assert (
        "fast"
        in families_by_name["mean_reversion"]["governance"]["available_profile_names"]
    )


def test_control_plane_reports_effective_autonomy_override(session):
    OperatorControlService(session).update_autonomous_control(
        enabled=False,
        reason="operator paused governed autonomy",
    )

    summary = ControlPlaneService(session).get_summary()

    assert summary["configured_autonomous_control_enabled"] is True
    assert summary["effective_autonomous_control_enabled"] is False
    assert summary["autonomy_override_active"] is True
    assert summary["autonomy_override_reason"] == "operator paused governed autonomy"


def test_control_plane_summary_exposes_operational_truth_fields(session, monkeypatch):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.record_price_update(now)
    stub = type(
        "StreamService",
        (),
        {
            "get_health": lambda self: type(
                "Health",
                (),
                {
                    "enabled": True,
                    "connected": False,
                    "subscribed_instruments": (),
                    "desired_instruments": (),
                    "last_tick_at": now - timedelta(seconds=30),
                },
            )(),
            "get_last_tick_at": lambda self, instrument: now - timedelta(seconds=30),
        },
    )()
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stub,
    )

    summary = ControlPlaneService(session).get_summary()

    assert summary["feed_source_state"] == "POLLING_FALLBACK"
    assert summary["feed_health_state"] == "DEGRADED"
    assert summary["broker_connectivity_state"] == "CONNECTED"
    assert summary["entry_eligible"] is False
    assert summary["exit_eligible"] is True
    assert summary["entry_block_reason"] == "polling_fallback_active"


def test_governance_service_upgrades_legacy_default_false_to_allowed(
    session, fixed_now
):
    governance_service = StrategyGovernanceService(session)
    legacy = StrategyFamilyGovernance(
        strategy_name="mean_reversion",
        approval_state="APPROVED",
        autonomous_operation_allowed=False,
        approved_asset_classes=[],
        approved_instruments=[],
        approved_profile_names=[],
        max_concurrent_deployments=1,
        created_at=fixed_now,
        updated_at=fixed_now,
    )
    session.add(legacy)
    session.commit()

    record = governance_service.get_strategy("mean_reversion")
    assert record is not None
    assert record.autonomous_operation_allowed is False

    governance_service.ensure_defaults()
    promoted = governance_service.get_strategy("mean_reversion")

    assert promoted is not None
    assert promoted.autonomous_operation_allowed is True


def test_reconcile_auto_deploys_approved_autonomous_strategy(
    session, broker, fixed_now
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["fast"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")

    result = manager.reconcile(now=fixed_now)

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()

    assert result.deployed >= 1
    assert deployment.state == "AUTO_DEPLOYED"
    assert deployment.selected_instrument == "IX.D.FTSE.DAILY.IP"
    assert deployment.selected_profile == "fast"
    assert deployment.selected_profile_parameters["window_size"] == 12
    assert runtime.status == "RUNNING"
    assert runtime.control_mode == "AUTO"
    assert runtime.deployment_id == deployment.id
    assert runtime.active_profile_name == "fast"
    assert runtime.parameters["window_size"] == 12
    assert (
        runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is not None
    )
    engine = runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP")
    assert engine is not None
    assert engine.active_profile_name == "fast"
    assert engine.strategy_parameters["window_size"] == 12
    assert getattr(engine.strategy, "window_size") == 12

    strategy_summary = next(
        strategy
        for strategy in StrategyService(session).list_strategies()
        if strategy["name"] == "mean_reversion"
    )
    assert strategy_summary["deployment_profile"] == "fast"
    assert strategy_summary["deployment_parameters"]["window_size"] == 12
    assert (
        next(
            parameter
            for parameter in strategy_summary["parameters"]
            if parameter["key"] == "window_size"
        )["value"]
        == 12
    )
    control_plane_family = ControlPlaneService(session).get_family_detail(
        "mean_reversion"
    )
    assert control_plane_family["deployment"]["selected_profile"] == "fast"
    assert control_plane_family["runtime"]["active_profile_name"] == "fast"
    assert control_plane_family["alignment"]["is_aligned"] is True


def test_audit_test_002_deployment_reconcile_persists_session_bound_domain_events(
    session, broker, fixed_now
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["fast"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")

    manager.reconcile(now=fixed_now)

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    events = _domain_events(session)
    mean_reversion_events = [
        event
        for event in events
        if event.strategy_name == "mean_reversion"
        and event.event_type
        in {
            "strategy.runtime_started",
            "strategy.runtime_mode_changed",
            "control_plane.runtime_restarted",
            "control_plane.deployment_state_changed",
        }
    ]
    assert [event.event_type for event in mean_reversion_events] == [
        "strategy.runtime_started",
        "strategy.runtime_mode_changed",
        "control_plane.runtime_restarted",
        "control_plane.deployment_state_changed",
    ]
    assert mean_reversion_events[0].runtime_id == runtime.runtime_id
    assert mean_reversion_events[0].actor_type == "service"
    assert mean_reversion_events[0].actor_id == "strategy_service"
    assert mean_reversion_events[0].payload_json["previous_state"] == "NOT_RUNNING"
    assert mean_reversion_events[0].payload_json["new_state"] == "RUNNING"
    assert mean_reversion_events[1].payload_json["previous_runtime_mode"] == "NORMAL"
    assert mean_reversion_events[1].payload_json["new_runtime_mode"] == "NORMAL"
    assert mean_reversion_events[2].source == "strategy_deployment_manager.reconcile"
    assert mean_reversion_events[2].strategy_name == "mean_reversion"
    assert mean_reversion_events[2].instrument == "IX.D.FTSE.DAILY.IP"
    assert mean_reversion_events[2].correlation_id is not None
    assert mean_reversion_events[2].payload_json["deployment_id"] == deployment.id
    assert mean_reversion_events[2].payload_json["reason"] == (
        "Runtime started with profile fast."
    )
    assert (
        mean_reversion_events[2].payload_json["startup_context"]["authority_kind"]
        == "deployment_reconcile"
    )
    assert mean_reversion_events[3].payload_json["previous_state"] == "NOT_APPROVED"
    assert mean_reversion_events[3].payload_json["new_state"] == "AUTO_DEPLOYED"
    assert mean_reversion_events[3].payload_json["deployment_id"] == deployment.id
    assert (
        mean_reversion_events[3].correlation_id
        == mean_reversion_events[2].correlation_id
    )


def test_audit_test_002_background_reconcile_preserves_authority_for_later_entry(
    session, broker, fixed_now, monkeypatch
):
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="smoke_test_hold",
        autonomous_operation_allowed=True,
        approved_asset_classes=["FOREX"],
        approved_instruments=["CS.D.EURUSD.MINI.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="CS.D.EURUSD.MINI.IP")
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="background-reconcile-entry-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
            status=BrokerOrderStatus.FILLED,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
        )
    )

    manager.reconcile(now=fixed_now)

    service = StrategyService(session)
    service.process_price_update(
        "CS.D.EURUSD.MINI.IP",
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        "CS.D.EURUSD.MINI.IP",
        100.5,
        bid=100.49,
        ask=100.51,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "smoke_test_hold",
            StrategyRuntimeState.instrument == "CS.D.EURUSD.MINI.IP",
        )
    ).one()
    execution = session.exec(select(Execution).order_by(Execution.id.desc())).first()
    events = _domain_events(session)
    runtime_started = next(
        event
        for event in events
        if event.event_type == "strategy.runtime_started"
        and event.strategy_name == "smoke_test_hold"
    )
    restarted = next(
        event
        for event in events
        if event.event_type == "control_plane.runtime_restarted"
        and event.strategy_name == "smoke_test_hold"
    )
    position_opened = next(
        event
        for event in events
        if event.event_type == "execution.position_opened"
        and event.strategy_name == "smoke_test_hold"
    )

    assert runtime.startup_context["authority_kind"] == "deployment_reconcile"
    assert runtime.startup_context["authority_source"] == (
        "strategy_deployment_manager.reconcile"
    )
    assert runtime.startup_context["actor_type"] == "service"
    assert runtime.startup_context["actor_id"] == "strategy_deployment_manager"
    assert runtime.startup_context["correlation_id"].startswith("deployment-reconcile:")
    assert broker.placed_orders
    assert broker.placed_orders[0].client_request_id == execution.client_request_id
    assert execution.details["runtime_authority"]["authority_kind"] == (
        "deployment_reconcile"
    )
    assert execution.details["runtime_authority"]["authority_source"] == (
        "strategy_deployment_manager.reconcile"
    )
    assert execution.details["runtime_authority"]["actor_type"] == "service"
    assert execution.details["runtime_authority"]["actor_id"] == (
        "strategy_deployment_manager"
    )
    assert execution.details["runtime_authority"]["correlation_id"].startswith(
        "[REDACTED_CORRELATION_ID:"
    )
    assert runtime_started.correlation_id == runtime.startup_context["correlation_id"]
    assert runtime_started.payload_json["startup_context"]["authority_kind"] == (
        "deployment_reconcile"
    )
    assert runtime_started.payload_json["startup_context"]["authority_source"] == (
        "strategy_deployment_manager.reconcile"
    )
    assert runtime_started.payload_json["startup_context"]["actor_type"] == "service"
    assert runtime_started.payload_json["startup_context"]["actor_id"] == (
        "strategy_deployment_manager"
    )
    assert runtime_started.payload_json["startup_context"]["correlation_id"].startswith(
        "[REDACTED_CORRELATION_ID:"
    )
    assert restarted.correlation_id == runtime.startup_context["correlation_id"]
    assert restarted.payload_json["startup_context"]["authority_kind"] == (
        "deployment_reconcile"
    )
    assert restarted.payload_json["startup_context"]["authority_source"] == (
        "strategy_deployment_manager.reconcile"
    )
    assert restarted.payload_json["startup_context"]["actor_type"] == "service"
    assert restarted.payload_json["startup_context"]["actor_id"] == (
        "strategy_deployment_manager"
    )
    assert restarted.payload_json["startup_context"]["correlation_id"].startswith(
        "[REDACTED_CORRELATION_ID:"
    )
    assert position_opened.correlation_id == execution.client_request_id
    assert position_opened.execution_id == execution.id
    assert position_opened.position_id == execution.local_position_id
    assert (
        position_opened.payload_json["details"]["runtime_authority"]["authority_kind"]
        == "deployment_reconcile"
    )
    assert (
        position_opened.payload_json["details"]["runtime_authority"]["authority_source"]
        == "strategy_deployment_manager.reconcile"
    )
    assert (
        position_opened.payload_json["details"]["runtime_authority"]["actor_type"]
        == "service"
    )
    assert (
        position_opened.payload_json["details"]["runtime_authority"]["actor_id"]
        == "strategy_deployment_manager"
    )
    assert position_opened.payload_json["details"]["runtime_authority"][
        "correlation_id"
    ].startswith("[REDACTED_CORRELATION_ID:")


def test_reconcile_emergency_stop_blocks_and_stops_auto_runtime(
    session, broker, fixed_now
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)

    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        emergency_stop=True,
    )
    result = manager.reconcile(now=fixed_now.replace(tzinfo=UTC))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()

    assert result.emergency_stopped >= 1
    assert deployment.state == "EMERGENCY_STOPPED"
    assert deployment.open_risk_management_state == "NO_OPEN_RISK"
    assert runtime.status == "STOPPED"
    assert runtime.runtime_mode == "STOPPED"
    assert runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is None


def test_profile_change_restarts_autonomous_runtime_with_new_parameters(
    session, broker, fixed_now
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)

    first_runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    first_runtime_id = first_runtime.runtime_id
    assert first_runtime.active_profile_name == "default"
    assert first_runtime.parameters["window_size"] == 20

    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        approved_profile_names=["fast"],
    )
    manager.reconcile(now=fixed_now.replace(tzinfo=UTC))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtimes = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).all()
    active_runtime = next(
        runtime for runtime in runtimes if runtime.status == "RUNNING"
    )

    assert deployment.selected_profile == "fast"
    assert deployment.profile_change_reason is not None
    assert deployment.last_restart_reason is not None
    assert active_runtime.runtime_id != first_runtime_id
    assert active_runtime.active_profile_name == "fast"
    assert active_runtime.parameters["window_size"] == 12
    engine = runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP")
    assert engine is not None
    assert engine.active_profile_name == "fast"
    assert getattr(engine.strategy, "window_size") == 12


def test_control_plane_reports_runtime_deployment_mismatch(session, broker, fixed_now):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["fast"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)

    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    runtime.active_profile_name = "default"
    runtime.parameters = {
        "window_size": 20,
        "entry_threshold": 0.0015,
        "exit_threshold": 0.0004,
    }
    session.add(runtime)
    session.commit()

    family = ControlPlaneService(session).get_family_detail("mean_reversion")

    assert family["alignment"]["is_aligned"] is False
    assert family["alignment"]["status"] == "MISMATCH"
    assert any(
        check["code"] == "profile_match" and check["passed"] is False
        for check in family["alignment"]["checks"]
    )


def test_reconcile_keeps_open_positions_in_exits_only_when_family_leaves_full_auto(
    session, broker, fixed_now, monkeypatch
):
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    _attach_open_position(
        session,
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        at=fixed_now,
    )

    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    family = ControlPlaneService(session).get_family_detail("mean_reversion")
    telemetry = OperationalTelemetryService(session).get_summary()

    assert deployment.state == "EMERGENCY_STOPPED"
    assert deployment.open_risk_management_state == "EXITS_ONLY"
    assert runtime.status == "RUNNING"
    assert runtime.runtime_mode == "EXITS_ONLY"
    assert (
        runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is not None
    )
    assert (
        runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP").runtime_mode
        == "EXITS_ONLY"
    )
    assert family["runtime"]["runtime_mode"] == "EXITS_ONLY"
    assert family["deployment"]["open_risk_management_state"] == "EXITS_ONLY"
    assert telemetry["open_risk_management_state"] == "EXITS_ONLY"


def test_reconcile_flags_unmanaged_open_risk_when_exits_not_eligible(
    session, broker, fixed_now, monkeypatch
):
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    _attach_open_position(
        session,
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        at=fixed_now,
    )
    blocked_snapshot = OperationalStateSnapshot(
        feed_source_state=FeedSourceState.DISCONNECTED,
        feed_health_state=FeedHealthState.FAILED,
        broker_connectivity_state=BrokerConnectivityState.DISCONNECTED,
        entry_eligible=False,
        exit_eligible=False,
        entry_eligibility_state=ExecutionEligibilityState.BLOCKED,
        exit_eligibility_state=ExecutionEligibilityState.BLOCKED,
        entry_block_reason="broker_disconnected",
        exit_block_reason="broker_disconnected",
        open_risk_management_state=OpenRiskManagementState.UNMANAGED_OPEN_RISK,
        open_risk_management_reason="broker_disconnected",
    )
    manager.operational_state_service.get_summary = lambda: blocked_snapshot
    manager.operational_state_service.get_summary_for_instrument = lambda instrument: (
        blocked_snapshot
    )

    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    summary = ControlPlaneService(session).get_summary()
    family = ControlPlaneService(session).get_family_detail("mean_reversion")
    telemetry = OperationalTelemetryService(session).get_summary()

    assert deployment.state == "EMERGENCY_STOPPED"
    assert deployment.open_risk_management_state == "UNMANAGED_OPEN_RISK"
    assert runtime.status == "STOPPED"
    assert runtime.runtime_mode == "STOPPED"
    assert runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is None
    assert summary["open_risk_management_state"] == "UNMANAGED_OPEN_RISK"
    assert family["deployment"]["open_risk_management_state"] == "UNMANAGED_OPEN_RISK"
    assert telemetry["open_risk_management_state"] == "UNMANAGED_OPEN_RISK"
    assert "open position" in (deployment.open_risk_management_reason or "").lower()


def test_audit_test_002_unmanaged_open_risk_persists_domain_event(
    session, broker, fixed_now, monkeypatch
):
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    _attach_open_position(
        session,
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        at=fixed_now,
    )
    blocked_snapshot = OperationalStateSnapshot(
        feed_source_state=FeedSourceState.DISCONNECTED,
        feed_health_state=FeedHealthState.FAILED,
        broker_connectivity_state=BrokerConnectivityState.DISCONNECTED,
        entry_eligible=False,
        exit_eligible=False,
        entry_eligibility_state=ExecutionEligibilityState.BLOCKED,
        exit_eligibility_state=ExecutionEligibilityState.BLOCKED,
        entry_block_reason="broker_disconnected",
        exit_block_reason="broker_disconnected",
        open_risk_management_state=OpenRiskManagementState.UNMANAGED_OPEN_RISK,
        open_risk_management_reason="broker_disconnected",
    )
    manager.operational_state_service.get_summary = lambda: blocked_snapshot
    manager.operational_state_service.get_summary_for_instrument = lambda instrument: (
        blocked_snapshot
    )

    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    events = _domain_events(session)
    unmanaged_events = [
        event for event in events if event.event_type == "risk.unmanaged_open_risk"
    ]
    assert len(unmanaged_events) == 1
    event = unmanaged_events[0]
    assert event.category == "risk"
    assert event.severity == "error"
    assert event.actor_type == "service"
    assert event.actor_id == "strategy_deployment_manager"
    assert event.strategy_name == "mean_reversion"
    assert event.payload_json["previous_open_risk_management_state"] != (
        "UNMANAGED_OPEN_RISK"
    )
    assert event.payload_json["new_open_risk_management_state"] == (
        "UNMANAGED_OPEN_RISK"
    )
    assert event.payload_json["deployment_state"] == "EMERGENCY_STOPPED"
    assert event.payload_json["exit_block_reason"] == "broker_disconnected"


def test_audit_test_002_background_reconcile_stop_persists_correlation_and_reason(
    session, broker, fixed_now
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)

    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()
    events = _domain_events(session)
    stopped = [
        event
        for event in events
        if event.event_type == "strategy.runtime_stopped"
        and event.strategy_name == "mean_reversion"
    ][-1]
    deployment_changed = [
        event
        for event in events
        if event.event_type == "control_plane.deployment_state_changed"
        and event.strategy_name == "mean_reversion"
    ][-1]

    assert stopped.runtime_id == runtime.runtime_id
    assert stopped.correlation_id == deployment_changed.correlation_id
    assert stopped.payload_json["previous_state"] == "RUNNING"
    assert stopped.payload_json["new_state"] == "STOPPED"
    assert (
        stopped.payload_json["stop_context"]["authority_kind"] == "deployment_reconcile"
    )
    assert stopped.payload_json["reason"] == (
        "Operator emergency stop is active for this strategy family."
    )
    assert stopped.payload_json["new_runtime_mode"] == "STOPPED"
    assert deployment_changed.payload_json["new_state"] == "EMERGENCY_STOPPED"


def test_audit_obs_001_background_reconcile_audit_failure_marks_health_degraded(
    session, broker, fixed_now, monkeypatch
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=2.0)
    health_service.set_stream_connected(True)
    health_service.record_price_update(fixed_now, stream_connected=True)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    original_record_event_in_session = domain_event_service.record_event_in_session

    def fail_runtime_stopped(**kwargs):
        if kwargs.get("event_type") == "strategy.runtime_stopped":
            return None
        return original_record_event_in_session(**kwargs)

    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        fail_runtime_stopped,
        raising=False,
    )

    with pytest.raises(AuditEventPersistenceError, match="strategy.runtime_stopped"):
        manager.reconcile(now=fixed_now + timedelta(minutes=1))

    telemetry = OperationalTelemetryService(session).get_summary()
    report = health_service.get_health_report()
    assert report["status"] == "degraded"
    assert report["details"].audit_write_failures_last_5m == 1
    assert report["details"].last_audit_write_failure is not None
    assert telemetry["audit_write_failures_last_5m"] == 1
    assert telemetry["last_audit_write_failure"] is not None


def test_reconcile_rotation_keeps_old_open_risk_exit_capable(
    session, broker, fixed_now, monkeypatch
):
    now = datetime.now(UTC)
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP", "IX.D.DAX.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    _attach_open_position(
        session,
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        at=fixed_now,
    )
    runtime_manager.load_cached_price("IX.D.FTSE.DAILY.IP", price=100.0, updated_at=now)

    _force_deployable_candidate(manager, instrument="IX.D.DAX.DAILY.IP")
    runtime_manager.load_cached_price("IX.D.DAX.DAILY.IP", price=150.0, updated_at=now)
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtimes = list(
        session.exec(
            select(StrategyRuntimeState).where(
                StrategyRuntimeState.strategy_name == "mean_reversion"
            )
        )
    )
    runtimes_by_instrument = {runtime.instrument: runtime for runtime in runtimes}

    assert deployment.state == "AUTO_DEPLOYED"
    assert deployment.selected_instrument == "IX.D.DAX.DAILY.IP"
    assert deployment.open_risk_management_state == "EXITS_ONLY"
    assert runtimes_by_instrument["IX.D.FTSE.DAILY.IP"].status == "RUNNING"
    assert runtimes_by_instrument["IX.D.FTSE.DAILY.IP"].runtime_mode == "EXITS_ONLY"
    assert runtimes_by_instrument["IX.D.DAX.DAILY.IP"].status == "RUNNING"
    assert runtimes_by_instrument["IX.D.DAX.DAILY.IP"].runtime_mode == "NORMAL"


def test_reconcile_uses_instrument_specific_exit_eligibility(
    session, broker, fixed_now, monkeypatch
):
    now = datetime.now(UTC)
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        autonomous_operation_allowed=True,
        approved_asset_classes=["INDICES"],
        approved_instruments=["IX.D.FTSE.DAILY.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="IX.D.FTSE.DAILY.IP")
    manager.reconcile(now=fixed_now)
    _attach_open_position(
        session,
        strategy_name="mean_reversion",
        instrument="IX.D.FTSE.DAILY.IP",
        at=fixed_now,
    )
    runtime_manager.load_cached_price(
        "IX.D.FTSE.DAILY.IP", price=100.0, updated_at=now - timedelta(seconds=30)
    )

    stale_snapshot = OperationalStateSnapshot(
        feed_source_state=FeedSourceState.STALE,
        feed_health_state=FeedHealthState.DEGRADED,
        broker_connectivity_state=BrokerConnectivityState.CONNECTED,
        entry_eligible=False,
        exit_eligible=False,
        entry_eligibility_state=ExecutionEligibilityState.BLOCKED,
        exit_eligibility_state=ExecutionEligibilityState.BLOCKED,
        entry_block_reason="stale_price_data",
        exit_block_reason="stale_price_data",
        open_risk_management_state=OpenRiskManagementState.UNMANAGED_OPEN_RISK,
        open_risk_management_reason="stale_price_data",
    )
    manager.operational_state_service.get_summary_for_instrument = lambda instrument: (
        stale_snapshot
    )

    governance_service.upsert_strategy(
        strategy_name="mean_reversion", emergency_stop=True
    )
    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    deployment = session.exec(
        select(StrategyDeployment).where(
            StrategyDeployment.strategy_name == "mean_reversion"
        )
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == "mean_reversion"
        )
    ).one()

    assert deployment.open_risk_management_state == "UNMANAGED_OPEN_RISK"
    assert "stale_price_data" in (deployment.open_risk_management_reason or "")
    assert runtime.status == "STOPPED"


def test_reconcile_preserves_selected_runtime_exits_only_after_partial_fill(
    session, broker, fixed_now, monkeypatch
):
    _enable_live_exit_context(monkeypatch, fixed_now)
    governance_service = StrategyGovernanceService(session)
    governance_service.ensure_defaults()
    governance_service.upsert_strategy(
        strategy_name="smoke_test_hold",
        autonomous_operation_allowed=True,
        approved_asset_classes=["FOREX"],
        approved_instruments=["CS.D.EURUSD.MINI.IP"],
        approved_profile_names=["default"],
    )
    manager = StrategyDeploymentManagerService(session)
    manager.settings.autonomous_control_enabled = True
    _force_deployable_candidate(manager, instrument="CS.D.EURUSD.MINI.IP")
    manager.reconcile(now=fixed_now)

    service = StrategyService(session)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="entry-partial-reconcile-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=fixed_now + timedelta(seconds=1),
            status=BrokerOrderStatus.PARTIALLY_FILLED,
            filled_size=0.1,
            average_fill_price=100.5,
            submitted_at=fixed_now + timedelta(seconds=1),
            acknowledged_at=fixed_now + timedelta(seconds=1),
            requires_manual_review=True,
        )
    )

    service.process_price_update(
        "CS.D.EURUSD.MINI.IP",
        100.0,
        bid=99.99,
        ask=100.01,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now,
    )
    service.process_price_update(
        "CS.D.EURUSD.MINI.IP",
        100.5,
        bid=100.49,
        ask=100.51,
        market_status="TRADEABLE",
        tradable=True,
        received_at=fixed_now + timedelta(seconds=1),
    )

    runtime_before = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == "smoke_test_hold")
        .where(StrategyRuntimeState.instrument == "CS.D.EURUSD.MINI.IP")
    ).one()
    assert runtime_before.runtime_mode == "EXITS_ONLY"

    manager.reconcile(now=fixed_now + timedelta(minutes=1))

    runtime_after = session.exec(
        select(StrategyRuntimeState)
        .where(StrategyRuntimeState.strategy_name == "smoke_test_hold")
        .where(StrategyRuntimeState.instrument == "CS.D.EURUSD.MINI.IP")
    ).one()

    assert runtime_after.status == "RUNNING"
    assert runtime_after.runtime_mode == "EXITS_ONLY"
    assert (
        runtime_manager.get_engine(
            "smoke_test_hold", "CS.D.EURUSD.MINI.IP"
        ).runtime_mode
        == "EXITS_ONLY"
    )
