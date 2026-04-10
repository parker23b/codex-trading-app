from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select

from app.core.runtime import runtime_manager
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.services.control_plane_service import ControlPlaneService
from app.services.health_service import get_health_service
from app.services.operator_control_service import OperatorControlService
from app.services.strategy_deployment_manager_service import StrategyDeploymentManagerService
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.strategy_service import StrategyService


def test_control_plane_seeds_governance_defaults(session):
    service = ControlPlaneService(session)

    summary = service.get_summary()

    assert summary["families"]
    families_by_name = {item["strategy_name"]: item for item in summary["families"]}
    assert families_by_name["mean_reversion"]["governance"]["approval_state"] == "APPROVED"
    assert families_by_name["mean_reversion"]["governance"]["autonomous_operation_allowed"] is True
    assert "default" in families_by_name["mean_reversion"]["governance"]["available_profile_names"]
    assert "fast" in families_by_name["mean_reversion"]["governance"]["available_profile_names"]


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


def test_governance_service_upgrades_legacy_default_false_to_allowed(session, fixed_now):
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


def test_reconcile_auto_deploys_approved_autonomous_strategy(session, broker, fixed_now):
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

    result = manager.reconcile(now=fixed_now)

    deployment = session.exec(
        select(StrategyDeployment).where(StrategyDeployment.strategy_name == "mean_reversion")
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.strategy_name == "mean_reversion")
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
    assert runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is not None
    engine = runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP")
    assert engine is not None
    assert engine.active_profile_name == "fast"
    assert engine.strategy_parameters["window_size"] == 12
    assert getattr(engine.strategy, "window_size") == 12

    strategy_summary = next(
        strategy for strategy in StrategyService(session).list_strategies()
        if strategy["name"] == "mean_reversion"
    )
    assert strategy_summary["deployment_profile"] == "fast"
    assert strategy_summary["deployment_parameters"]["window_size"] == 12
    assert next(
        parameter for parameter in strategy_summary["parameters"]
        if parameter["key"] == "window_size"
    )["value"] == 12
    control_plane_family = ControlPlaneService(session).get_family_detail("mean_reversion")
    assert control_plane_family["deployment"]["selected_profile"] == "fast"
    assert control_plane_family["runtime"]["active_profile_name"] == "fast"
    assert control_plane_family["alignment"]["is_aligned"] is True


def test_reconcile_emergency_stop_blocks_and_stops_auto_runtime(session, broker, fixed_now):
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
    manager.reconcile(now=fixed_now)

    governance_service.upsert_strategy(
        strategy_name="mean_reversion",
        emergency_stop=True,
    )
    result = manager.reconcile(now=fixed_now.replace(tzinfo=UTC))

    deployment = session.exec(
        select(StrategyDeployment).where(StrategyDeployment.strategy_name == "mean_reversion")
    ).one()
    runtime = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.strategy_name == "mean_reversion")
    ).one()

    assert result.emergency_stopped >= 1
    assert deployment.state == "EMERGENCY_STOPPED"
    assert runtime.status == "STOPPED"
    assert runtime_manager.get_engine("mean_reversion", "IX.D.FTSE.DAILY.IP") is None


def test_profile_change_restarts_autonomous_runtime_with_new_parameters(session, broker, fixed_now):
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
    manager.reconcile(now=fixed_now)

    first_runtime = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.strategy_name == "mean_reversion")
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
        select(StrategyDeployment).where(StrategyDeployment.strategy_name == "mean_reversion")
    ).one()
    runtimes = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.strategy_name == "mean_reversion")
    ).all()
    active_runtime = next(runtime for runtime in runtimes if runtime.status == "RUNNING")

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
    manager.reconcile(now=fixed_now)

    runtime = session.exec(
        select(StrategyRuntimeState).where(StrategyRuntimeState.strategy_name == "mean_reversion")
    ).one()
    runtime.active_profile_name = "default"
    runtime.parameters = {"window_size": 20, "entry_threshold": 0.0015, "exit_threshold": 0.0004}
    session.add(runtime)
    session.commit()

    family = ControlPlaneService(session).get_family_detail("mean_reversion")

    assert family["alignment"]["is_aligned"] is False
    assert family["alignment"]["status"] == "MISMATCH"
    assert any(
        check["code"] == "profile_match" and check["passed"] is False
        for check in family["alignment"]["checks"]
    )
