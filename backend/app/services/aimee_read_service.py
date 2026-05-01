from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlmodel import Session, desc, select

from app.core.config import get_settings
from app.models.domain_event import DomainEvent
from app.models.operator_control import OperatorControlState
from app.models.promotion_request import PromotionRequest
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import Execution, ExecutionStatus, TradeIntent, TradeIntentState
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.reviewer.service import AIReviewerService
from app.services.operational_telemetry_service import OperationalTelemetryService
from app.strategies.registry import strategy_registry


class AimeeReadService:
    """Read-only projection for AIMEE.

    AIMEE is intended to explain the system without affecting the system.
    This service must therefore stay side-effect free and avoid any workflow
    that reconciles, persists reviews, seeds defaults, emits events, or mutates
    runtime or control-plane state while serving passive reads.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def get_snapshot(self) -> dict[str, object]:
        now = datetime.now(UTC)
        reviewer = AIReviewerService(self.session)
        return {
            "review": reviewer.get_operator_summary(persist=False),
            "history": reviewer.list_review_history(
                review_type="operator_summary", limit=6
            ),
            "controlPlane": self._control_plane_summary(),
            "coverage": self._coverage_summary(),
            "telemetry": OperationalTelemetryService(self.session).get_summary(),
            "events": self._events(limit=8),
            "strategies": self._strategies(),
            "updatedAt": now,
        }

    def _control_plane_summary(self) -> dict[str, object]:
        control_state = self.session.get(OperatorControlState, 1)
        effective_autonomy = (
            self.settings.autonomous_control_enabled
            if control_state is None
            or control_state.autonomous_control_override is None
            else control_state.autonomous_control_override
        )
        governance_by_name = {
            record.strategy_name: record
            for record in self.session.exec(select(StrategyFamilyGovernance)).all()
        }
        deployment_by_name = {
            deployment.strategy_name: deployment
            for deployment in self.session.exec(select(StrategyDeployment)).all()
        }
        runtimes_by_strategy: dict[str, list[StrategyRuntimeState]] = defaultdict(list)
        for runtime in self.session.exec(
            select(StrategyRuntimeState).order_by(
                StrategyRuntimeState.updated_at.desc()
            )
        ).all():
            runtimes_by_strategy[runtime.strategy_name].append(runtime)

        families: list[dict[str, object]] = []
        misaligned_count = 0
        for metadata in strategy_registry.list_metadata():
            strategy_name = metadata.name
            governance = governance_by_name.get(strategy_name)
            deployment = deployment_by_name.get(strategy_name)
            runtimes = runtimes_by_strategy.get(strategy_name, [])
            active_runtime = self._select_active_runtime(runtimes)
            alignment = self._alignment(
                deployment=deployment, active_runtime=active_runtime
            )
            if alignment["is_aligned"] is False:
                misaligned_count += 1
            families.append(
                {
                    "strategy_name": strategy_name,
                    "deployment": self._serialize_deployment(deployment),
                    "runtime": self._serialize_runtime(active_runtime, runtimes),
                    "alignment": alignment,
                    "governance": {
                        "approval_state": governance.approval_state
                        if governance is not None
                        else "UNKNOWN",
                        "autonomous_operation_allowed": governance.autonomous_operation_allowed
                        if governance is not None
                        else False,
                        "emergency_stop": governance.emergency_stop
                        if governance is not None
                        else False,
                    },
                }
            )

        counts = Counter(
            family["deployment"]["state"]
            for family in families
            if isinstance(family.get("deployment"), dict)
            and family["deployment"].get("state") is not None
        )
        return {
            "effective_autonomous_control_enabled": effective_autonomy,
            "configured_autonomous_control_enabled": self.settings.autonomous_control_enabled,
            "autonomy_override_active": control_state is not None
            and control_state.autonomous_control_override is not None,
            "autonomy_override_reason": control_state.override_reason
            if control_state is not None
            else None,
            "misaligned_count": misaligned_count,
            "counts": dict(counts),
            "families": families,
        }

    def _coverage_summary(self) -> dict[str, object]:
        tier1_entries = list(
            self.session.exec(
                select(WatchlistEntry)
                .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
            ).all()
        )
        tier1_entries.sort(
            key=lambda entry: (
                0 if entry.pinned else 1,
                -entry.priority_score,
                entry.assigned_at,
                entry.instrument,
            )
        )
        selected, pinned, capped, asset_usage = self._compute_streaming_plan(
            tier1_entries
        )
        promotion_requests = list(
            self.session.exec(
                select(PromotionRequest)
                .order_by(desc(PromotionRequest.updated_at))
                .limit(12)
            ).all()
        )
        promotion_counts = Counter(request.status for request in promotion_requests)
        allocator_events = list(
            self.session.exec(
                select(DomainEvent)
                .where(
                    DomainEvent.event_type.in_(
                        [
                            "strategy.trade_allocator_selected",
                            "strategy.trade_allocator_rejected",
                        ]
                    )
                )
                .order_by(desc(DomainEvent.created_at), desc(DomainEvent.id))
                .limit(20)
            ).all()
        )
        allocator_counts = Counter(event.event_type for event in allocator_events)
        allocator_reason_counts = Counter(
            str((event.payload_json or {}).get("reason_code") or "unknown")
            for event in allocator_events
        )
        return {
            "streaming": {
                "active_instruments": [
                    entry.instrument
                    for entry in tier1_entries
                    if entry.instrument in selected
                ],
                "desired_instruments": list(selected),
                "pinned_instruments": list(pinned),
                "capped_instruments": list(capped),
                "asset_class_usage": dict(asset_usage),
            },
            "promotions": {
                "pending_count": promotion_counts.get("PENDING", 0),
                "accepted_count": promotion_counts.get("ACCEPTED", 0),
                "rejected_count": promotion_counts.get("REJECTED", 0),
                "expired_count": promotion_counts.get("EXPIRED", 0),
            },
            "trade_allocator": {
                "selected_count": allocator_counts.get(
                    "strategy.trade_allocator_selected", 0
                ),
                "rejected_count": allocator_counts.get(
                    "strategy.trade_allocator_rejected", 0
                ),
                "reason_counts": dict(allocator_reason_counts),
            },
        }

    def _strategies(self) -> list[dict[str, object]]:
        executions = self.session.exec(
            select(Execution)
            .order_by(desc(Execution.last_transition_at), desc(Execution.id))
            .limit(250)
        ).all()
        intents = self.session.exec(
            select(TradeIntent)
            .order_by(desc(TradeIntent.updated_at), desc(TradeIntent.id))
            .limit(250)
        ).all()
        latest_execution_warning_by_strategy: dict[str, Execution] = {}
        for execution in executions:
            if execution.status not in {
                ExecutionStatus.FAILED.value,
                ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
            }:
                continue
            latest_execution_warning_by_strategy.setdefault(
                execution.strategy_name, execution
            )
        latest_intent_warning_by_strategy: dict[str, TradeIntent] = {}
        for intent in intents:
            if intent.state != TradeIntentState.REJECTED.value:
                continue
            latest_intent_warning_by_strategy.setdefault(intent.strategy_name, intent)

        runtimes = self.session.exec(select(StrategyRuntimeState)).all()
        running_by_strategy = {
            runtime.strategy_name for runtime in runtimes if runtime.status == "RUNNING"
        }
        summaries: list[dict[str, object]] = []
        for metadata in strategy_registry.list_metadata():
            execution_warning = latest_execution_warning_by_strategy.get(metadata.name)
            intent_warning = latest_intent_warning_by_strategy.get(metadata.name)
            warning_message = None
            if execution_warning is not None:
                warning_message = (
                    execution_warning.error_message or execution_warning.reason
                )
            elif intent_warning is not None:
                warning_message = intent_warning.decision_reason
            summaries.append(
                {
                    "name": metadata.name,
                    "status": "RUNNING"
                    if metadata.name in running_by_strategy
                    else "STOPPED",
                    "warning_message": warning_message,
                }
            )
        return summaries

    def _events(self, *, limit: int) -> list[dict[str, object]]:
        events = self.session.exec(
            select(DomainEvent)
            .order_by(desc(DomainEvent.created_at), desc(DomainEvent.id))
            .limit(limit)
        ).all()
        return [
            {
                "id": event.id or 0,
                "created_at": event.created_at,
                "event_type": event.event_type,
                "category": event.category,
                "severity": event.severity,
                "error_type": event.error_type,
                "source": event.source,
                "correlation_id": event.correlation_id,
                "runtime_id": event.runtime_id,
                "strategy_name": event.strategy_name,
                "instrument": event.instrument,
                "position_id": event.position_id,
                "trade_id": event.trade_id,
                "execution_id": event.execution_id,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "title": event.title,
                "message": event.message,
                "payload_json": event.payload_json,
            }
            for event in events
        ]

    @staticmethod
    def _select_active_runtime(
        runtimes: list[StrategyRuntimeState],
    ) -> StrategyRuntimeState | None:
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

    @staticmethod
    def _serialize_deployment(
        deployment: StrategyDeployment | None,
    ) -> dict[str, object] | None:
        if deployment is None:
            return None
        return {
            "state": deployment.state,
            "blocked_reason": deployment.blocked_reason,
            "degraded_reason": deployment.degraded_reason,
            "selected_instrument": deployment.selected_instrument,
            "selected_profile": deployment.selected_profile,
            "updated_at": deployment.updated_at,
        }

    @staticmethod
    def _serialize_runtime(
        active_runtime: StrategyRuntimeState | None,
        runtimes: list[StrategyRuntimeState],
    ) -> dict[str, object]:
        if active_runtime is None:
            return {
                "is_running": False,
                "active_instrument": None,
                "active_profile_name": None,
                "control_mode": None,
                "persisted_runtime_count": len(runtimes),
            }
        return {
            "is_running": True,
            "active_instrument": active_runtime.instrument,
            "active_profile_name": active_runtime.active_profile_name,
            "control_mode": active_runtime.control_mode,
            "persisted_runtime_count": len(runtimes),
        }

    @staticmethod
    def _alignment(
        *,
        deployment: StrategyDeployment | None,
        active_runtime: StrategyRuntimeState | None,
    ) -> dict[str, object]:
        if deployment is None:
            return {
                "is_aligned": None,
                "reason": "No deployment record exists for this strategy family yet.",
            }
        if deployment.state == "AUTO_DEPLOYED":
            if active_runtime is None:
                return {
                    "is_aligned": False,
                    "reason": "Deployment expects an autonomous runtime, but none is running.",
                }
            if active_runtime.control_mode != "AUTO":
                return {
                    "is_aligned": False,
                    "reason": "Deployment expects AUTO control mode, but the runtime is not autonomous.",
                }
            if active_runtime.instrument != deployment.selected_instrument:
                return {
                    "is_aligned": False,
                    "reason": "Runtime instrument differs from the deployed instrument.",
                }
            return {
                "is_aligned": True,
                "reason": "Deployment and runtime are aligned.",
            }
        if active_runtime is not None and deployment.state in {
            "BLOCKED",
            "AUTO_PAUSED",
            "EMERGENCY_STOPPED",
        }:
            return {
                "is_aligned": False,
                "reason": "Runtime is still active despite the deployment state requiring it to be stopped.",
            }
        return {
            "is_aligned": True,
            "reason": "Runtime state matches the deployment expectation.",
        }

    def _compute_streaming_plan(
        self,
        entries: list[WatchlistEntry],
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], dict[str, int]]:
        asset_budgets = {
            asset_class.upper(): budget
            for asset_class, budget in self.settings.ig_streaming_asset_class_slot_budgets.items()
        }
        asset_usage: defaultdict[str, int] = defaultdict(int)
        selected: list[str] = []
        pinned: list[str] = []
        capped: list[str] = []
        for entry in entries:
            asset_class = (entry.asset_class or "UNCLASSIFIED").upper()
            if entry.pinned:
                selected.append(entry.instrument)
                pinned.append(entry.instrument)
                asset_usage[asset_class] += 1
                continue
            if (
                self.settings.ig_streaming_max_instruments > 0
                and len(selected) >= self.settings.ig_streaming_max_instruments
            ):
                capped.append(entry.instrument)
                continue
            budget = asset_budgets.get(asset_class)
            if budget is not None and asset_usage[asset_class] >= budget:
                capped.append(entry.instrument)
                continue
            selected.append(entry.instrument)
            asset_usage[asset_class] += 1
        return tuple(selected), tuple(pinned), tuple(capped), dict(asset_usage)
