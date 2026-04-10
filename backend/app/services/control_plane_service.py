from __future__ import annotations

from collections import Counter

from sqlmodel import Session, desc, select

from app.core.config import get_settings
from app.models.domain_event import DomainEvent
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.services.operator_control_service import OperatorControlService
from app.services.strategy_deployment_manager_service import StrategyDeploymentManagerService
from app.services.strategy_governance_service import StrategyGovernanceService
from app.strategies.registry import strategy_registry


class ControlPlaneService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.operator_control_service = OperatorControlService(session)
        self.governance_service = StrategyGovernanceService(session)
        self.deployment_manager = StrategyDeploymentManagerService(session)

    def get_summary(self) -> dict[str, object]:
        families = self._build_family_rows()
        counts = Counter(str(family["deployment"]["state"]) for family in families if family.get("deployment"))
        misaligned_count = len([family for family in families if family["alignment"]["is_aligned"] is False])
        operator_control = self.operator_control_service.get_summary()
        return {
            "autonomous_control_enabled": operator_control["effective_autonomous_control_enabled"],
            "configured_autonomous_control_enabled": operator_control["configured_autonomous_control_enabled"],
            "effective_autonomous_control_enabled": operator_control["effective_autonomous_control_enabled"],
            "autonomy_override_active": operator_control["override_active"],
            "autonomy_override_value": operator_control["override_value"],
            "autonomy_override_reason": operator_control["override_reason"],
            "autonomy_updated_at": operator_control["updated_at"],
            "counts": dict(counts),
            "misaligned_count": misaligned_count,
            "families": families,
        }

    def get_family_detail(self, strategy_name: str) -> dict[str, object]:
        family = next(
            (row for row in self._build_family_rows() if row["strategy_name"] == strategy_name),
            None,
        )
        if family is None:
            raise ValueError(f"Strategy family '{strategy_name}' is not registered.")
        return family

    def _build_family_rows(self) -> list[dict[str, object]]:
        governance = {
            record.strategy_name: record
            for record in self.governance_service.list_strategies()
        }
        deployments = {
            deployment.strategy_name: deployment
            for deployment in self.deployment_manager.list_deployments()
        }
        runtimes_by_strategy: dict[str, list[StrategyRuntimeState]] = {}
        for runtime in self.session.exec(select(StrategyRuntimeState).order_by(StrategyRuntimeState.updated_at.desc())).all():
            runtimes_by_strategy.setdefault(runtime.strategy_name, []).append(runtime)

        metadata_by_name = {
            metadata.name: metadata
            for metadata in strategy_registry.list_metadata()
        }
        rows: list[dict[str, object]] = []
        for strategy_name, metadata in metadata_by_name.items():
            governance_record = governance.get(strategy_name)
            deployment = deployments.get(strategy_name)
            runtimes = runtimes_by_strategy.get(strategy_name, [])
            active_runtime = self._select_active_runtime(runtimes)
            recent_events = self._load_recent_events(strategy_name)
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "description": metadata.description,
                    "supported_asset_classes": list(metadata.supported_asset_classes),
                    "available_profile_names": [profile.name for profile in metadata.parameter_profiles],
                    "governance": self._serialize_governance(governance_record, metadata),
                    "deployment": self._serialize_deployment(deployment),
                    "runtime": self._serialize_runtime(active_runtime, runtimes),
                    "alignment": self._build_alignment(deployment=deployment, active_runtime=active_runtime),
                    "recent_events": [self._serialize_event(event) for event in recent_events],
                }
            )
        return rows

    @staticmethod
    def _select_active_runtime(runtimes: list[StrategyRuntimeState]) -> StrategyRuntimeState | None:
        running = [runtime for runtime in runtimes if runtime.status == "RUNNING"]
        if not running:
            return None
        return sorted(
            running,
            key=lambda runtime: (
                0 if runtime.control_mode == "AUTO" else 1,
                runtime.updated_at,
            ),
            reverse=True,
        )[0]

    def _load_recent_events(self, strategy_name: str) -> list[DomainEvent]:
        event_types = [
            "control_plane.deployment_state_changed",
            "control_plane.runtime_restarted",
            "control_plane.reconciled",
            "control_plane.reconciliation_cycle_completed",
            "operator.governance_updated",
            "strategy.runtime_started",
            "strategy.runtime_stopped",
        ]
        statement = (
            select(DomainEvent)
            .where(DomainEvent.strategy_name == strategy_name)
            .where(DomainEvent.event_type.in_(event_types))
            .order_by(desc(DomainEvent.created_at), desc(DomainEvent.id))
            .limit(8)
        )
        return list(self.session.exec(statement).all())

    @staticmethod
    def _serialize_governance(record, metadata) -> dict[str, object]:
        if record is None:
            return {
                "approval_state": "UNKNOWN",
                "autonomous_operation_allowed": False,
                "emergency_stop": False,
                "approved_asset_classes": [],
                "approved_instruments": [],
                "approved_profile_names": [],
                "supported_asset_classes": list(metadata.supported_asset_classes),
                "available_profile_names": [profile.name for profile in metadata.parameter_profiles],
                "updated_at": None,
            }
        return {
            "approval_state": record.approval_state,
            "autonomous_operation_allowed": record.autonomous_operation_allowed,
            "emergency_stop": record.emergency_stop,
            "approved_asset_classes": record.approved_asset_classes,
            "approved_instruments": record.approved_instruments,
            "approved_profile_names": record.approved_profile_names,
            "supported_asset_classes": list(metadata.supported_asset_classes),
            "available_profile_names": [profile.name for profile in metadata.parameter_profiles],
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _serialize_deployment(deployment: StrategyDeployment | None) -> dict[str, object] | None:
        if deployment is None:
            return None
        return {
            "state": deployment.state,
            "selected_profile": deployment.selected_profile,
            "selected_profile_parameters": deployment.selected_profile_parameters,
            "selected_instrument": deployment.selected_instrument,
            "selected_asset_class": deployment.selected_asset_class,
            "suitability_score": deployment.suitability_score,
            "suitability_reason": deployment.suitability_reason,
            "profile_selected_at": deployment.profile_selected_at,
            "profile_change_reason": deployment.profile_change_reason,
            "last_restart_reason": deployment.last_restart_reason,
            "blocked_reason": deployment.blocked_reason,
            "degraded_reason": deployment.degraded_reason,
            "last_evaluated_at": deployment.last_evaluated_at,
            "last_deployed_at": deployment.last_deployed_at,
            "updated_at": deployment.updated_at,
        }

    @staticmethod
    def _serialize_runtime(active_runtime: StrategyRuntimeState | None, runtimes: list[StrategyRuntimeState]) -> dict[str, object]:
        if active_runtime is None:
            return {
                "is_running": False,
                "active_runtime_id": None,
                "active_instrument": None,
                "active_profile_name": None,
                "active_parameters": {},
                "control_mode": None,
                "recovery_state": None,
                "updated_at": None,
                "persisted_runtimes": [
                    {
                        "runtime_id": runtime.runtime_id,
                        "status": runtime.status,
                        "instrument": runtime.instrument,
                        "control_mode": runtime.control_mode,
                        "active_profile_name": runtime.active_profile_name,
                        "parameters": runtime.parameters,
                        "updated_at": runtime.updated_at,
                    }
                    for runtime in runtimes
                ],
            }
        return {
            "is_running": True,
            "active_runtime_id": active_runtime.runtime_id,
            "active_instrument": active_runtime.instrument,
            "active_profile_name": active_runtime.active_profile_name,
            "active_parameters": active_runtime.parameters,
            "control_mode": active_runtime.control_mode,
            "recovery_state": active_runtime.recovery_state,
            "updated_at": active_runtime.updated_at,
            "persisted_runtimes": [
                {
                    "runtime_id": runtime.runtime_id,
                    "status": runtime.status,
                    "instrument": runtime.instrument,
                    "control_mode": runtime.control_mode,
                    "active_profile_name": runtime.active_profile_name,
                    "parameters": runtime.parameters,
                    "updated_at": runtime.updated_at,
                }
                for runtime in runtimes
            ],
        }

    @staticmethod
    def _build_alignment(
        *,
        deployment: StrategyDeployment | None,
        active_runtime: StrategyRuntimeState | None,
    ) -> dict[str, object]:
        if deployment is None:
            return {
                "is_aligned": None,
                "status": "NO_DEPLOYMENT",
                "reason": "No deployment record exists for this strategy family yet.",
                "checks": [],
            }
        if deployment.state == "AUTO_DEPLOYED":
            if active_runtime is None:
                return {
                    "is_aligned": False,
                    "status": "MISMATCH",
                    "reason": "Deployment expects an autonomous runtime, but none is running.",
                    "checks": [
                        {"code": "runtime_present", "passed": False},
                    ],
                }
            checks = [
                {
                    "code": "control_mode_auto",
                    "passed": active_runtime.control_mode == "AUTO",
                    "expected": "AUTO",
                    "actual": active_runtime.control_mode,
                },
                {
                    "code": "instrument_match",
                    "passed": active_runtime.instrument == deployment.selected_instrument,
                    "expected": deployment.selected_instrument,
                    "actual": active_runtime.instrument,
                },
                {
                    "code": "profile_match",
                    "passed": active_runtime.active_profile_name == deployment.selected_profile,
                    "expected": deployment.selected_profile,
                    "actual": active_runtime.active_profile_name,
                },
                {
                    "code": "parameters_match",
                    "passed": (active_runtime.parameters or {}) == (deployment.selected_profile_parameters or {}),
                    "expected": deployment.selected_profile_parameters,
                    "actual": active_runtime.parameters,
                },
            ]
            passed = all(bool(check["passed"]) for check in checks)
            return {
                "is_aligned": passed,
                "status": "ALIGNED" if passed else "MISMATCH",
                "reason": (
                    "Runtime matches deployment intent."
                    if passed
                    else "Runtime diverges from selected deployment profile or instrument."
                ),
                "checks": checks,
            }
        if active_runtime is not None and active_runtime.control_mode == "AUTO":
            return {
                "is_aligned": False,
                "status": "MISMATCH",
                "reason": "An autonomous runtime is running while deployment is not in AUTO_DEPLOYED state.",
                "checks": [
                    {"code": "unexpected_auto_runtime", "passed": False, "actual": active_runtime.control_mode},
                ],
            }
        return {
            "is_aligned": True,
            "status": "ALIGNED",
            "reason": "Runtime state is consistent with non-deployed deployment intent.",
            "checks": [],
        }

    @staticmethod
    def _serialize_event(event: DomainEvent) -> dict[str, object]:
        return {
            "id": event.id,
            "created_at": event.created_at,
            "event_type": event.event_type,
            "title": event.title,
            "message": event.message,
            "severity": event.severity,
            "payload_json": event.payload_json,
        }
