from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment, StrategyDeploymentState
from app.models.strategy_governance import (
    GovernanceApprovalState,
    StrategyFamilyGovernance,
)
from app.models.trade import Position
from app.services.audit_event_recorder import record_required_domain_event
from app.services.health_service import get_health_service
from app.services.operator_control_service import OperatorControlService
from app.services.open_risk_authority_service import OpenRiskAuthorityService
from app.services.operational_state_service import (
    OpenRiskManagementState,
    OperationalStateService,
)
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
        self.operational_state_service = OperationalStateService(session)
        self.suitability_service = RegimeSuitabilityService(session)
        self.strategy_service = StrategyService(session)

    def reconcile(
        self,
        *,
        now: datetime | None = None,
        startup_context: dict[str, object] | None = None,
    ) -> DeploymentReconcileResult:
        current_time = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        reconcile_startup_context = self._resolve_startup_context(
            startup_context=startup_context,
            current_time=current_time,
        )
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
            deployment = self._get_or_create_deployment(
                governance=governance, now=current_time
            )
            (
                target_state,
                selected_profile,
                selected_parameters,
                selected_instrument,
                selected_asset_class,
                reason,
                score,
            ) = self._evaluate_target_state(
                governance=governance,
                metadata=metadata,
            )
            open_positions = self._list_open_positions(governance.strategy_name)
            open_risk_management_state = OpenRiskManagementState.NO_OPEN_RISK.value
            open_risk_management_reason: str | None = None

            if target_state == StrategyDeploymentState.AUTO_DEPLOYED.value:
                manual_runtime = self._get_running_manual_runtime(
                    governance.strategy_name
                )
                if manual_runtime is not None:
                    target_state = StrategyDeploymentState.BLOCKED.value
                    reason = f"Manual runtime is active on {manual_runtime.instrument}, so autonomous deployment is blocked."
                    selected_instrument = manual_runtime.instrument
                    selected_asset_class = selected_asset_class or None
                else:
                    restart_reason = self._ensure_auto_runtime(
                        strategy_name=governance.strategy_name,
                        instrument=selected_instrument,
                        open_positions=open_positions,
                        deployment_id=deployment.id,
                        profile_name=selected_profile,
                        strategy_parameters=selected_parameters,
                        startup_context=reconcile_startup_context,
                    )
                    if selected_instrument is not None:
                        selected_engine = runtime_manager.get_engine(
                            governance.strategy_name, selected_instrument
                        )
                        if (
                            selected_engine is not None
                            and getattr(selected_engine, "runtime_mode", "NORMAL")
                            == "NORMAL"
                        ):
                            self.strategy_service.set_runtime_mode(
                                strategy_name=governance.strategy_name,
                                instrument=selected_instrument,
                                runtime_mode="NORMAL",
                            )
                    if restart_reason is not None:
                        deployment.last_restart_reason = restart_reason
                        record_required_domain_event(
                            session=self.session,
                            event_type="control_plane.runtime_restarted",
                            category="strategy",
                            severity="info",
                            correlation_id=str(
                                reconcile_startup_context.get("correlation_id")
                            )
                            if reconcile_startup_context.get("correlation_id")
                            is not None
                            else None,
                            source="strategy_deployment_manager.reconcile",
                            title="Autonomous runtime restarted",
                            message=f"{governance.strategy_name} runtime restarted to apply deployment change.",
                            strategy_name=governance.strategy_name,
                            instrument=selected_instrument,
                            actor_type="service",
                            actor_id="strategy_deployment_manager",
                            payload_json={
                                "deployment_id": deployment.id,
                                "reason": restart_reason,
                                "selected_profile": selected_profile,
                                "selected_parameters": selected_parameters,
                                "startup_context": reconcile_startup_context,
                            },
                            created_at=current_time,
                        )
                open_risk_management_state, open_risk_management_reason = (
                    self._assess_open_risk_management(
                        strategy_name=governance.strategy_name,
                        open_positions=open_positions,
                    )
                )
            else:
                open_risk_management_state, open_risk_management_reason = (
                    self._handle_non_auto_runtime_transition(
                        strategy_name=governance.strategy_name,
                        deployment=deployment,
                        open_positions=open_positions,
                        target_state=target_state,
                        target_reason=reason,
                        stop_context=reconcile_startup_context,
                    )
                )

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
            deployment.suitability_reason = (
                reason
                if target_state
                in {
                    StrategyDeploymentState.AUTO_DEPLOYED.value,
                    StrategyDeploymentState.AUTO_DEPLOYABLE.value,
                    StrategyDeploymentState.AUTO_PAUSED.value,
                }
                else None
            )
            deployment.blocked_reason = (
                reason
                if target_state
                in {
                    StrategyDeploymentState.NOT_APPROVED.value,
                    StrategyDeploymentState.BLOCKED.value,
                    StrategyDeploymentState.EMERGENCY_STOPPED.value,
                }
                else None
            )
            deployment.degraded_reason = (
                reason
                if target_state == StrategyDeploymentState.DEGRADED.value
                else None
            )
            deployment.last_evaluated_at = current_time
            deployment.open_risk_management_state = open_risk_management_state
            deployment.open_risk_management_reason = open_risk_management_reason
            if target_state != previous_state:
                deployment.last_state_changed_at = current_time
            if (
                target_state == StrategyDeploymentState.AUTO_DEPLOYED.value
                and previous_state != target_state
            ):
                deployment.last_deployed_at = current_time
            deployment.updated_at = current_time
            self.session.add(deployment)
            self.session.commit()
            self.session.refresh(deployment)
            OpenRiskAuthorityService(self.session).refresh(
                source="strategy_deployment_manager.reconcile"
            )
            if target_state in counts:
                counts[target_state] += 1
            if target_state != previous_state:
                record_required_domain_event(
                    session=self.session,
                    event_type="control_plane.deployment_state_changed",
                    category="strategy",
                    severity="info",
                    correlation_id=str(reconcile_startup_context.get("correlation_id"))
                    if reconcile_startup_context.get("correlation_id") is not None
                    else None,
                    source="strategy_deployment_manager.reconcile",
                    title="Strategy deployment state changed",
                    message=f"{governance.strategy_name} moved from {previous_state} to {target_state}.",
                    strategy_name=governance.strategy_name,
                    instrument=selected_instrument,
                    actor_type="service",
                    actor_id="strategy_deployment_manager",
                    payload_json={
                        "deployment_id": deployment.id,
                        "previous_state": previous_state,
                        "new_state": target_state,
                        "selected_profile": selected_profile,
                        "selected_parameters": selected_parameters,
                        "selected_instrument": selected_instrument,
                        "selected_asset_class": selected_asset_class,
                        "reason": reason,
                        "suitability_score": score,
                        "startup_context": reconcile_startup_context,
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

    @staticmethod
    def _resolve_startup_context(
        *,
        startup_context: dict[str, object] | None,
        current_time: datetime,
    ) -> dict[str, object]:
        if startup_context:
            return dict(startup_context)
        return {
            "authority_kind": "deployment_reconcile",
            "authority_source": "strategy_deployment_manager.reconcile",
            "actor_type": "service",
            "actor_id": "strategy_deployment_manager",
            "correlation_id": (f"deployment-reconcile:{current_time.isoformat()}"),
        }

    def list_deployments(self) -> list[StrategyDeployment]:
        self.governance_service.ensure_defaults()
        return self.list_existing_deployments()

    def list_existing_deployments(self) -> list[StrategyDeployment]:
        statement = select(StrategyDeployment).order_by(
            StrategyDeployment.strategy_name
        )
        return list(self.session.exec(statement))

    def _evaluate_target_state(
        self,
        *,
        governance: StrategyFamilyGovernance,
        metadata: StrategyMetadata,
    ) -> tuple[
        str, str | None, dict[str, object], str | None, str | None, str, float | None
    ]:
        health_status = str(
            get_health_service().get_health_report(session=self.session)["status"]
        )
        resolved_profile = self._select_profile(
            governance=governance, metadata=metadata
        )
        selected_profile = (
            resolved_profile.profile_name if resolved_profile is not None else None
        )
        selected_parameters = (
            resolved_profile.parameter_values if resolved_profile is not None else {}
        )
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
        if (
            not governance.autonomous_operation_allowed
            or not self.operator_control_service.get_effective_autonomous_control_enabled()
        ):
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
        if (
            not candidate.market_status.market_open
            or not candidate.market_status.tradable
        ):
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
        statement = select(StrategyDeployment).where(
            StrategyDeployment.deployment_key == deployment_key
        )
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
        available_profiles = [
            profile.name for profile in metadata.parameter_profiles
        ] or ["default"]
        for profile_name in governance.approved_profile_names:
            if profile_name in available_profiles:
                return strategy_registry.resolve_profile(metadata.name, profile_name)
        return strategy_registry.resolve_profile(
            metadata.name, available_profiles[0] if available_profiles else None
        )

    def _get_running_manual_runtime(
        self, strategy_name: str
    ) -> StrategyRuntimeState | None:
        statement = (
            select(StrategyRuntimeState)
            .where(StrategyRuntimeState.strategy_name == strategy_name)
            .where(StrategyRuntimeState.status == "RUNNING")
            .where(StrategyRuntimeState.control_mode == "MANUAL")
        )
        return self.session.exec(statement).first()

    def _get_running_auto_runtimes(
        self, strategy_name: str
    ) -> list[StrategyRuntimeState]:
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
        open_positions: list[Position],
        deployment_id: int,
        profile_name: str | None,
        strategy_parameters: dict[str, object],
        startup_context: dict[str, object] | None,
    ) -> str | None:
        if instrument is None:
            return None
        running_auto_runtimes = self._get_running_auto_runtimes(strategy_name)
        restart_reason: str | None = None
        for runtime in running_auto_runtimes:
            if runtime.instrument != instrument:
                restart_reason = (
                    f"Instrument changed from {runtime.instrument} to {instrument}."
                )
                if self._instrument_has_open_risk(
                    runtime.instrument, open_positions=open_positions
                ):
                    self.strategy_service.set_runtime_mode(
                        strategy_name=strategy_name,
                        instrument=runtime.instrument,
                        runtime_mode="EXITS_ONLY",
                        recovery_reason=(
                            f"Autonomy rotated to {instrument} while {runtime.instrument} still has open risk."
                        ),
                    )
                else:
                    self.strategy_service.stop_strategy(
                        strategy_name=strategy_name,
                        instrument=runtime.instrument,
                        stop_context=startup_context,
                        stop_reason=restart_reason,
                    )
            elif (
                runtime.active_profile_name != profile_name
                or (runtime.parameters or {}) != strategy_parameters
            ):
                restart_reason = f"Profile changed from {runtime.active_profile_name or 'unassigned'} to {profile_name or 'default'}."
                self.strategy_service.stop_strategy(
                    strategy_name=strategy_name,
                    instrument=runtime.instrument,
                    stop_context=startup_context,
                    stop_reason=restart_reason,
                )
        if runtime_manager.get_engine(strategy_name, instrument) is None:
            self.strategy_service.start_strategy(
                strategy_name=strategy_name,
                instrument=instrument,
                control_mode="AUTO",
                runtime_mode="NORMAL",
                deployment_id=deployment_id,
                profile_name=profile_name,
                strategy_parameters=strategy_parameters,
                startup_context=startup_context,
            )
            if restart_reason is None:
                restart_reason = (
                    f"Runtime started with profile {profile_name or 'default'}."
                )
        return restart_reason

    @staticmethod
    def _instrument_has_open_risk(
        instrument: str, *, open_positions: list[Position]
    ) -> bool:
        return any(position.instrument == instrument for position in open_positions)

    def _stop_auto_runtimes(
        self,
        strategy_name: str,
        *,
        stop_context: dict[str, object] | None = None,
        stop_reason: str | None = None,
    ) -> None:
        for runtime in self._get_running_auto_runtimes(strategy_name):
            if (
                runtime_manager.get_engine(strategy_name, runtime.instrument)
                is not None
            ):
                self.strategy_service.stop_strategy(
                    strategy_name=strategy_name,
                    instrument=runtime.instrument,
                    stop_context=stop_context,
                    stop_reason=stop_reason
                    or "Autonomous deployment no longer permits this runtime.",
                )

    def _list_open_positions(self, strategy_name: str) -> list[Position]:
        statement = select(Position).where(
            Position.strategy_name == strategy_name,
            Position.is_open.is_(True),
        )
        return list(self.session.exec(statement))

    def _handle_non_auto_runtime_transition(
        self,
        *,
        strategy_name: str,
        deployment: StrategyDeployment,
        open_positions: list[Position],
        target_state: str,
        target_reason: str,
        stop_context: dict[str, object] | None = None,
    ) -> tuple[str, str | None]:
        if not open_positions:
            self._stop_auto_runtimes(
                strategy_name,
                stop_context=stop_context,
                stop_reason=target_reason,
            )
            return (OpenRiskManagementState.NO_OPEN_RISK.value, None)

        running_auto_runtimes = self._get_running_auto_runtimes(strategy_name)
        runtime_by_instrument = {
            runtime.instrument: runtime
            for runtime in running_auto_runtimes
            if runtime_manager.get_engine(strategy_name, runtime.instrument) is not None
        }
        open_instruments = sorted({position.instrument for position in open_positions})
        blocked_instruments: list[tuple[str, str | None]] = []

        for instrument in open_instruments:
            operational_state = (
                self.operational_state_service.get_summary_for_instrument(instrument)
            )
            if (
                not operational_state.exit_eligible
                or instrument not in runtime_by_instrument
            ):
                blocked_instruments.append(
                    (instrument, operational_state.exit_block_reason)
                )

        if not blocked_instruments and runtime_by_instrument:
            reason = f"{len(open_positions)} open position(s) remain; runtime retained in EXITS_ONLY while deployment is {target_state}."
            for runtime in running_auto_runtimes:
                if (
                    runtime.instrument in open_instruments
                    and runtime_manager.get_engine(strategy_name, runtime.instrument)
                    is not None
                ):
                    self.strategy_service.set_runtime_mode(
                        strategy_name=strategy_name,
                        instrument=runtime.instrument,
                        runtime_mode="EXITS_ONLY",
                        recovery_reason=reason,
                    )
                elif (
                    runtime_manager.get_engine(strategy_name, runtime.instrument)
                    is not None
                ):
                    self.strategy_service.stop_strategy(
                        strategy_name=strategy_name,
                        instrument=runtime.instrument,
                        stop_context=stop_context,
                        stop_reason=reason,
                    )
            return (OpenRiskManagementState.EXITS_ONLY.value, reason)

        self._stop_auto_runtimes(
            strategy_name,
            stop_context=stop_context,
            stop_reason=target_reason,
        )
        exit_block_reason = (
            blocked_instruments[0][1]
            if blocked_instruments
            else "no_exit_capable_runtime"
        )
        reason = (
            f"{len(open_positions)} open position(s) remain while exits are not operationally eligible; "
            f"deployment moved to {target_state} ({exit_block_reason})."
        )
        record_required_domain_event(
            session=self.session,
            event_type="risk.unmanaged_open_risk",
            category="risk",
            severity="error",
            source="strategy_deployment_manager.reconcile",
            title="Open risk is no longer under active automated management",
            message=f"{strategy_name} has open positions but no exit-capable AUTO runtime remains.",
            strategy_name=strategy_name,
            instrument=deployment.selected_instrument,
            actor_type="service",
            actor_id="strategy_deployment_manager",
            payload_json={
                "deployment_id": deployment.id,
                "deployment_state": target_state,
                "deployment_reason": target_reason,
                "previous_open_risk_management_state": (
                    deployment.open_risk_management_state
                ),
                "new_open_risk_management_state": (
                    OpenRiskManagementState.UNMANAGED_OPEN_RISK.value
                ),
                "open_position_count": len(open_positions),
                "blocked_instruments": [
                    {"instrument": instrument, "exit_block_reason": block_reason}
                    for instrument, block_reason in blocked_instruments
                ],
                "exit_eligible": False,
                "exit_block_reason": exit_block_reason,
            },
        )
        return (OpenRiskManagementState.UNMANAGED_OPEN_RISK.value, reason)

    def _assess_open_risk_management(
        self,
        *,
        strategy_name: str,
        open_positions: list[Position],
    ) -> tuple[str, str | None]:
        if not open_positions:
            return (OpenRiskManagementState.NO_OPEN_RISK.value, None)

        running_auto_runtimes = {
            runtime.instrument: runtime
            for runtime in self._get_running_auto_runtimes(strategy_name)
            if runtime_manager.get_engine(strategy_name, runtime.instrument) is not None
        }
        uncovered_instruments: list[str] = []
        blocked_instruments: list[tuple[str, str | None]] = []
        exits_only_instruments: list[str] = []

        for instrument in sorted({position.instrument for position in open_positions}):
            runtime = running_auto_runtimes.get(instrument)
            if runtime is None:
                uncovered_instruments.append(instrument)
                continue
            operational_state = (
                self.operational_state_service.get_summary_for_instrument(instrument)
            )
            if not operational_state.exit_eligible:
                blocked_instruments.append(
                    (instrument, operational_state.exit_block_reason)
                )
                continue
            if runtime.runtime_mode == "EXITS_ONLY":
                exits_only_instruments.append(instrument)

        if uncovered_instruments:
            return (
                OpenRiskManagementState.UNMANAGED_OPEN_RISK.value,
                f"Open positions remain on {', '.join(uncovered_instruments)} without an exit-capable AUTO runtime.",
            )
        if blocked_instruments:
            blocked_reason = blocked_instruments[0][1] or "exit_not_eligible"
            instruments = ", ".join(instrument for instrument, _ in blocked_instruments)
            return (
                OpenRiskManagementState.UNMANAGED_OPEN_RISK.value,
                f"Open positions on {instruments} are not exit-eligible ({blocked_reason}).",
            )
        if exits_only_instruments:
            return (
                OpenRiskManagementState.EXITS_ONLY.value,
                f"Open positions on {', '.join(exits_only_instruments)} are retained under EXITS_ONLY protection.",
            )
        return (
            OpenRiskManagementState.MANAGED.value,
            f"{len(open_positions)} open position(s) remain under active AUTO runtime management.",
        )
