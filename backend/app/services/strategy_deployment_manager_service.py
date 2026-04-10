from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment, StrategyDeploymentState
from app.models.strategy_governance import GovernanceApprovalState, StrategyFamilyGovernance
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.operator_control_service import OperatorControlService
from app.services.regime_suitability_service import RegimeSuitabilityService
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.strategy_service import StrategyService
from app.strategies.registry import StrategyMetadata, strategy_registry


@dataclass(frozen=True, slots=True)
class DeploymentReconcileResult:
    deployed: int
    paused: int
    blocked: int
    degraded: int
    emergency_stopped: int


class StrategyDeploymentManagerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.governance_service = StrategyGovernanceService(session)
        self.operator_control_service = OperatorControlService(session)
        self.suitability_service = RegimeSuitabilityService()
        self.strategy_service = StrategyService(session)

    def reconcile(self, *, now: datetime | None = None) -> DeploymentReconcileResult:
        current_time = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        governance_records = self.governance_service.list_strategies()
        counts = {
            StrategyDeploymentState.AUTO_DEPLOYED.value: 0,
            StrategyDeploymentState.AUTO_PAUSED.value: 0,
            StrategyDeploymentState.BLOCKED.value: 0,
            StrategyDeploymentState.DEGRADED.value: 0,
            StrategyDeploymentState.EMERGENCY_STOPPED.value: 0,
        }
        for governance in governance_records:
            metadata = strategy_registry.get_metadata(governance.strategy_name)
            deployment = self._get_or_create_deployment(governance=governance, now=current_time)
            target_state, selected_profile, selected_parameters, selected_instrument, selected_asset_class, reason, score = self._evaluate_target_state(
                governance=governance,
                metadata=metadata,
            )

            if target_state == StrategyDeploymentState.AUTO_DEPLOYED.value:
                manual_runtime = self._get_running_manual_runtime(governance.strategy_name)
                if manual_runtime is not None:
                    target_state = StrategyDeploymentState.BLOCKED.value
                    reason = (
                        f"Manual runtime is active on {manual_runtime.instrument}, so autonomous deployment is blocked."
                    )
                    selected_instrument = manual_runtime.instrument
                    selected_asset_class = selected_asset_class or None
                else:
                    restart_reason = self._ensure_auto_runtime(
                        strategy_name=governance.strategy_name,
                        instrument=selected_instrument,
                        deployment_id=deployment.id,
                        profile_name=selected_profile,
                        strategy_parameters=selected_parameters,
                    )
                    if restart_reason is not None:
                        deployment.last_restart_reason = restart_reason
                        domain_event_service.record_event(
                            event_type="control_plane.runtime_restarted",
                            category="strategy",
                            severity="info",
                            source="strategy_deployment_manager.reconcile",
                            title="Autonomous runtime restarted",
                            message=f"{governance.strategy_name} runtime restarted to apply deployment change.",
                            strategy_name=governance.strategy_name,
                            instrument=selected_instrument,
                            payload_json={
                                "reason": restart_reason,
                                "selected_profile": selected_profile,
                                "selected_parameters": selected_parameters,
                            },
                            created_at=current_time,
                        )
            else:
                self._stop_auto_runtimes(governance.strategy_name)

            previous_state = deployment.state
            previous_profile = deployment.selected_profile
            deployment.state = target_state
            deployment.selected_profile = selected_profile
            deployment.selected_profile_parameters = dict(selected_parameters)
            deployment.selected_instrument = selected_instrument
            deployment.selected_asset_class = selected_asset_class
            deployment.suitability_score = score
            if selected_profile is not None and selected_profile != previous_profile:
                deployment.profile_selected_at = current_time
                deployment.profile_change_reason = reason
            deployment.suitability_reason = reason if target_state in {
                StrategyDeploymentState.AUTO_DEPLOYED.value,
                StrategyDeploymentState.AUTO_DEPLOYABLE.value,
                StrategyDeploymentState.AUTO_PAUSED.value,
            } else None
            deployment.blocked_reason = reason if target_state in {
                StrategyDeploymentState.NOT_APPROVED.value,
                StrategyDeploymentState.BLOCKED.value,
                StrategyDeploymentState.EMERGENCY_STOPPED.value,
            } else None
            deployment.degraded_reason = reason if target_state == StrategyDeploymentState.DEGRADED.value else None
            deployment.last_evaluated_at = current_time
            if target_state != previous_state:
                deployment.last_state_changed_at = current_time
            if target_state == StrategyDeploymentState.AUTO_DEPLOYED.value and previous_state != target_state:
                deployment.last_deployed_at = current_time
            deployment.updated_at = current_time
            self.session.add(deployment)
            self.session.commit()
            self.session.refresh(deployment)
            if target_state in counts:
                counts[target_state] += 1
            if target_state != previous_state:
                domain_event_service.record_event(
                    event_type="control_plane.deployment_state_changed",
                    category="strategy",
                    severity="info",
                    source="strategy_deployment_manager.reconcile",
                    title="Strategy deployment state changed",
                    message=f"{governance.strategy_name} moved from {previous_state} to {target_state}.",
                    strategy_name=governance.strategy_name,
                    instrument=selected_instrument,
                    payload_json={
                        "previous_state": previous_state,
                        "new_state": target_state,
                        "selected_profile": selected_profile,
                        "selected_parameters": selected_parameters,
                        "selected_instrument": selected_instrument,
                        "selected_asset_class": selected_asset_class,
                        "reason": reason,
                        "suitability_score": score,
                    },
                    created_at=current_time,
                )

        return DeploymentReconcileResult(
            deployed=counts[StrategyDeploymentState.AUTO_DEPLOYED.value],
            paused=counts[StrategyDeploymentState.AUTO_PAUSED.value],
            blocked=counts[StrategyDeploymentState.BLOCKED.value],
            degraded=counts[StrategyDeploymentState.DEGRADED.value],
            emergency_stopped=counts[StrategyDeploymentState.EMERGENCY_STOPPED.value],
        )

    def list_deployments(self) -> list[StrategyDeployment]:
        self.governance_service.ensure_defaults()
        statement = select(StrategyDeployment).order_by(StrategyDeployment.strategy_name)
        return list(self.session.exec(statement))

    def _evaluate_target_state(
        self,
        *,
        governance: StrategyFamilyGovernance,
        metadata: StrategyMetadata,
    ) -> tuple[str, str | None, dict[str, object], str | None, str | None, str, float | None]:
        health_status = str(get_health_service().get_health_report()["status"])
        resolved_profile = self._select_profile(governance=governance, metadata=metadata)
        selected_profile = resolved_profile.profile_name if resolved_profile is not None else None
        selected_parameters = resolved_profile.parameter_values if resolved_profile is not None else {}
        if governance.approval_state != GovernanceApprovalState.APPROVED.value:
            return (
                StrategyDeploymentState.NOT_APPROVED.value,
                selected_profile,
                selected_parameters,
                None,
                None,
                "Strategy family is not approved for deployment.",
                None,
            )
        if governance.emergency_stop:
            return (
                StrategyDeploymentState.EMERGENCY_STOPPED.value,
                selected_profile,
                selected_parameters,
                None,
                None,
                "Operator emergency stop is active for this strategy family.",
                None,
            )
        if not governance.autonomous_operation_allowed or not self.operator_control_service.get_effective_autonomous_control_enabled():
            return (
                StrategyDeploymentState.APPROVED.value,
                selected_profile,
                selected_parameters,
                None,
                None,
                "Governance approval exists, but autonomous deployment is not enabled.",
                None,
            )
        if self.settings.runtime_global_entry_kill_switch:
            return (
                StrategyDeploymentState.BLOCKED.value,
                selected_profile,
                selected_parameters,
                None,
                None,
                "Global entry kill switch is active.",
                None,
            )
        candidate = self.suitability_service.select_best_candidate(
            metadata=metadata,
            approved_asset_classes=governance.approved_asset_classes,
            approved_instruments=governance.approved_instruments,
        )
        if candidate is None:
            return (
                StrategyDeploymentState.BLOCKED.value,
                selected_profile,
                selected_parameters,
                None,
                None,
                "No governance-approved instrument candidates are currently available.",
                None,
            )
        if health_status == "critical":
            return (
                StrategyDeploymentState.BLOCKED.value,
                selected_profile,
                selected_parameters,
                candidate.instrument,
                candidate.asset_class,
                "Operational health is critical, so autonomous deployment is blocked.",
                candidate.score,
            )
        if not candidate.market_status.market_open or not candidate.market_status.tradable:
            return (
                StrategyDeploymentState.AUTO_PAUSED.value,
                selected_profile,
                selected_parameters,
                candidate.instrument,
                candidate.asset_class,
                candidate.reason,
                candidate.score,
            )
        if not candidate.market_status.is_ok:
            return (
                StrategyDeploymentState.DEGRADED.value,
                selected_profile,
                selected_parameters,
                candidate.instrument,
                candidate.asset_class,
                candidate.reason,
                candidate.score,
            )
        return (
            StrategyDeploymentState.AUTO_DEPLOYED.value,
            selected_profile,
            selected_parameters,
            candidate.instrument,
            candidate.asset_class,
            candidate.reason,
            candidate.score,
        )

    def _get_or_create_deployment(
        self,
        *,
        governance: StrategyFamilyGovernance,
        now: datetime,
    ) -> StrategyDeployment:
        deployment_key = f"{governance.strategy_name}:auto"
        statement = select(StrategyDeployment).where(StrategyDeployment.deployment_key == deployment_key)
        deployment = self.session.exec(statement).first()
        if deployment is not None:
            return deployment
        deployment = StrategyDeployment(
            strategy_name=governance.strategy_name,
            governance_id=governance.id,
            deployment_key=deployment_key,
            state=StrategyDeploymentState.NOT_APPROVED.value,
            control_mode="AUTO",
            created_at=now,
            updated_at=now,
            last_state_changed_at=now,
        )
        self.session.add(deployment)
        self.session.commit()
        self.session.refresh(deployment)
        return deployment

    @staticmethod
    def _select_profile(
        *,
        governance: StrategyFamilyGovernance,
        metadata: StrategyMetadata,
    ):
        available_profiles = [profile.name for profile in metadata.parameter_profiles] or ["default"]
        for profile_name in governance.approved_profile_names:
            if profile_name in available_profiles:
                return strategy_registry.resolve_profile(metadata.name, profile_name)
        return strategy_registry.resolve_profile(metadata.name, available_profiles[0] if available_profiles else None)

    def _get_running_manual_runtime(self, strategy_name: str) -> StrategyRuntimeState | None:
        statement = (
            select(StrategyRuntimeState)
            .where(StrategyRuntimeState.strategy_name == strategy_name)
            .where(StrategyRuntimeState.status == "RUNNING")
            .where(StrategyRuntimeState.control_mode == "MANUAL")
        )
        return self.session.exec(statement).first()

    def _get_running_auto_runtimes(self, strategy_name: str) -> list[StrategyRuntimeState]:
        statement = (
            select(StrategyRuntimeState)
            .where(StrategyRuntimeState.strategy_name == strategy_name)
            .where(StrategyRuntimeState.status == "RUNNING")
            .where(StrategyRuntimeState.control_mode == "AUTO")
        )
        return list(self.session.exec(statement))

    def _ensure_auto_runtime(
        self,
        *,
        strategy_name: str,
        instrument: str | None,
        deployment_id: int,
        profile_name: str | None,
        strategy_parameters: dict[str, object],
    ) -> str | None:
        if instrument is None:
            return None
        running_auto_runtimes = self._get_running_auto_runtimes(strategy_name)
        restart_reason: str | None = None
        for runtime in running_auto_runtimes:
            if runtime.instrument != instrument:
                restart_reason = f"Instrument changed from {runtime.instrument} to {instrument}."
                self.strategy_service.stop_strategy(strategy_name=strategy_name, instrument=runtime.instrument)
            elif runtime.active_profile_name != profile_name or (runtime.parameters or {}) != strategy_parameters:
                restart_reason = f"Profile changed from {runtime.active_profile_name or 'unassigned'} to {profile_name or 'default'}."
                self.strategy_service.stop_strategy(strategy_name=strategy_name, instrument=runtime.instrument)
        if runtime_manager.get_engine(strategy_name, instrument) is None:
            self.strategy_service.start_strategy(
                strategy_name=strategy_name,
                instrument=instrument,
                control_mode="AUTO",
                deployment_id=deployment_id,
                profile_name=profile_name,
                strategy_parameters=strategy_parameters,
            )
            if restart_reason is None:
                restart_reason = f"Runtime started with profile {profile_name or 'default'}."
        return restart_reason

    def _stop_auto_runtimes(self, strategy_name: str) -> None:
        for runtime in self._get_running_auto_runtimes(strategy_name):
            if runtime_manager.get_engine(strategy_name, runtime.instrument) is not None:
                self.strategy_service.stop_strategy(strategy_name=strategy_name, instrument=runtime.instrument)
