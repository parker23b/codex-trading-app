from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlmodel import Session, select

from app.core.broker import (
    BrokerExecutionSource,
    BrokerOrderStatus,
    BrokerSizingPrecision,
    OrderRequest,
)
from app.core.config import get_settings
from app.core.identifier_policy import project_identifier
from app.core.logging import get_logger
from app.core.signals import EntrySignal, ExitSignal, SignalCandidate, SignalStatus
from app.core.instrument_catalog import list_instruments
from app.core.runtime import runtime_manager
from app.models.strategy_deployment import StrategyDeployment
from app.models.trade import (
    Execution,
    ExecutionPhase,
    ExecutionStatus,
    Position,
    Trade,
    TradeIntent,
    TradeIntentState,
    clone_position,
    utc_now,
)
from app.strategies.registry import strategy_registry
from app.services.audit_event_recorder import (
    AuditEventPersistenceError,
    record_required_domain_event,
)
from app.services.trade_decision_service import (
    TradeDecisionResult,
    TradeDecisionService,
)
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.lifecycle_rules import EXECUTION_LEGACY_COMPATIBILITY_STATUSES
from app.services.market_status_service import MarketStatus, get_market_status_service
from app.services.operational_state_service import OperationalStateService
from app.services.runtime_state_service import RuntimeStateService
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.trade_service import TradeService

logger = get_logger(__name__)

AUDIT_PERSISTENCE_REQUIRED = "REQUIRED_DURABLE"
AUDIT_PERSISTENCE_BEST_EFFORT = "BEST_EFFORT_INFORMATIONAL"


AMBIGUOUS_BROKER_ORDER_STATUSES = {
    BrokerOrderStatus.ACKNOWLEDGED,
    BrokerOrderStatus.PENDING,
    BrokerOrderStatus.TIMED_OUT,
    BrokerOrderStatus.RATE_LIMITED,
    BrokerOrderStatus.UNKNOWN,
    BrokerOrderStatus.AMBIGUOUS,
}


class StrategyService:
    # Legacy execution statuses are read only so persisted older rows can still
    # exist for historical reads, but retries must create a new execution
    # attempt rather than rewriting compatibility-only rows.
    LEGACY_EXECUTION_COMPAT_STATUSES = {
        status.value for status in EXECUTION_LEGACY_COMPATIBILITY_STATUSES
    }
    RETRYABLE_EXECUTION_STATUSES = {
        ExecutionStatus.SUBMISSION_PENDING.value,
        ExecutionStatus.ORDER_SUBMITTED.value,
        ExecutionStatus.ORDER_ACKNOWLEDGED.value,
        ExecutionStatus.FILL_PARTIAL.value,
        ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
    }
    SAFE_CLOSE_RETRY_STATUSES = {
        ExecutionStatus.SUBMISSION_PENDING.value,
    }
    UNSAFE_ENTRY_RETRY_STATUSES = {
        ExecutionStatus.ORDER_SUBMITTED.value,
        ExecutionStatus.ORDER_ACKNOWLEDGED.value,
        ExecutionStatus.FILL_PARTIAL.value,
        ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
    }

    def __init__(self, session: Session | None = None):
        self.session = session
        self.settings = get_settings()
        self.event_service = domain_event_service
        self.health_service = get_health_service()
        self.market_status_service = get_market_status_service()
        self.trade_decision_service = (
            TradeDecisionService(session) if session is not None else None
        )
        self.runtime_state_service = (
            RuntimeStateService(session) if session is not None else None
        )

    def list_strategies(self) -> list[dict[str, object]]:
        if self.session is None:
            raise ValueError("A database session is required to list strategies.")

        trade_service = TradeService(self.session)
        trades = trade_service.list_trades()
        positions = trade_service.list_positions()
        executions = trade_service.list_executions(limit=250)
        intents = trade_service.list_trade_intents(limit=250)
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_intents = trade_service.list_trade_intents(
            limit=1000, date_from=today_start
        )
        today_intents_by_strategy: dict[str, list[TradeIntent]] = defaultdict(list)
        for intent in today_intents:
            today_intents_by_strategy[intent.strategy_name].append(intent)
        open_positions_by_strategy: dict[str, list] = defaultdict(list)
        for position in positions:
            open_positions_by_strategy[position.strategy_name].append(position)
        trades_by_strategy: dict[str, list[float]] = defaultdict(list)
        for trade in trades:
            trades_by_strategy[trade.strategy_name].append(trade.pnl)
        latest_execution_warning_by_key: dict[tuple[str, str], Execution] = {}
        for execution in executions:
            if execution.status not in {
                ExecutionStatus.FAILED.value,
                ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
            }:
                continue
            key = (execution.strategy_name, execution.instrument)
            if key not in latest_execution_warning_by_key:
                latest_execution_warning_by_key[key] = execution
        latest_decision_warning_by_key: dict[tuple[str, str], TradeIntent] = {}
        for intent in intents:
            if intent.state != TradeIntentState.REJECTED.value:
                continue
            key = (intent.strategy_name, intent.instrument)
            if key not in latest_decision_warning_by_key:
                latest_decision_warning_by_key[key] = intent

        strategies: list[dict[str, object]] = []
        governance_records = StrategyGovernanceService(
            self.session
        ).list_existing_strategies()
        governance_by_name = {
            record.strategy_name: record for record in governance_records
        }
        deployment_by_name = {
            deployment.strategy_name: deployment
            for deployment in self.session.exec(select(StrategyDeployment)).all()
        }
        runtimes_by_key = {}
        if self.runtime_state_service is not None:
            runtimes_by_key = {
                (runtime.strategy_name, runtime.instrument): runtime
                for runtime in self.runtime_state_service.list_runtimes()
            }
        for metadata in runtime_manager.list_registered_strategies():
            active_engines = runtime_manager.get_engines_for_strategy(metadata.name)
            primary_engine = active_engines[0][1] if active_engines else None
            strategy_positions = open_positions_by_strategy.get(metadata.name, [])
            strategy_pnls = trades_by_strategy.get(metadata.name, [])
            trade_count = len(strategy_pnls)
            win_count = len([pnl for pnl in strategy_pnls if pnl > 0])
            current_pnl = round(
                sum(position.unrealized_pnl or 0.0 for position in strategy_positions),
                2,
            )
            primary_instrument = (
                primary_engine.instrument
                if primary_engine
                else metadata.default_instrument
            )
            primary_warning = latest_execution_warning_by_key.get(
                (metadata.name, primary_instrument)
            )
            primary_decision_warning = latest_decision_warning_by_key.get(
                (metadata.name, primary_instrument)
            )
            primary_warning_message = None
            primary_warning_status = None
            if primary_warning is not None:
                primary_warning_message = (
                    primary_warning.error_message or primary_warning.reason
                )
                primary_warning_status = primary_warning.status
            elif primary_decision_warning is not None:
                primary_warning_message = primary_decision_warning.decision_reason
                primary_warning_status = primary_decision_warning.state
            governance = governance_by_name.get(metadata.name)
            deployment = deployment_by_name.get(metadata.name)
            primary_runtime = runtimes_by_key.get((metadata.name, primary_instrument))
            strategy_today_intents = today_intents_by_strategy.get(metadata.name, [])
            promoted_today_count = len(
                [
                    intent
                    for intent in strategy_today_intents
                    if intent.state
                    in {
                        TradeIntentState.APPROVED.value,
                        TradeIntentState.SUBMITTED.value,
                        TradeIntentState.ACKNOWLEDGED.value,
                        TradeIntentState.FILLED.value,
                        TradeIntentState.POSITION_OPENED.value,
                    }
                ]
            )
            blocked_today_count = len(
                [
                    intent
                    for intent in strategy_today_intents
                    if intent.state == TradeIntentState.REJECTED.value
                ]
            )
            active_parameter_values = (
                primary_runtime.parameters
                if primary_runtime is not None and primary_runtime.parameters
                else {
                    parameter.key: parameter.value for parameter in metadata.parameters
                }
            )
            price_snapshot = (
                self._resolve_price_snapshot(
                    primary_instrument,
                    strategy_positions[0].current_price if strategy_positions else None,
                )
                if primary_engine or strategy_positions
                else None
            )
            strategies.append(
                {
                    "name": metadata.name,
                    "description": metadata.description,
                    "instrument": primary_instrument,
                    "status": "RUNNING" if active_engines else "STOPPED",
                    "current_pnl": current_pnl,
                    "last_price": price_snapshot["price"] if price_snapshot else None,
                    "price_status": price_snapshot["status"]
                    if price_snapshot
                    else "STOPPED",
                    "price_error": price_snapshot["error"] if price_snapshot else None,
                    "last_price_updated_at": price_snapshot["updated_at"]
                    if price_snapshot
                    else None,
                    "trade_count": trade_count,
                    "win_rate": round((win_count / trade_count) * 100, 2)
                    if trade_count
                    else 0.0,
                    "account_type": self.settings.broker_mode,
                    "position_size": metadata.position_size,
                    "risk_per_trade": metadata.risk_per_trade,
                    "supported_asset_classes": list(metadata.supported_asset_classes),
                    "available_profiles": [
                        profile.name for profile in metadata.parameter_profiles
                    ],
                    "governance_approval_state": governance.approval_state
                    if governance is not None
                    else "UNKNOWN",
                    "autonomous_operation_allowed": (
                        governance.autonomous_operation_allowed
                        if governance is not None
                        else False
                    ),
                    "authorized": (
                        governance.approval_state == "APPROVED"
                        and governance.autonomous_operation_allowed
                        and not governance.emergency_stop
                        if governance is not None
                        else False
                    ),
                    "emergency_stop": governance.emergency_stop
                    if governance is not None
                    else False,
                    "deployment_state": deployment.state
                    if deployment is not None
                    else "UNASSIGNED",
                    "deployment_profile": deployment.selected_profile
                    if deployment is not None
                    else None,
                    "deployment_parameters": deployment.selected_profile_parameters
                    if deployment is not None
                    else {},
                    "deployment_instrument": deployment.selected_instrument
                    if deployment is not None
                    else None,
                    "deployment_reason": (
                        deployment.blocked_reason
                        or deployment.degraded_reason
                        or deployment.suitability_reason
                        if deployment is not None
                        else None
                    ),
                    "active_instruments": [
                        engine.instrument for _, engine in active_engines
                    ],
                    "evaluating_instrument_count": len(
                        {engine.instrument for _, engine in active_engines}
                    ),
                    "candidates_generated_today": len(strategy_today_intents),
                    "candidates_promoted_today": promoted_today_count,
                    "candidates_blocked_today": blocked_today_count,
                    "active_runtime_count": len(active_engines),
                    "open_position_count": len(strategy_positions),
                    "warning_message": primary_warning_message,
                    "warning_instrument": (
                        primary_warning.instrument
                        if primary_warning is not None
                        else primary_decision_warning.instrument
                        if primary_decision_warning is not None
                        else None
                    ),
                    "warning_status": primary_warning_status,
                    "active_runtimes": [
                        {
                            "strategy_name": metadata.name,
                            "instrument": engine.instrument,
                            "runtime_key": f"{metadata.name}:{engine.instrument}",
                            "has_open_position": engine.current_position is not None,
                            "broker_reference": project_identifier(
                                engine.current_position.broker_reference,
                                kind="broker_reference",
                            )
                            if engine.current_position
                            else None,
                            "direction": engine.current_position.direction
                            if engine.current_position
                            else None,
                            "current_price": engine.current_position.current_price
                            if engine.current_position
                            else None,
                            "unrealized_pnl": engine.current_position.unrealized_pnl
                            if engine.current_position
                            else None,
                            "recovery_state": (
                                runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                ).recovery_state
                                if runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                )
                                is not None
                                else "EPHEMERAL"
                            ),
                            "runtime_mode": (
                                runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                ).runtime_mode
                                if runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                )
                                is not None
                                else getattr(engine, "runtime_mode", "NORMAL")
                            ),
                            "control_mode": (
                                runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                ).control_mode
                                if runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                )
                                is not None
                                else "EPHEMERAL"
                            ),
                            "deployment_id": (
                                runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                ).deployment_id
                                if runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                )
                                is not None
                                else None
                            ),
                            "recovery_reason": (
                                runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                ).recovery_reason
                                if runtimes_by_key.get(
                                    (metadata.name, engine.instrument)
                                )
                                is not None
                                else None
                            ),
                        }
                        for _, engine in active_engines
                    ],
                    "open_positions": [
                        {
                            "broker_reference": project_identifier(
                                position.broker_reference,
                                kind="broker_reference",
                            ),
                            "instrument": position.instrument,
                            "direction": position.direction,
                            "size": position.size,
                            "open_price": position.open_price,
                            "current_price": position.current_price,
                            "unrealized_pnl": position.unrealized_pnl,
                            "risk_percent": position.risk_percent,
                        }
                        for position in strategy_positions
                    ],
                    "persisted_runtimes": [
                        {
                            "runtime_id": project_identifier(
                                runtime.runtime_id,
                                kind="runtime_id",
                            ),
                            "instrument": runtime.instrument,
                            "status": runtime.status,
                            "recovery_state": runtime.recovery_state,
                            "recovery_reason": runtime.recovery_reason,
                            "last_heartbeat_at": runtime.last_heartbeat_at,
                            "last_price_seen": runtime.last_price_seen,
                            "last_price_seen_at": runtime.last_price_seen_at,
                            "control_mode": runtime.control_mode,
                            "runtime_mode": runtime.runtime_mode,
                            "deployment_id": runtime.deployment_id,
                            "active_profile_name": runtime.active_profile_name,
                            "parameters": runtime.parameters,
                            "auto_resume": runtime.auto_resume,
                        }
                        for key, runtime in runtimes_by_key.items()
                        if key[0] == metadata.name
                    ],
                    "instrument_options": list_instruments(),
                    "parameters": [
                        {
                            "key": parameter.key,
                            "label": parameter.label,
                            "value": active_parameter_values.get(
                                parameter.key, parameter.value
                            ),
                            "step": parameter.step,
                        }
                        for parameter in metadata.parameters
                    ],
                }
            )
        return strategies

    def start_strategy(
        self,
        strategy_name: str,
        instrument: str,
        *,
        control_mode: str = "MANUAL",
        runtime_mode: str | None = None,
        deployment_id: int | None = None,
        profile_name: str | None = None,
        strategy_parameters: dict[str, object] | None = None,
        startup_context: dict[str, object] | None = None,
    ) -> None:
        # Service-layer start is the authoritative path for runtime startup.
        # It resolves persisted runtime mode and deployment/open-risk context
        # before the engine is created, so callers should not bypass it by
        # invoking `runtime_manager.start(...)` directly.
        previous_runtime = (
            self.runtime_state_service.get_runtime(strategy_name, instrument)
            if self.runtime_state_service is not None
            else None
        )
        resolved_runtime_mode = self._resolve_runtime_start_mode(
            strategy_name=strategy_name,
            instrument=instrument,
            requested_runtime_mode=runtime_mode,
        )
        engine = runtime_manager.start(
            strategy_name=strategy_name,
            instrument=instrument,
            profile_name=profile_name,
            strategy_parameters=strategy_parameters,
            startup_context=startup_context,
            runtime_mode=resolved_runtime_mode,
            startup_source="strategy_service.start_strategy",
        )
        if self.runtime_state_service is not None:
            self.runtime_state_service.sync_engine_state(
                strategy_name=strategy_name,
                instrument=instrument,
                status="RUNNING",
                recovery_state="RUNNING",
                control_mode=control_mode,
                runtime_mode=resolved_runtime_mode,
                deployment_id=deployment_id,
                active_profile_name=engine.active_profile_name,
                parameters=engine.strategy_parameters,
                startup_context=engine.startup_context,
                last_price_seen=runtime_manager.get_last_price(instrument),
                last_price_seen_at=runtime_manager.get_last_price_updated_at(
                    instrument
                ),
                current_position=engine.current_position,
            )
        self._record_domain_event(
            audit_persistence=AUDIT_PERSISTENCE_REQUIRED,
            event_type="strategy.runtime_started",
            category="strategy",
            severity="info",
            source="strategy_service.start_strategy",
            title="Strategy runtime started",
            message=f"{strategy_name} started on {instrument}.",
            correlation_id=str((engine.startup_context or {}).get("correlation_id"))
            if (engine.startup_context or {}).get("correlation_id") is not None
            else None,
            runtime_id=engine.runtime_id,
            strategy_name=strategy_name,
            instrument=instrument,
            actor_type="service",
            actor_id="strategy_service",
            payload_json={
                "previous_state": (
                    previous_runtime.status
                    if previous_runtime is not None
                    else "NOT_RUNNING"
                ),
                "new_state": "RUNNING",
                "status": "RUNNING",
                "control_mode": control_mode,
                "runtime_mode": resolved_runtime_mode,
                "deployment_id": deployment_id,
                "active_profile_name": engine.active_profile_name,
                "strategy_parameters": engine.strategy_parameters,
                "startup_context": engine.startup_context,
            },
        )
        self._refresh_paused_strategy_count()

    def _resolve_runtime_start_mode(
        self,
        *,
        strategy_name: str,
        instrument: str,
        requested_runtime_mode: str | None,
    ) -> str:
        # Default starts must never silently erase persisted EXITS_ONLY or
        # unmanaged-risk context by normalizing back to NORMAL.
        if self.session is None or self.runtime_state_service is None:
            return requested_runtime_mode or "NORMAL"

        deployment = self.session.exec(
            select(StrategyDeployment).where(
                StrategyDeployment.strategy_name == strategy_name
            )
        ).first()
        if (
            deployment is not None
            and deployment.open_risk_management_state == "UNMANAGED_OPEN_RISK"
            and requested_runtime_mode in {None, "NORMAL"}
        ):
            raise ValueError(
                f"Cannot start {strategy_name} on {instrument} in NORMAL mode while open risk is marked UNMANAGED_OPEN_RISK."
            )

        if requested_runtime_mode is not None:
            return requested_runtime_mode

        persisted_runtime = self.runtime_state_service.get_runtime(
            strategy_name, instrument
        )
        if persisted_runtime is not None and persisted_runtime.runtime_mode in {
            "NORMAL",
            "EXITS_ONLY",
        }:
            return persisted_runtime.runtime_mode
        if (
            deployment is not None
            and deployment.open_risk_management_state == "EXITS_ONLY"
        ):
            return "EXITS_ONLY"
        return "NORMAL"

    def set_runtime_mode(
        self,
        *,
        strategy_name: str,
        instrument: str,
        runtime_mode: str,
        recovery_reason: str | None = None,
    ) -> None:
        engine = runtime_manager.get_engine(strategy_name, instrument)
        if engine is None:
            raise ValueError(
                f"No active engine for strategy '{strategy_name}' on '{instrument}'."
            )
        previous_runtime_mode = getattr(engine, "runtime_mode", None)
        engine.runtime_mode = runtime_mode
        persisted_runtime = None
        if self.runtime_state_service is not None:
            persisted_runtime = self.runtime_state_service.sync_engine_state(
                strategy_name=strategy_name,
                instrument=instrument,
                status="RUNNING",
                recovery_state="RUNNING",
                runtime_mode=runtime_mode,
                last_price_seen=runtime_manager.get_last_price(instrument),
                last_price_seen_at=runtime_manager.get_last_price_updated_at(
                    instrument
                ),
                current_position=engine.current_position,
                recovery_reason=recovery_reason,
            )
        self._record_domain_event(
            audit_persistence=AUDIT_PERSISTENCE_REQUIRED,
            event_type="strategy.runtime_mode_changed",
            category="strategy",
            severity="warning" if runtime_mode == "EXITS_ONLY" else "info",
            source="strategy_service.set_runtime_mode",
            title="Strategy runtime mode changed",
            message=f"{strategy_name} runtime on {instrument} changed to {runtime_mode}.",
            runtime_id=engine.runtime_id,
            strategy_name=strategy_name,
            instrument=instrument,
            actor_type="service",
            actor_id="strategy_service",
            payload_json={
                "previous_runtime_mode": previous_runtime_mode,
                "new_runtime_mode": runtime_mode,
                "runtime_mode": runtime_mode,
                "control_mode": (
                    persisted_runtime.control_mode
                    if persisted_runtime is not None
                    else None
                ),
                "reason": recovery_reason,
            },
        )

    def stop_strategy(
        self,
        instrument: str | None = None,
        strategy_name: str | None = None,
        *,
        stop_context: dict[str, object] | None = None,
        stop_reason: str | None = None,
    ) -> list[dict[str, object]]:
        stopped_engines = runtime_manager.stop(
            instrument=instrument, strategy_name=strategy_name
        )
        stopped_runtime_details = [
            {
                "runtime_id": engine.runtime_id,
                "strategy_name": engine.strategy.name,
                "instrument": engine.instrument,
                "control_mode": getattr(engine, "control_mode", None),
                "previous_runtime_mode": getattr(engine, "runtime_mode", None),
                "current_position_broker_reference": (
                    engine.current_position.broker_reference
                    if getattr(engine, "current_position", None) is not None
                    else None
                ),
            }
            for engine in stopped_engines
        ]
        if self.runtime_state_service is not None:
            for engine in stopped_engines:
                self.runtime_state_service.mark_stopped(engine.runtime_id)
        normalized_stop_context = dict(stop_context or {})
        for engine, runtime_detail in zip(
            stopped_engines, stopped_runtime_details, strict=True
        ):
            self._record_domain_event(
                audit_persistence=AUDIT_PERSISTENCE_REQUIRED,
                event_type="strategy.runtime_stopped",
                category="strategy",
                severity="info",
                source="strategy_service.stop_strategy",
                title="Strategy runtime stopped",
                message=f"{engine.strategy.name} stopped on {engine.instrument}.",
                correlation_id=str(normalized_stop_context.get("correlation_id"))
                if normalized_stop_context.get("correlation_id") is not None
                else None,
                runtime_id=engine.runtime_id,
                strategy_name=engine.strategy.name,
                instrument=engine.instrument,
                actor_type="service",
                actor_id="strategy_service",
                payload_json={
                    "previous_state": "RUNNING",
                    "new_state": "STOPPED",
                    "status": "STOPPED",
                    "control_mode": runtime_detail["control_mode"],
                    "previous_runtime_mode": runtime_detail["previous_runtime_mode"],
                    "new_runtime_mode": "STOPPED",
                    "current_position_broker_reference": runtime_detail[
                        "current_position_broker_reference"
                    ],
                    "reason": stop_reason,
                    "stop_context": normalized_stop_context,
                },
            )
        self._refresh_paused_strategy_count()
        return stopped_runtime_details

    def _record_domain_event(
        self,
        *,
        audit_persistence: str = AUDIT_PERSISTENCE_REQUIRED,
        **kwargs: object,
    ) -> None:
        payload = dict(kwargs.get("payload_json") or {})
        payload.setdefault("audit_persistence", audit_persistence)
        payload.setdefault(
            "audit_role",
            (
                "candidate_signal"
                if audit_persistence == AUDIT_PERSISTENCE_BEST_EFFORT
                else "lifecycle_or_operational_evidence"
            ),
        )
        kwargs["payload_json"] = payload
        if audit_persistence == AUDIT_PERSISTENCE_BEST_EFFORT:
            self.event_service.record_event(**kwargs)
            return
        if self.session is None:
            raise RuntimeError(
                "A database session is required for durable strategy audit events."
            )
        record_required_domain_event(session=self.session, **kwargs)

    def _refresh_paused_strategy_count(self) -> None:
        if self.runtime_state_service is None:
            self.health_service.set_paused_strategies(0)
            return
        paused_count = len(
            [
                runtime
                for runtime in self.runtime_state_service.list_runtimes()
                if runtime.status == "RUNNING" and runtime.recovery_state != "RUNNING"
            ]
        )
        self.health_service.set_paused_strategies(paused_count)

    @staticmethod
    def _entry_execution_policy_block(
        *, session: Session, engine
    ) -> tuple[str, str, dict[str, object]] | None:
        # This late guard intentionally mirrors the admission-time policy.
        # It must remain in place even if earlier layers already blocked
        # entries, because runtime mode or operational eligibility can change
        # after admission but before broker submission.
        runtime_mode = str(getattr(engine, "runtime_mode", "NORMAL") or "NORMAL")
        if runtime_mode in {"EXITS_ONLY", "STOPPED"}:
            return (
                "entry_execution_blocked_runtime_mode_changed",
                f"Entry execution blocked because runtime mode is {runtime_mode}.",
                {"runtime_mode": runtime_mode},
            )
        operational_state = OperationalStateService(session).get_summary()
        if not operational_state.entry_eligible:
            return (
                "entry_execution_blocked_operational_policy",
                f"Entry execution blocked by operational policy: {operational_state.entry_block_reason}.",
                {
                    "operational_policy": operational_state.model_dump(mode="json"),
                    "runtime_mode": runtime_mode,
                },
            )
        return None

    def process_price_update(
        self,
        instrument: str,
        price: float,
        *,
        bid: float | None = None,
        ask: float | None = None,
        high: float | None = None,
        low: float | None = None,
        market_status: str | None = None,
        tradable: bool | None = None,
        received_at: datetime | None = None,
    ) -> None:
        # Ownership chain:
        # 1. TradingEngine emits raw alpha signals.
        # 2. TradeDecisionService persists PROPOSED TradeIntents and is the only
        #    authority that can move them to APPROVED / REJECTED.
        # 3. StrategyService only executes already-admitted intents and mirrors
        #    lifecycle changes into execution, position, and trade records.
        candidates = self.evaluate_price_update(
            instrument=instrument,
            price=price,
            bid=bid,
            ask=ask,
            high=high,
            low=low,
            market_status=market_status,
            tradable=tradable,
            received_at=received_at,
            source_tier="TIER1",
        )
        decisions = self.decide_signal_candidates(candidates, received_at=received_at)
        self.orchestrate_trade_decisions(
            decisions,
            price=price,
            bid=bid,
            ask=ask,
            received_at=received_at,
        )

    def evaluate_price_update(
        self,
        instrument: str,
        price: float,
        *,
        bid: float | None = None,
        ask: float | None = None,
        high: float | None = None,
        low: float | None = None,
        market_status: str | None = None,
        tradable: bool | None = None,
        received_at: datetime | None = None,
        source_tier: str = "TIER1",
    ) -> list[SignalCandidate]:
        if self.session is None:
            raise ValueError(
                "A database session is required to evaluate price updates."
            )

        update_results = runtime_manager.process_price_update(
            instrument=instrument,
            price=price,
            bid=bid,
            ask=ask,
            high=high,
            low=low,
            market_status=market_status,
            tradable=tradable,
            received_at=received_at,
        )
        if self.runtime_state_service is not None:
            for update_result in update_results:
                self.runtime_state_service.sync_engine_state(
                    strategy_name=update_result.engine.strategy.name,
                    instrument=update_result.engine.instrument,
                    status="RUNNING",
                    recovery_state="RUNNING",
                    runtime_mode=update_result.engine.runtime_mode,
                    last_price_seen=price,
                    last_price_seen_at=received_at or datetime.now(UTC),
                    current_position=update_result.engine.current_position,
                    current_position_broker_reference=(
                        update_result.engine.current_position.broker_reference
                        if update_result.engine.current_position is not None
                        else None
                    ),
                )
        candidates: list[SignalCandidate] = []
        for update_result in update_results:
            candidates.append(
                SignalCandidate(
                    strategy_name=update_result.engine.strategy.name,
                    instrument=update_result.engine.instrument,
                    signal=update_result.signal,
                    engine=update_result.engine,
                    source_tier=source_tier,
                    metadata=strategy_registry.get_metadata(
                        update_result.engine.strategy.name
                    ),
                )
            )
        return candidates

    def decide_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[TradeDecisionResult]:
        if self.session is None or self.trade_decision_service is None:
            raise ValueError(
                "A database session is required to decide signal candidates."
            )
        return self.trade_decision_service.decide_signal_candidates(
            candidates, received_at=received_at
        )

    def allocate_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[SignalCandidate]:
        """
        Backward-compatible wrapper around the centralized decision service.

        Raw strategy signals become `TradeIntent` proposals inside
        `TradeDecisionService`. This method now only returns the admitted raw
        candidates for callers that still expect the previous shape.
        """

        decisions = self.decide_signal_candidates(candidates, received_at=received_at)
        return [decision.candidate for decision in decisions if decision.admitted]

    def orchestrate_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        price: float,
        bid: float | None = None,
        ask: float | None = None,
        received_at: datetime | None = None,
    ) -> None:
        decisions = self.decide_signal_candidates(candidates, received_at=received_at)
        self.orchestrate_trade_decisions(
            decisions,
            price=price,
            bid=bid,
            ask=ask,
            received_at=received_at,
        )

    def orchestrate_trade_decisions(
        self,
        decisions: list[TradeDecisionResult],
        *,
        price: float,
        bid: float | None = None,
        ask: float | None = None,
        received_at: datetime | None = None,
    ) -> None:
        if self.session is None:
            raise ValueError(
                "A database session is required to orchestrate trade decisions."
            )

        trade_service = TradeService(self.session)

        for decision in decisions:
            candidate = decision.candidate
            engine = candidate.engine
            intent = decision.intent
            existing_position = trade_service.get_open_position(
                candidate.instrument,
                strategy_name=engine.strategy.name,
                broker_reference=(
                    getattr(
                        getattr(engine, "current_position", None),
                        "broker_reference",
                        None,
                    )
                ),
            )
            signal = candidate.signal

            if isinstance(signal, EntrySignal):
                # The raw signal became a durable proposal in TradeDecisionService.
                # and only materialize execution rows once an approved intent is
                # actually entering broker-submission orchestration.
                if decision.admitted and intent is not None:
                    late_block = self._entry_execution_policy_block(
                        session=self.session, engine=engine
                    )
                    if late_block is not None:
                        code, reason, details = late_block
                        trade_service.transition_trade_intent(
                            intent,
                            state=TradeIntentState.FAILED,
                            decision_reason_code=code,
                            decision_reason=reason,
                            details={
                                **StrategyService._allocation_outcome_update(
                                    stage="execution_policy_blocked",
                                    final_status=TradeIntentState.FAILED.value,
                                    hard_risk_passed=True,
                                    execution_blocked=True,
                                ),
                                "execution_policy_block": details,
                            },
                        )
                        continue
                    execution, should_submit = self._prepare_execution(
                        trade_service=trade_service,
                        trade_intent_id=intent.id,
                        strategy_name=signal.strategy_name,
                        instrument=signal.instrument,
                        phase=ExecutionPhase.ENTRY.value,
                        signal_time=signal.signal_at,
                        requested_size=signal.size,
                        requested_price=signal.observed_price,
                        reason="Execution attempt created for approved entry intent",
                        details={
                            "action_key": self._entry_action_key(signal),
                            "runtime_authority": self._runtime_authority_context(
                                engine
                            ),
                            "direction": signal.direction.value,
                            "market_status": signal.market_status,
                            "tradable": signal.tradable,
                            "trade_intent_id": intent.id,
                            "decision_reason_code": intent.decision_reason_code,
                            "decision_reason": intent.decision_reason,
                            "allocated_size": intent.allocated_size,
                            "allocated_risk_percent": intent.allocated_risk_percent,
                            **(intent.details or {}),
                        },
                    )
                    if not should_submit:
                        continue
                    self._record_domain_event(
                        audit_persistence=AUDIT_PERSISTENCE_BEST_EFFORT,
                        event_type="strategy.entry_candidate",
                        category="strategy",
                        severity="info",
                        source="strategy_service.process_price_update",
                        title="Strategy produced entry candidate",
                        message=f"{signal.strategy_name} proposed an entry on {signal.instrument}.",
                        correlation_id=execution.client_request_id,
                        strategy_name=signal.strategy_name,
                        instrument=signal.instrument,
                        execution_id=execution.id,
                        actor_type="service",
                        actor_id="strategy_service",
                        payload_json={
                            "trade_intent_id": intent.id,
                            "direction": signal.direction.value,
                            "observed_price": signal.observed_price,
                            "size": signal.size,
                            "market_status": signal.market_status,
                            "tradable": signal.tradable,
                            "source_tier": candidate.source_tier,
                        },
                        created_at=signal.signal_at,
                    )
                    try:
                        created_position = self._execute_entry_signal(
                            engine=engine,
                            signal=signal,
                            intent=intent,
                            trade_service=trade_service,
                            execution=execution,
                        )
                    except Exception as exc:
                        engine.current_position = None
                        engine.strategy.on_entry_failed()
                        if intent.state != TradeIntentState.POSITION_OPENED.value:
                            latest_execution = (
                                trade_service.get_latest_execution_for_trade_intent(
                                    intent.id or 0
                                )
                                if intent.id is not None
                                else execution
                            )
                            preserve_ambiguous_broker_state = (
                                latest_execution is not None
                                and latest_execution.status
                                == ExecutionStatus.NEEDS_MANUAL_REVIEW.value
                                and intent.state
                                in {
                                    TradeIntentState.SUBMITTED.value,
                                    TradeIntentState.ACKNOWLEDGED.value,
                                    TradeIntentState.PARTIALLY_FILLED.value,
                                }
                            )
                            if preserve_ambiguous_broker_state:
                                logger.exception(
                                    "Entry execution needs manual review",
                                    extra={
                                        "strategy": engine.strategy.name,
                                        "instrument": engine.instrument,
                                        "error": str(exc),
                                    },
                                )
                                continue
                            execution_stage = "execution_failed"
                            fill_status = None
                            if (
                                latest_execution is not None
                                and latest_execution.status
                                == ExecutionStatus.FILL_PARTIAL.value
                            ):
                                execution_stage = "partial_fill_requires_review"
                                fill_status = ExecutionStatus.FILL_PARTIAL.value
                            elif (
                                latest_execution is not None
                                and latest_execution.status
                                == ExecutionStatus.FAILED.value
                            ):
                                execution_stage = "execution_failed"
                            trade_service.transition_trade_intent(
                                intent,
                                state=TradeIntentState.FAILED,
                                decision_reason_code="execution_failed",
                                decision_reason=str(exc),
                                details=StrategyService._allocation_outcome_update(
                                    stage=execution_stage,
                                    final_status=TradeIntentState.FAILED.value,
                                    hard_risk_passed=True,
                                    execution_submitted=True,
                                    execution_blocked=True,
                                    fill_status=fill_status,
                                ),
                            )
                        logger.exception(
                            "Entry execution failed",
                            extra={
                                "strategy": engine.strategy.name,
                                "instrument": engine.instrument,
                                "error": str(exc),
                            },
                        )
                    else:
                        if self.runtime_state_service is not None:
                            self.runtime_state_service.sync_engine_state(
                                strategy_name=engine.strategy.name,
                                instrument=engine.instrument,
                                status="RUNNING",
                                recovery_state="RUNNING",
                                runtime_mode=engine.runtime_mode,
                                last_price_seen=price,
                                last_price_seen_at=received_at or datetime.now(UTC),
                                current_position=created_position,
                                current_position_broker_reference=created_position.broker_reference,
                            )
                else:
                    engine.current_position = None

            if engine.current_position is not None:
                existing_position = trade_service.get_open_position(
                    candidate.instrument,
                    strategy_name=engine.strategy.name,
                    broker_reference=engine.current_position.broker_reference,
                )

                risk_percent = 0.0
                current_position_risk = getattr(
                    engine.current_position, "risk_percent", None
                )
                if current_position_risk is not None:
                    risk_percent = current_position_risk
                mark_price = self._mark_price(
                    direction=engine.current_position.direction,
                    price=price,
                    bid=bid,
                    ask=ask,
                )
                unrealized_pnl = self._calculate_open_pnl(
                    direction=engine.current_position.direction,
                    open_price=engine.current_position.open_price,
                    current_price=mark_price,
                    size=engine.current_position.size,
                )
                if existing_position is None:
                    engine.current_position.current_price = mark_price
                    engine.current_position.unrealized_pnl = round(unrealized_pnl, 2)
                    engine.current_position.risk_percent = risk_percent
                    engine.current_position.reason = (
                        f"{engine.strategy.name} signal active"
                    )
                    if isinstance(engine.current_position, Position):
                        trade_service.record_broker_position(engine.current_position)
                else:
                    trade_service.update_position_analytics(
                        existing_position,
                        current_price=mark_price,
                        unrealized_pnl=unrealized_pnl,
                        risk_percent=risk_percent,
                        pnl=unrealized_pnl,
                    )
            elif existing_position is not None:
                mark_price = self._mark_price(
                    direction=existing_position.direction,
                    price=price,
                    bid=bid,
                    ask=ask,
                )
                unrealized_pnl = self._calculate_open_pnl(
                    direction=existing_position.direction,
                    open_price=existing_position.open_price,
                    current_price=mark_price,
                    size=existing_position.size,
                )
                trade_service.update_position_analytics(
                    existing_position,
                    current_price=mark_price,
                    unrealized_pnl=unrealized_pnl,
                )

            if isinstance(signal, ExitSignal):
                if not decision.admitted or intent is None:
                    continue
                execution, should_submit = self._prepare_execution(
                    trade_service=trade_service,
                    trade_intent_id=intent.id,
                    strategy_name=signal.strategy_name,
                    instrument=signal.instrument,
                    phase=ExecutionPhase.CLOSE.value,
                    signal_time=signal.signal_at,
                    requested_size=signal.position.size
                    if signal.position is not None
                    else None,
                    requested_price=signal.observed_price,
                    reason="Execution attempt created for admissible close intent",
                    broker_reference=signal.position.broker_reference
                    if signal.position is not None
                    else None,
                    local_position_id=signal.position.id
                    if signal.position is not None
                    else None,
                    details={
                        "action_key": self._close_action_key(signal),
                        "runtime_authority": self._runtime_authority_context(engine),
                        "market_status": signal.market_status,
                        "tradable": signal.tradable,
                        "trade_intent_id": intent.id,
                        "close_reason_code": intent.close_reason_code,
                        "close_reason": intent.close_reason,
                    },
                )
                if not should_submit:
                    continue
                    self._record_domain_event(
                        audit_persistence=AUDIT_PERSISTENCE_BEST_EFFORT,
                        event_type="strategy.exit_candidate",
                        category="strategy",
                        severity="info",
                        source="strategy_service.process_price_update",
                        title="Strategy produced exit candidate",
                        message=f"{signal.strategy_name} proposed an exit on {signal.instrument}.",
                        correlation_id=execution.client_request_id,
                        strategy_name=signal.strategy_name,
                        instrument=signal.instrument,
                        position_id=signal.position.id
                        if signal.position is not None
                        else None,
                        execution_id=execution.id,
                        actor_type="service",
                        actor_id="strategy_service",
                        payload_json={
                            "trade_intent_id": intent.id,
                            "observed_price": signal.observed_price,
                            "market_status": signal.market_status,
                            "tradable": signal.tradable,
                            "broker_reference": signal.position.broker_reference
                            if signal.position is not None
                            else None,
                            "source_tier": candidate.source_tier,
                        },
                        created_at=signal.signal_at,
                    )
                try:
                    trade = self._execute_exit_signal(
                        engine=engine,
                        signal=signal,
                        intent=intent,
                        trade_service=trade_service,
                        execution=execution,
                    )
                except Exception as exc:
                    if intent.state not in {
                        TradeIntentState.CLOSED.value,
                        TradeIntentState.CLOSE_REQUESTED.value,
                    }:
                        trade_service.transition_trade_intent(
                            intent,
                            state=TradeIntentState.FAILED,
                            close_reason_code="execution_failed",
                            close_reason=str(exc),
                        )
                    continue
                trade.outcome = "win" if trade.pnl > 0 else "loss"
                allocation_risk_amount = trade.entry_risk_amount
                if intent is not None:
                    if not allocation_risk_amount:
                        allocation_risk_amount = (
                            intent.fill_derived_risk_amount
                            or intent.submitted_risk_amount
                            or intent.estimated_risk_amount
                            or ((intent.details or {}).get("allocation") or {}).get(
                                "risk_amount"
                            )
                        )
                risk_budget = float(allocation_risk_amount or 0.0)
                if risk_budget <= 0:
                    risk_budget = max(abs(trade.open_price * trade.size), 1.0)
                trade.r_multiple = round(trade.pnl / risk_budget, 2)
                trade.reason = f"{trade.strategy_name} exit triggered"
                existing_position = trade_service.get_open_position(
                    candidate.instrument,
                    strategy_name=trade.strategy_name,
                    broker_reference=trade.broker_reference,
                )
                if existing_position is not None:
                    closed_position = trade_service.close_position(
                        existing_position,
                        close_price=trade.close_price,
                        close_time=trade.close_time,
                        pnl=trade.pnl,
                        broker_sync_status=(
                            "CONFIRMED"
                            if trade.close_execution_source
                            == BrokerExecutionSource.BROKER_CONFIRMED.value
                            else str(
                                trade.close_execution_source
                                or BrokerExecutionSource.BROKER_CONFIRMED.value
                            )
                        ),
                        close_execution_source=trade.close_execution_source,
                        broker_confirmed_at=trade.close_time,
                    )
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.CLOSE_CONFIRMED,
                        trade_intent_id=intent.id,
                        client_request_id=execution.client_request_id,
                        local_position_id=closed_position.id,
                        completed_at=trade.close_time,
                        average_fill_price=trade.close_price,
                        filled_size=trade.size,
                        reason="Position close confirmed",
                    )
                persisted_trade = trade_service.record_trade(trade)
                trade_service.transition_trade_intent(
                    intent,
                    state=TradeIntentState.CLOSED,
                    trade_id=persisted_trade.id,
                    close_broker_reference=trade.close_broker_reference,
                    average_fill_price=trade.close_price,
                    filled_size=trade.size,
                    close_reason_code="strategy_exit",
                    close_reason=trade.reason or "Strategy exit confirmed.",
                    completed_at=trade.close_time,
                    closed_at=trade.close_time,
                    details={
                        **StrategyService._allocation_outcome_update(
                            stage="trade_closed",
                            final_status=TradeIntentState.CLOSED.value,
                            hard_risk_passed=True,
                            execution_submitted=True,
                            fill_status=ExecutionStatus.FILL_FULL.value,
                        ),
                        "risk_tracking": {
                            "reservation_owner": "TRADE",
                            "risk_state": "closed_trade",
                        },
                    },
                )
                trade_service.transition_execution(
                    execution,
                    status=ExecutionStatus.CLOSE_CONFIRMED,
                    trade_intent_id=intent.id,
                    client_request_id=execution.client_request_id,
                    local_trade_id=persisted_trade.id,
                    completed_at=trade.close_time,
                    average_fill_price=trade.close_price,
                    filled_size=trade.size,
                    reason="Position close confirmed",
                )
                StrategyService._record_close_broker_action_event(
                    trade_service=trade_service,
                    execution=execution,
                    trade_intent=intent,
                    trade=persisted_trade,
                )
                if self.runtime_state_service is not None:
                    self.runtime_state_service.sync_engine_state(
                        strategy_name=engine.strategy.name,
                        instrument=engine.instrument,
                        status="RUNNING",
                        recovery_state="RUNNING",
                        runtime_mode=engine.runtime_mode,
                        last_price_seen=trade.close_price,
                        last_price_seen_at=trade.close_time,
                        current_position=None,
                    )
        self._refresh_paused_strategy_count()

    def _apply_market_status_gate(self, *, engine, signal: EntrySignal) -> EntrySignal:
        status = self.market_status_service.get_status(
            signal.instrument, broker=engine.broker, now=signal.signal_at
        )
        if status.is_ok:
            audit_summary = dict(signal.audit_summary)
            audit_summary["market_status"] = status.model_dump(mode="json")
            return replace(signal, audit_summary=audit_summary)

        logger.warning(
            "Entry blocked by market status",
            extra={
                "event": "market_status_blocked",
                "strategy": signal.strategy_name,
                "instrument": signal.instrument,
                "phase": "entry_gate",
                "reason": status.reason,
                "market_status": status.model_dump(mode="json"),
            },
        )
        audit_trail = list(signal.audit_trail)
        audit_trail.append(
            {
                "layer": "market_status",
                "status": "REJECTED",
                "passed": False,
                "reason": status.reason,
                "checks": [
                    {
                        "code": "market_status_ok",
                        "passed": False,
                        "reason": status.reason,
                        "actual": status.model_dump(mode="json"),
                    }
                ],
            }
        )
        audit_summary = dict(signal.audit_summary)
        audit_summary.update(
            {
                "approved": False,
                "rejection_layer": "market_status",
                "market_status": status.model_dump(mode="json"),
            }
        )
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=status.reason or "Market status check failed.",
            rejection_layer="market_status",
            audit_trail=audit_trail,
            audit_summary=audit_summary,
        )

    @staticmethod
    def _calculate_open_pnl(
        *, direction: str, open_price: float, current_price: float, size: float
    ) -> float:
        multiplier = 1 if direction == "BUY" else -1
        return (current_price - open_price) * size * multiplier

    @staticmethod
    def _mark_price(
        *, direction: str, price: float, bid: float | None, ask: float | None
    ) -> float:
        if direction == "BUY" and bid is not None:
            return bid
        if direction == "SELL" and ask is not None:
            return ask
        return price

    @staticmethod
    def _allocation_details(intent: TradeIntent) -> dict[str, object]:
        return (intent.details or {}).get("allocation") or {}

    @staticmethod
    def _drift_metric(
        *,
        expected: float | None,
        actual: float | None,
        threshold_percent: float | None = None,
    ) -> dict[str, object] | None:
        if expected is None or actual is None:
            return None
        absolute_drift = float(actual) - float(expected)
        percent_drift = None
        percent_drift_abs = None
        if abs(float(expected)) > 1e-9:
            percent_drift = (absolute_drift / float(expected)) * 100.0
            percent_drift_abs = abs(percent_drift)
        return {
            "expected": round(float(expected), 8),
            "actual": round(float(actual), 8),
            "absolute_drift": round(absolute_drift, 8),
            "absolute_drift_abs": round(abs(absolute_drift), 8),
            "percent_drift": round(percent_drift, 8)
            if percent_drift is not None
            else None,
            "percent_drift_abs": round(percent_drift_abs, 8)
            if percent_drift_abs is not None
            else None,
            "material": (
                percent_drift_abs is not None
                and threshold_percent is not None
                and percent_drift_abs >= threshold_percent
            ),
        }

    @staticmethod
    def _merge_stage_snapshot(
        current: dict[str, object] | None,
        update: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not current and not update:
            return None
        merged = dict(current or {})
        merged.update(
            {key: value for key, value in (update or {}).items() if value is not None}
        )
        return merged

    @staticmethod
    def _risk_truth_confidence(
        *,
        stage: str,
        source: str | None,
        precision: str | None,
        fill_confirmed: bool = False,
        partial_fill: bool = False,
        incomplete: bool = False,
    ) -> str:
        if incomplete:
            return "INCOMPLETE_DEGRADED"
        if partial_fill:
            return "PARTIAL_FILL_PROVISIONAL"
        if stage == "estimated":
            return "ALLOCATION_INTENT_ONLY"
        if stage == "submitted":
            return "SUBMITTED_EXECUTABLE_ESTIMATE"
        if (
            stage == "filled"
            and fill_confirmed
            and source == "broker_quote_unit_risk"
            and precision == "EXACT"
        ):
            return "EXACT_FILL_DERIVED"
        if stage == "filled" and fill_confirmed:
            return "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
        if source == "broker_quote_unit_risk" and precision == "EXACT":
            return "SUBMITTED_EXECUTABLE_ESTIMATE"
        return "ALLOCATION_INTENT_ONLY"

    @classmethod
    def _build_risk_reconciliation(
        cls,
        *,
        intent: TradeIntent,
        submitted_risk_tracking: dict[str, object] | None = None,
        fill_risk_tracking: dict[str, object] | None = None,
        submitted_size: float | None = None,
        filled_size: float | None = None,
        submitted_price: float | None = None,
        fill_price: float | None = None,
        live_position: Position | None = None,
        fill_status: str | None = None,
    ) -> dict[str, object]:
        allocation = cls._allocation_details(intent)
        existing = (intent.details or {}).get("risk_reconciliation") or {}
        settings = get_settings()
        estimated = cls._merge_stage_snapshot(
            existing.get("estimated") if isinstance(existing, dict) else None,
            {
                "risk_amount": intent.estimated_risk_amount
                or allocation.get("risk_amount"),
                "risk_percent": intent.allocated_risk_percent
                or allocation.get("allocated_risk_percent"),
                "size": intent.allocated_size
                or allocation.get("normalized_size")
                or allocation.get("requested_size"),
                "entry_price": intent.observed_price,
                "risk_currency": intent.risk_currency,
                "derivation_mode": "allocation_estimate",
                "precision": allocation.get("sizing_precision"),
                "sizing_mode": allocation.get("sizing_mode"),
                "risk_truth_confidence": intent.risk_truth_confidence
                or "ALLOCATION_INTENT_ONLY",
            },
        )
        submitted = cls._merge_stage_snapshot(
            existing.get("submitted") if isinstance(existing, dict) else None,
            {
                "risk_amount": (submitted_risk_tracking or {}).get(
                    "submitted_executable_risk_amount"
                )
                or intent.submitted_risk_amount,
                "risk_percent": (submitted_risk_tracking or {}).get(
                    "submitted_executable_risk_percent"
                ),
                "size": submitted_size
                if submitted_size is not None
                else (submitted_risk_tracking or {}).get("submitted_size"),
                "entry_price": submitted_price,
                "risk_currency": intent.risk_currency,
                "derivation_mode": (submitted_risk_tracking or {}).get(
                    "risk_estimate_source"
                ),
                "precision": (submitted_risk_tracking or {}).get(
                    "risk_sizing_precision"
                ),
                "sizing_mode": (submitted_risk_tracking or {}).get("risk_sizing_mode"),
                "risk_truth_confidence": (submitted_risk_tracking or {}).get(
                    "risk_truth_confidence"
                ),
            },
        )
        fill_source = (fill_risk_tracking or {}).get("risk_estimate_source")
        filled = cls._merge_stage_snapshot(
            existing.get("filled") if isinstance(existing, dict) else None,
            {
                "risk_amount": (fill_risk_tracking or {}).get(
                    "fill_derived_risk_amount"
                )
                or intent.fill_derived_risk_amount,
                "risk_percent": (fill_risk_tracking or {}).get(
                    "fill_derived_risk_percent"
                ),
                "size": filled_size
                if filled_size is not None
                else (fill_risk_tracking or {}).get("filled_size"),
                "entry_price": fill_price,
                "risk_currency": intent.risk_currency,
                "derivation_mode": fill_source
                or ("fill_price_fallback" if fill_price is not None else None),
                "precision": (fill_risk_tracking or {}).get("risk_sizing_precision"),
                "sizing_mode": (fill_risk_tracking or {}).get("risk_sizing_mode"),
                "risk_truth_confidence": (fill_risk_tracking or {}).get(
                    "risk_truth_confidence"
                ),
            },
        )
        live_snapshot = cls._merge_stage_snapshot(
            existing.get("live_position") if isinstance(existing, dict) else None,
            {
                "risk_amount": live_position.entry_risk_amount
                if live_position is not None
                else None,
                "risk_percent": live_position.risk_percent
                if live_position is not None
                else None,
                "size": live_position.size if live_position is not None else None,
                "entry_price": live_position.open_price
                if live_position is not None
                else None,
                "risk_currency": intent.risk_currency,
                "derivation_mode": "position_entry_risk_amount"
                if live_position is not None
                else None,
                "risk_truth_confidence": live_position.risk_truth_confidence
                if live_position is not None
                else None,
            },
        )
        drift_metrics = {
            "requested_to_normalized_size": (
                (allocation.get("drift_metrics") or {}).get(
                    "requested_to_normalized_size"
                )
                if isinstance(allocation, dict)
                else None
            ),
            "requested_to_allocated_risk_percent": (
                (allocation.get("drift_metrics") or {}).get(
                    "requested_to_allocated_risk_percent"
                )
                if isinstance(allocation, dict)
                else None
            ),
            "normalized_to_submitted_size": cls._drift_metric(
                expected=float(allocation.get("normalized_size"))
                if allocation.get("normalized_size") is not None
                else None,
                actual=float(submitted["size"])
                if submitted and submitted.get("size") is not None
                else None,
                threshold_percent=settings.allocation_drift_warning_percent,
            ),
            "submitted_to_filled_size": cls._drift_metric(
                expected=float(submitted["size"])
                if submitted and submitted.get("size") is not None
                else None,
                actual=float(filled["size"])
                if filled and filled.get("size") is not None
                else None,
                threshold_percent=settings.allocation_drift_warning_percent,
            ),
            "estimated_to_submitted_risk": cls._drift_metric(
                expected=float(estimated["risk_amount"])
                if estimated and estimated.get("risk_amount") is not None
                else None,
                actual=float(submitted["risk_amount"])
                if submitted and submitted.get("risk_amount") is not None
                else None,
                threshold_percent=settings.allocation_drift_warning_percent,
            ),
            "submitted_to_fill_risk": cls._drift_metric(
                expected=float(submitted["risk_amount"])
                if submitted and submitted.get("risk_amount") is not None
                else None,
                actual=float(filled["risk_amount"])
                if filled and filled.get("risk_amount") is not None
                else None,
                threshold_percent=settings.allocation_drift_warning_percent,
            ),
            "intended_to_fill_price": cls._drift_metric(
                expected=float(intent.observed_price)
                if intent.observed_price is not None
                else None,
                actual=float(fill_price) if fill_price is not None else None,
                threshold_percent=settings.allocation_drift_warning_percent,
            ),
        }
        material_execution_drift = any(
            isinstance(metric, dict) and bool(metric.get("material"))
            for key, metric in drift_metrics.items()
            if key
            in {
                "normalized_to_submitted_size",
                "submitted_to_filled_size",
                "estimated_to_submitted_risk",
                "submitted_to_fill_risk",
                "intended_to_fill_price",
            }
        )
        incomplete_fill_data = bool(
            filled is not None
            and (
                filled.get("size") is None
                or filled.get("entry_price") is None
                or filled.get("risk_amount") is None
            )
        )
        partial_fill_provisional = bool(
            fill_status == BrokerOrderStatus.PARTIALLY_FILLED.value
        )
        return {
            "estimated": estimated,
            "submitted": submitted,
            "filled": filled,
            "live_position": live_snapshot,
            "drift_metrics": drift_metrics,
            "flags": {
                "material_execution_drift": material_execution_drift,
                "critical_execution_drift": any(
                    isinstance(metric, dict)
                    and (metric.get("percent_drift_abs") or 0.0)
                    >= settings.allocation_drift_critical_percent
                    for metric in drift_metrics.values()
                    if metric is not None
                ),
                "fill_risk_estimated": bool(
                    fill_source in {None, "size_scaled_allocation"}
                ),
                "incomplete_fill_data": incomplete_fill_data,
                "partial_fill_provisional": partial_fill_provisional,
                "degraded_sizing": bool(allocation.get("degraded"))
                if isinstance(allocation, dict)
                else False,
            },
        }

    @staticmethod
    def _allocation_outcome_update(
        *,
        stage: str,
        final_status: str,
        allocator_selected: bool = True,
        hard_risk_passed: bool | None = None,
        hard_risk_blocked: bool = False,
        execution_submitted: bool = False,
        execution_blocked: bool = False,
        execution_revalidation_changed_outcome: bool = False,
        fill_status: str | None = None,
    ) -> dict[str, object]:
        return {
            "allocation_outcome": {
                "stage": stage,
                "allocator_selected": allocator_selected,
                "hard_risk_passed": hard_risk_passed,
                "hard_risk_blocked": hard_risk_blocked,
                "execution_submitted": execution_submitted,
                "execution_blocked": execution_blocked,
                "execution_revalidation_changed_outcome": execution_revalidation_changed_outcome,
                "fill_status": fill_status,
                "final_status": final_status,
            }
        }

    @classmethod
    def _estimate_execution_risk_snapshot(
        cls,
        *,
        broker,
        intent: TradeIntent,
        entry_price: float,
        size: float,
        risk_state: str,
        reservation_owner: str,
        broker_order_status: BrokerOrderStatus | None = None,
        fill_price_confirmed: bool = False,
        filled_size_confirmed: bool = False,
    ) -> dict[str, object]:
        allocation = cls._allocation_details(intent)
        sizing_details = (
            (allocation.get("sizing_details") or {})
            if isinstance(allocation, dict)
            else {}
        )
        risk_currency = intent.risk_currency or (
            (sizing_details.get("sizing_quote") or {}).get("account_currency")
        )
        account_equity = float(allocation.get("account_equity") or 0.0)
        stop_loss_price = sizing_details.get("stop_loss_price")
        fallback_stop_distance = sizing_details.get("stop_distance_price")
        estimated_amount = float(
            intent.estimated_risk_amount or allocation.get("risk_amount") or 0.0
        )
        estimated_size = float(
            intent.allocated_size
            or allocation.get("normalized_size")
            or allocation.get("requested_size")
            or 0.0
        )
        risk_amount: float | None = None
        risk_percent: float | None = None
        risk_precision = str(
            allocation.get("sizing_precision")
            or sizing_details.get("sizing_precision")
            or "UNSUPPORTED"
        )
        risk_mode = str(
            allocation.get("sizing_mode")
            or sizing_details.get("sizing_mode")
            or "UNSUPPORTED"
        )
        source = "size_scaled_allocation"
        if size > 0 and entry_price > 0:
            try:
                unit_quote = broker.quote_risk_sized_order(
                    intent.instrument,
                    entry_price=entry_price,
                    risk_amount=1.0,
                    stop_loss_price=float(stop_loss_price)
                    if stop_loss_price is not None
                    else None,
                    fallback_stop_distance=float(fallback_stop_distance)
                    if fallback_stop_distance is not None
                    else None,
                )
            except Exception:
                unit_quote = None
            if (
                unit_quote is not None
                and unit_quote.sizing_available
                and (unit_quote.risk_per_unit or 0.0) > 0
            ):
                risk_amount = float(unit_quote.risk_per_unit or 0.0) * size
                risk_precision = unit_quote.precision.value
                risk_mode = unit_quote.mode.value
                source = "broker_quote_unit_risk"
            elif estimated_amount > 0 and estimated_size > 0:
                risk_amount = estimated_amount * (size / estimated_size)
        if risk_amount is None and estimated_amount > 0 and estimated_size > 0:
            risk_amount = estimated_amount * (size / estimated_size)
        if risk_amount is not None and account_equity > 0:
            risk_percent = (risk_amount / account_equity) * 100.0
        partial_fill = broker_order_status is BrokerOrderStatus.PARTIALLY_FILLED
        incomplete = risk_state == "filled" and (
            not fill_price_confirmed or not filled_size_confirmed or risk_amount is None
        )
        truth_confidence = cls._risk_truth_confidence(
            stage="filled"
            if risk_state == "filled"
            else "submitted"
            if risk_state == "submitted"
            else "estimated",
            source=source,
            precision=risk_precision,
            fill_confirmed=fill_price_confirmed and filled_size_confirmed,
            partial_fill=partial_fill,
            incomplete=incomplete,
        )
        return {
            "risk_currency": risk_currency,
            "estimated_allocation_risk_amount": estimated_amount,
            "estimated_allocation_risk_percent": allocation.get(
                "allocated_risk_percent"
            )
            or intent.allocated_risk_percent,
            "submitted_executable_risk_amount": risk_amount
            if risk_state in {"submitted", "filled"}
            else None,
            "submitted_executable_risk_percent": risk_percent
            if risk_state in {"submitted", "filled"}
            else None,
            "fill_derived_risk_amount": risk_amount if risk_state == "filled" else None,
            "fill_derived_risk_percent": risk_percent
            if risk_state == "filled"
            else None,
            "submitted_size": size if risk_state in {"submitted", "filled"} else None,
            "filled_size": size if risk_state == "filled" else None,
            "reservation_owner": reservation_owner,
            "risk_state": risk_state,
            "risk_estimate_source": source,
            "risk_sizing_precision": risk_precision,
            "risk_sizing_mode": risk_mode,
            "risk_truth_confidence": truth_confidence,
            "risk_derivation_confidence": (
                "EXACT"
                if source == "broker_quote_unit_risk" and risk_precision == "EXACT"
                else "APPROXIMATE"
                if source == "broker_quote_unit_risk"
                else "ESTIMATED"
            ),
        }

    @staticmethod
    def _fail_entry_execution_revalidation(
        *,
        trade_service: TradeService,
        execution: Execution,
        intent: TradeIntent,
        reason: str,
        reason_code: str,
        details: dict[str, object],
    ) -> None:
        risk_reconciliation = StrategyService._build_risk_reconciliation(intent=intent)
        revalidation_details = {
            "accepted": False,
            "reason_code": reason_code,
            "reason": reason,
            **details,
        }
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.FAILED,
            trade_intent_id=intent.id,
            client_request_id=execution.client_request_id,
            reason=reason,
            error_message=reason,
            risk_truth_confidence="INCOMPLETE_DEGRADED",
            requires_manual_review=False,
            details={
                "risk_reconciliation": risk_reconciliation,
                "execution_revalidation": revalidation_details,
            },
        )
        trade_service.transition_trade_intent(
            intent,
            state=TradeIntentState.FAILED,
            decision_reason_code="execution_revalidation_failed",
            decision_reason=reason,
            risk_truth_confidence="INCOMPLETE_DEGRADED",
            details={
                **StrategyService._allocation_outcome_update(
                    stage="execution_revalidation_failed",
                    final_status=TradeIntentState.FAILED.value,
                    hard_risk_passed=True,
                    execution_blocked=True,
                ),
                "risk_reconciliation": risk_reconciliation,
                "execution_revalidation": revalidation_details,
            },
        )

    @staticmethod
    def _assert_account_and_sizing_allow_execution(
        *,
        engine,
        signal: EntrySignal,
        intent: TradeIntent,
        execution: Execution,
        trade_service: TradeService,
    ) -> dict[str, object]:
        try:
            account_summary = engine.broker.get_account_summary()
        except Exception as exc:
            reason = (
                "Entry execution blocked because broker account equity is unavailable."
            )
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="account_equity_unavailable",
                details={
                    "layer": "account",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise ValueError(reason) from exc

        account_equity = float(account_summary.equity or 0.0)
        account_available = float(account_summary.available or 0.0)
        if account_equity <= 0 or account_available <= 0:
            reason = "Entry execution blocked because broker account equity or available funds are invalid."
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="account_equity_invalid",
                details={
                    "layer": "account",
                    "account_equity": account_equity,
                    "account_available": account_available,
                },
            )
            raise ValueError(reason)

        allocation = StrategyService._allocation_details(intent)
        sizing_details = (
            (allocation.get("sizing_details") or {})
            if isinstance(allocation, dict)
            else {}
        )
        fallback_stop_distance = sizing_details.get("stop_distance_price")
        if fallback_stop_distance is None:
            fallback_stop_distance = max(
                float(signal.observed_price or 0.0)
                * get_settings().allocation_fallback_stop_distance_percent,
                1e-9,
            )
        risk_amount = (
            intent.estimated_risk_amount
            or allocation.get("risk_amount")
            or (
                account_equity * ((intent.allocated_risk_percent or 0.0) / 100.0)
                if intent.allocated_risk_percent is not None
                else None
            )
            or 1.0
        )
        risk_amount = float(risk_amount)
        if account_available < risk_amount:
            reason = "Entry execution blocked because current available funds are below approved risk."
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="account_available_below_risk",
                details={
                    "layer": "account",
                    "account_equity": account_equity,
                    "account_available": account_available,
                    "risk_amount": risk_amount,
                },
            )
            raise ValueError(reason)

        allocation_account_equity = float(allocation.get("account_equity") or 0.0)
        approved_risk_percent = (
            intent.allocated_risk_percent
            or allocation.get("allocated_risk_percent")
            or (
                (risk_amount / allocation_account_equity) * 100.0
                if allocation_account_equity > 0
                else None
            )
        )
        current_risk_percent = (risk_amount / account_equity) * 100.0
        risk_percent_drift = StrategyService._drift_metric(
            expected=float(approved_risk_percent)
            if approved_risk_percent is not None
            else None,
            actual=current_risk_percent,
            threshold_percent=get_settings().allocation_drift_warning_percent,
        )
        if (
            isinstance(risk_percent_drift, dict)
            and bool(risk_percent_drift.get("material"))
            and float(risk_percent_drift.get("absolute_drift") or 0.0) > 0
        ):
            reason = "Entry execution blocked because account equity drift materially increased approved risk."
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="account_equity_drift",
                details={
                    "layer": "account",
                    "account_equity_at_allocation": allocation.get("account_equity"),
                    "account_equity": account_equity,
                    "account_available": account_available,
                    "risk_amount": risk_amount,
                    "approved_risk_percent": approved_risk_percent,
                    "current_risk_percent": current_risk_percent,
                    "risk_percent_drift": risk_percent_drift,
                },
            )
            raise ValueError(reason)
        try:
            sizing_quote = engine.broker.quote_risk_sized_order(
                signal.instrument,
                entry_price=signal.observed_price,
                risk_amount=risk_amount,
                stop_loss_price=signal.stop_loss_price
                or sizing_details.get("stop_loss_price"),
                fallback_stop_distance=float(fallback_stop_distance),
            )
        except Exception as exc:
            reason = (
                "Entry execution blocked because broker sizing quote is unavailable."
            )
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="sizing_quote_unavailable",
                details={
                    "layer": "sizing_quote",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "account_equity": account_equity,
                    "account_available": account_available,
                },
            )
            raise ValueError(reason) from exc

        if (
            not sizing_quote.sizing_available
            or sizing_quote.precision is BrokerSizingPrecision.UNSUPPORTED
        ):
            reason = (
                sizing_quote.reason
                or "Entry execution blocked because broker sizing quote is unavailable."
            )
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code=sizing_quote.reason_code or "sizing_quote_unavailable",
                details={
                    "layer": "sizing_quote",
                    "precision": sizing_quote.precision.value,
                    "mode": sizing_quote.mode.value,
                    "sizing_available": sizing_quote.sizing_available,
                    "account_equity": account_equity,
                    "account_available": account_available,
                },
            )
            raise ValueError(reason)
        previous_sizing_quote = sizing_details.get("sizing_quote")
        approved_sizing_quote_size: float | None = None
        if isinstance(previous_sizing_quote, dict):
            previous_normalization = previous_sizing_quote.get("normalization")
            if isinstance(previous_normalization, dict):
                raw_previous_size = previous_normalization.get("normalized_size")
                if raw_previous_size is not None:
                    approved_sizing_quote_size = float(raw_previous_size)
            if approved_sizing_quote_size is None:
                raw_previous_size = previous_sizing_quote.get("normalized_size")
                if raw_previous_size is not None:
                    approved_sizing_quote_size = float(raw_previous_size)
        if approved_sizing_quote_size is None and (
            previous_sizing_quote is not None or allocation.get("sizing_precision")
        ):
            raw_previous_size = allocation.get("normalized_size")
            if raw_previous_size is not None:
                approved_sizing_quote_size = float(raw_previous_size)
        previous_sizing_precision = (
            previous_sizing_quote.get("precision")
            if isinstance(previous_sizing_quote, dict)
            else allocation.get("sizing_precision")
        )
        if previous_sizing_precision == BrokerSizingPrecision.APPROXIMATE.value:
            raw_allocated_size = allocation.get("normalized_size")
            if raw_allocated_size is not None:
                approved_sizing_quote_size = float(raw_allocated_size)
        supported_size_drift_precisions = {
            BrokerSizingPrecision.EXACT.value,
            BrokerSizingPrecision.APPROXIMATE.value,
        }
        if (
            approved_sizing_quote_size is not None
            and previous_sizing_precision in supported_size_drift_precisions
            and sizing_quote.precision.value in supported_size_drift_precisions
        ):
            sizing_quote_size_drift = StrategyService._drift_metric(
                expected=approved_sizing_quote_size,
                actual=float(sizing_quote.normalized_size),
                threshold_percent=get_settings().allocation_drift_warning_percent,
            )
            if (
                isinstance(sizing_quote_size_drift, dict)
                and bool(sizing_quote_size_drift.get("material"))
                and float(sizing_quote_size_drift.get("absolute_drift_abs") or 0.0) > 0
            ):
                reason = (
                    "Entry execution blocked because broker sizing quote drift "
                    "requires reallocation."
                )
                StrategyService._fail_entry_execution_revalidation(
                    trade_service=trade_service,
                    execution=execution,
                    intent=intent,
                    reason=reason,
                    reason_code="sizing_quote_drift",
                    details={
                        "layer": "sizing_quote",
                        "approved_sizing_quote_size": approved_sizing_quote_size,
                        "current_sizing_quote_size": sizing_quote.normalized_size,
                        "sizing_quote_size_drift": sizing_quote_size_drift,
                        "precision": sizing_quote.precision.value,
                        "mode": sizing_quote.mode.value,
                        "sizing_available": sizing_quote.sizing_available,
                        "account_equity": account_equity,
                        "account_available": account_available,
                    },
                )
                raise ValueError(reason)
        approved_risk_amount = risk_amount
        if isinstance(previous_sizing_quote, dict):
            raw_previous_risk_amount = previous_sizing_quote.get("risk_amount")
            if raw_previous_risk_amount is not None:
                approved_risk_amount = float(raw_previous_risk_amount)
        if previous_sizing_precision == BrokerSizingPrecision.APPROXIMATE.value:
            raw_allocated_risk_amount = allocation.get("risk_amount")
            if raw_allocated_risk_amount is not None:
                approved_risk_amount = float(raw_allocated_risk_amount)
        current_executable_risk_amount = None
        same_executable_size = (
            approved_sizing_quote_size is not None
            and sizing_quote.normalized_size is not None
            and abs(float(sizing_quote.normalized_size) - approved_sizing_quote_size)
            <= 1e-8
        )
        if (
            sizing_quote.risk_per_unit is not None
            and sizing_quote.normalized_size is not None
            and (
                sizing_quote.precision is BrokerSizingPrecision.EXACT
                or same_executable_size
            )
        ):
            current_executable_risk_amount = float(
                sizing_quote.normalized_size
            ) * float(sizing_quote.risk_per_unit)
        if approved_risk_amount > 0 and current_executable_risk_amount is not None:
            sizing_quote_risk_drift = StrategyService._drift_metric(
                expected=approved_risk_amount,
                actual=current_executable_risk_amount,
                threshold_percent=get_settings().allocation_drift_warning_percent,
            )
            if (
                isinstance(sizing_quote_risk_drift, dict)
                and bool(sizing_quote_risk_drift.get("material"))
                and float(sizing_quote_risk_drift.get("absolute_drift_abs") or 0.0) > 0
            ):
                reason = (
                    "Entry execution blocked because broker sizing quote risk drift "
                    "requires reallocation."
                )
                StrategyService._fail_entry_execution_revalidation(
                    trade_service=trade_service,
                    execution=execution,
                    intent=intent,
                    reason=reason,
                    reason_code="sizing_quote_risk_drift",
                    details={
                        "layer": "sizing_quote",
                        "approved_risk_amount": approved_risk_amount,
                        "current_executable_risk_amount": current_executable_risk_amount,
                        "sizing_quote_risk_drift": sizing_quote_risk_drift,
                        "current_sizing_quote_size": sizing_quote.normalized_size,
                        "risk_per_unit": sizing_quote.risk_per_unit,
                        "precision": sizing_quote.precision.value,
                        "mode": sizing_quote.mode.value,
                        "sizing_available": sizing_quote.sizing_available,
                        "account_equity": account_equity,
                        "account_available": account_available,
                    },
                )
                raise ValueError(reason)
        if (
            engine.broker.account_type.value == "LIVE"
            and sizing_quote.precision is BrokerSizingPrecision.APPROXIMATE
        ):
            reason = "Entry execution blocked because approximate sizing is not permitted for live submission."
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="approximate_sizing_unsupported",
                details={
                    "layer": "sizing_quote",
                    "precision": sizing_quote.precision.value,
                    "mode": sizing_quote.mode.value,
                    "sizing_available": sizing_quote.sizing_available,
                    "account_equity": account_equity,
                    "account_available": account_available,
                },
            )
            raise ValueError(reason)

        return {
            "account": {
                "account_id": account_summary.account_id,
                "equity": account_equity,
                "available": account_available,
                "account_type": account_summary.account_type.value,
            },
            "sizing_quote": {
                "precision": sizing_quote.precision.value,
                "mode": sizing_quote.mode.value,
                "sizing_available": sizing_quote.sizing_available,
                "reason_code": sizing_quote.reason_code,
                "risk_amount": sizing_quote.risk_amount,
                "requested_size": sizing_quote.requested_size,
                "normalized_size": sizing_quote.normalized_size,
                "risk_per_unit": sizing_quote.risk_per_unit,
                "stop_distance_price": sizing_quote.stop_distance_price,
                "account_currency": sizing_quote.account_currency,
            },
        }

    @staticmethod
    def _execute_entry_signal(
        *,
        engine,
        signal: EntrySignal,
        intent: TradeIntent,
        trade_service: TradeService,
        execution: Execution,
    ) -> Position:
        # Keep this late policy check here even if orchestration also blocks.
        # `_execute_entry_signal(...)` is the last broker-submission boundary
        # for entries and must remain safe if future callers reach it directly.
        if intent.state != TradeIntentState.APPROVED.value:
            raise ValueError(
                f"Entry execution requires an APPROVED trade intent; got {intent.state} for intent {intent.id}."
            )
        late_block = StrategyService._entry_execution_policy_block(
            session=trade_service.session, engine=engine
        )
        if late_block is not None:
            code, reason, details = late_block
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                reason=reason,
                error_message=reason,
                requires_manual_review=False,
                details={"execution_policy_block": details},
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.FAILED,
                decision_reason_code=code,
                decision_reason=reason,
                details={
                    **StrategyService._allocation_outcome_update(
                        stage="execution_policy_blocked",
                        final_status=TradeIntentState.FAILED.value,
                        hard_risk_passed=True,
                        execution_blocked=True,
                    ),
                    "execution_policy_block": details,
                },
            )
            raise ValueError(reason)
        conflicting_active = (
            trade_service.find_active_trade_intent_for_instrument_excluding(
                signal.instrument,
                exclude_intent_id=intent.id,
            )
        )
        if conflicting_active is not None:
            raise ValueError(
                f"Entry execution blocked because instrument {signal.instrument} is already owned by "
                f"active intent {conflicting_active.id} in state {conflicting_active.state}."
            )
        status = StrategyService._assert_market_status_allows_execution(
            engine=engine,
            instrument=signal.instrument,
            execution=execution,
            trade_service=trade_service,
            phase="entry_execution",
            trade_intent=intent,
        )
        executable_size = intent.allocated_size or signal.size
        try:
            size_validation = engine.broker.normalize_order_size(
                signal.instrument, executable_size
            )
        except Exception as exc:
            reason = "Entry execution blocked because broker metadata is unavailable during size normalization."
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=intent,
                reason=reason,
                reason_code="broker_metadata_unavailable",
                details={
                    "layer": "broker_metadata",
                    "stage": "size_normalization",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "requested_size": executable_size,
                },
            )
            raise ValueError(reason) from exc
        if not size_validation.accepted:
            risk_reconciliation = StrategyService._build_risk_reconciliation(
                intent=intent
            )
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                reason=f"Entry execution blocked by broker size validation: {size_validation.reason}",
                error_message=size_validation.reason,
                risk_truth_confidence="INCOMPLETE_DEGRADED",
                requires_manual_review=False,
                details={
                    "risk_reconciliation": risk_reconciliation,
                    "execution_revalidation": {
                        "accepted": False,
                        "reason_code": size_validation.reason_code,
                        "reason": size_validation.reason,
                        "normalized_size": size_validation.normalized_size,
                        "min_deal_size": size_validation.min_deal_size,
                        "size_step": size_validation.size_step,
                        "notes": size_validation.notes,
                    },
                },
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.FAILED,
                decision_reason_code="execution_revalidation_failed",
                decision_reason=size_validation.reason,
                risk_truth_confidence="INCOMPLETE_DEGRADED",
                details={
                    **StrategyService._allocation_outcome_update(
                        stage="execution_revalidation_failed",
                        final_status=TradeIntentState.FAILED.value,
                        hard_risk_passed=True,
                        execution_blocked=True,
                    ),
                    "risk_reconciliation": risk_reconciliation,
                    "execution_revalidation": {
                        "accepted": False,
                        "reason_code": size_validation.reason_code,
                        "reason": size_validation.reason,
                        "normalized_size": size_validation.normalized_size,
                    },
                },
            )
            raise ValueError(
                f"Entry execution blocked by broker size validation for {signal.instrument}: {size_validation.reason}"
            )
        if abs(size_validation.normalized_size - executable_size) > 1e-8:
            risk_reconciliation = StrategyService._build_risk_reconciliation(
                intent=intent,
                submitted_size=size_validation.normalized_size,
                submitted_price=signal.observed_price,
            )
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                reason="Broker size normalization changed after approval; reallocation required.",
                error_message="Execution-time normalization drift requires reallocation.",
                risk_truth_confidence="INCOMPLETE_DEGRADED",
                requires_manual_review=False,
                details={
                    "risk_reconciliation": risk_reconciliation,
                    "execution_revalidation": {
                        "accepted": True,
                        "reallocation_required": True,
                        "approved_size": executable_size,
                        "normalized_size": size_validation.normalized_size,
                    },
                },
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.FAILED,
                decision_reason_code="execution_revalidation_failed",
                decision_reason="Broker size normalization changed after approval; reallocation required.",
                risk_truth_confidence="INCOMPLETE_DEGRADED",
                details={
                    **StrategyService._allocation_outcome_update(
                        stage="execution_revalidation_failed",
                        final_status=TradeIntentState.FAILED.value,
                        hard_risk_passed=True,
                        execution_blocked=True,
                        execution_revalidation_changed_outcome=True,
                    ),
                    "risk_reconciliation": risk_reconciliation,
                    "execution_revalidation": {
                        "accepted": True,
                        "reallocation_required": True,
                        "approved_size": executable_size,
                        "normalized_size": size_validation.normalized_size,
                    },
                },
            )
            raise ValueError(
                f"Broker size normalization for {signal.instrument} changed after approval "
                f"({executable_size} -> {size_validation.normalized_size}); reallocation required."
            )
        broker_revalidation = (
            StrategyService._assert_account_and_sizing_allow_execution(
                engine=engine,
                signal=signal,
                intent=intent,
                execution=execution,
                trade_service=trade_service,
            )
        )
        submitted_risk_tracking = StrategyService._estimate_execution_risk_snapshot(
            broker=engine.broker,
            intent=intent,
            entry_price=signal.observed_price,
            size=size_validation.normalized_size,
            risk_state="submitted",
            reservation_owner="INTENT",
            filled_size_confirmed=True,
        )
        submitted_risk_reconciliation = StrategyService._build_risk_reconciliation(
            intent=intent,
            submitted_risk_tracking=submitted_risk_tracking,
            submitted_size=size_validation.normalized_size,
            submitted_price=signal.observed_price,
        )
        order_request = OrderRequest(
            instrument=signal.instrument,
            direction=signal.direction,
            size=size_validation.normalized_size,
            price=signal.observed_price,
            strategy_name=signal.strategy_name,
            client_request_id=execution.client_request_id,
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            trade_intent_id=intent.id,
            submitted_at=utc_now(),
            client_request_id=execution.client_request_id,
            intended_risk_amount=intent.estimated_risk_amount,
            submitted_risk_amount=submitted_risk_tracking.get(
                "submitted_executable_risk_amount"
            ),
            risk_truth_confidence=str(
                submitted_risk_tracking.get("risk_truth_confidence")
                or "SUBMITTED_EXECUTABLE_ESTIMATE"
            ),
            reason="Entry order submitted",
            details={
                "market_status_execution_check": status.model_dump(mode="json"),
                "broker_execution_revalidation": broker_revalidation,
                "risk_tracking": submitted_risk_tracking,
                "risk_reconciliation": submitted_risk_reconciliation,
            },
        )
        trade_service.transition_trade_intent(
            intent,
            state=TradeIntentState.SUBMITTED,
            execution_client_request_id=execution.client_request_id,
            submitted_risk_amount=submitted_risk_tracking.get(
                "submitted_executable_risk_amount"
            ),
            risk_truth_confidence=str(
                submitted_risk_tracking.get("risk_truth_confidence")
                or "SUBMITTED_EXECUTABLE_ESTIMATE"
            ),
            submitted_at=execution.submitted_at,
            details={
                **StrategyService._allocation_outcome_update(
                    stage="submitted_to_broker",
                    final_status=TradeIntentState.SUBMITTED.value,
                    hard_risk_passed=True,
                    execution_submitted=True,
                ),
                "broker_execution_revalidation": broker_revalidation,
                "risk_tracking": submitted_risk_tracking,
                "risk_reconciliation": submitted_risk_reconciliation,
            },
        )
        started_at = perf_counter()
        try:
            order = engine.broker.place_order(order_request)
        except Exception as exc:
            get_health_service().update_broker_state(
                connected=False, latency_ms=(perf_counter() - started_at) * 1000
            )
            get_health_service().record_order_failure()
            logger.error(
                "Entry order failed",
                extra={
                    "event": "order_failed",
                    "strategy": signal.strategy_name,
                    "strategy_name": signal.strategy_name,
                    "instrument": signal.instrument,
                    "phase": "entry",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "event_category": "execution",
                    "event_type": "execution.order_failed",
                    "event_title": "Entry order failed",
                    "correlation_id": execution.client_request_id,
                    "execution_id": execution.id,
                },
            )
            if isinstance(exc, TimeoutError):
                broker_result = {
                    "status": BrokerOrderStatus.TIMED_OUT.value,
                    "confirmation_ambiguous": True,
                    "client_request_id": execution.client_request_id,
                    "error_message": str(exc),
                }
                trade_service.transition_execution(
                    execution,
                    status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                    trade_intent_id=intent.id,
                    client_request_id=execution.client_request_id,
                    intended_risk_amount=intent.estimated_risk_amount,
                    submitted_risk_amount=submitted_risk_tracking.get(
                        "submitted_executable_risk_amount"
                    ),
                    risk_truth_confidence=str(
                        submitted_risk_tracking.get("risk_truth_confidence")
                        or "SUBMITTED_EXECUTABLE_ESTIMATE"
                    ),
                    error_code="BROKER_CONFIRMATION_TIMEOUT",
                    error_message=str(exc),
                    reason="Broker confirmation timed out; manual review required.",
                    requires_manual_review=True,
                    details={
                        "broker_result": broker_result,
                        "risk_reconciliation": submitted_risk_reconciliation,
                    },
                )
                trade_service.transition_trade_intent(
                    intent,
                    state=TradeIntentState.ACKNOWLEDGED,
                    decision_reason_code="broker_confirmation_ambiguous",
                    decision_reason=(
                        "Broker confirmation timed out after submission; manual review required."
                    ),
                    submitted_risk_amount=submitted_risk_tracking.get(
                        "submitted_executable_risk_amount"
                    ),
                    risk_truth_confidence=str(
                        submitted_risk_tracking.get("risk_truth_confidence")
                        or "SUBMITTED_EXECUTABLE_ESTIMATE"
                    ),
                    acknowledged_at=utc_now(),
                    details={
                        **StrategyService._allocation_outcome_update(
                            stage="broker_confirmation_ambiguous",
                            final_status=TradeIntentState.ACKNOWLEDGED.value,
                            hard_risk_passed=True,
                            execution_submitted=True,
                            execution_blocked=True,
                            fill_status=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
                        ),
                        "broker_result": broker_result,
                        "risk_reconciliation": submitted_risk_reconciliation,
                    },
                )
                raise
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                intended_risk_amount=intent.estimated_risk_amount,
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                risk_truth_confidence=str(
                    submitted_risk_tracking.get("risk_truth_confidence")
                    or "SUBMITTED_EXECUTABLE_ESTIMATE"
                ),
                error_message=str(exc),
                reason="Entry order submission failed",
                requires_manual_review=False,
                details={"risk_reconciliation": submitted_risk_reconciliation},
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.FAILED,
                decision_reason_code="broker_submission_failed",
                decision_reason="Entry order submission failed.",
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                risk_truth_confidence=str(
                    submitted_risk_tracking.get("risk_truth_confidence")
                    or "SUBMITTED_EXECUTABLE_ESTIMATE"
                ),
                details={
                    "error_message": str(exc),
                    **StrategyService._allocation_outcome_update(
                        stage="broker_submission_failed",
                        final_status=TradeIntentState.FAILED.value,
                        hard_risk_passed=True,
                        execution_submitted=True,
                        execution_blocked=True,
                    ),
                    "risk_tracking": submitted_risk_tracking,
                    "risk_reconciliation": submitted_risk_reconciliation,
                },
            )
            raise
        get_health_service().update_broker_state(
            connected=True, latency_ms=(perf_counter() - started_at) * 1000
        )
        StrategyService._record_order_health(order.status)

        StrategyService._transition_execution_from_broker_result(
            trade_service=trade_service,
            execution=execution,
            trade_intent=intent,
            order=order,
            opened_reason="Entry order acknowledged",
            completed_reason="Entry fill received",
        )
        if order.status in AMBIGUOUS_BROKER_ORDER_STATUSES:
            raise RuntimeError(
                f"Entry order for {signal.instrument} requires manual review; broker result is {order.status.value}."
            )
        filled_size = order.filled_size or order.size
        if (
            order.status
            in {
                BrokerOrderStatus.REJECTED,
                BrokerOrderStatus.FAILED,
                BrokerOrderStatus.CANCELLED,
            }
            or filled_size <= 0
        ):
            raise RuntimeError(
                f"Entry order for {signal.instrument} did not produce an open fill."
            )
        fill_risk_tracking = StrategyService._estimate_execution_risk_snapshot(
            broker=engine.broker,
            intent=intent,
            entry_price=order.average_fill_price or order.price,
            size=filled_size,
            risk_state="filled",
            reservation_owner="POSITION",
            broker_order_status=order.status,
            fill_price_confirmed=(
                order.average_fill_price is not None or order.price is not None
            ),
            filled_size_confirmed=(
                order.filled_size is not None or order.size is not None
            ),
        )
        fill_risk_reconciliation = StrategyService._build_risk_reconciliation(
            intent=intent,
            submitted_risk_tracking=submitted_risk_tracking,
            fill_risk_tracking=fill_risk_tracking,
            submitted_size=size_validation.normalized_size,
            filled_size=filled_size,
            submitted_price=signal.observed_price,
            fill_price=order.average_fill_price or order.price,
            fill_status=order.status.value,
        )
        engine.current_position = Position(
            trade_intent_id=intent.id,
            instrument=signal.instrument,
            broker_reference=order.broker_reference,
            direction=signal.direction.value,
            size=filled_size,
            open_price=order.average_fill_price or order.price,
            open_time=order.executed_at,
            strategy_name=signal.strategy_name,
            family_name=intent.family_name,
            account_type=engine.broker.account_type.value,
            is_open=True,
            risk_percent=float(
                fill_risk_tracking.get("fill_derived_risk_percent")
                or intent.allocated_risk_percent
                or signal.risk_percent
                or 0.0
            ),
            entry_risk_amount=float(
                fill_risk_tracking.get("fill_derived_risk_amount")
                or fill_risk_tracking.get("submitted_executable_risk_amount")
                or intent.estimated_risk_amount
                or 0.0
            ),
            risk_truth_confidence=str(
                fill_risk_tracking.get("risk_truth_confidence") or "INCOMPLETE_DEGRADED"
            ),
            current_price=order.average_fill_price or order.price,
            unrealized_pnl=0.0,
            reason=f"{signal.strategy_name} entry approved",
            broker_sync_status=StrategyService._position_sync_status_for_order(order),
        )
        persisted_position = trade_service.record_broker_position(
            engine.current_position
        )
        if order.status is BrokerOrderStatus.PARTIALLY_FILLED:
            residual_size = max(size_validation.normalized_size - filled_size, 0.0)
            engine.runtime_mode = "EXITS_ONLY"
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                local_position_id=persisted_position.id,
                broker_reference=persisted_position.broker_reference,
                completed_at=persisted_position.broker_open_confirmed_at
                or persisted_position.open_time,
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                intended_risk_amount=intent.estimated_risk_amount,
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                fill_derived_risk_amount=fill_risk_tracking.get(
                    "fill_derived_risk_amount"
                ),
                risk_truth_confidence=str(
                    fill_risk_tracking.get("risk_truth_confidence")
                    or "INCOMPLETE_DEGRADED"
                ),
                reason="Entry partially filled; runtime restricted to exits only pending review.",
                requires_manual_review=True,
                details={
                    "risk_tracking": fill_risk_tracking,
                    "risk_reconciliation": fill_risk_reconciliation,
                    "partial_fill": {
                        "submitted_size": size_validation.normalized_size,
                        "filled_size": filled_size,
                        "residual_size": residual_size,
                    },
                },
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.PARTIALLY_FILLED,
                broker_reference=persisted_position.broker_reference,
                position_id=persisted_position.id,
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                fill_derived_risk_amount=fill_risk_tracking.get(
                    "fill_derived_risk_amount"
                ),
                risk_truth_confidence=str(
                    fill_risk_tracking.get("risk_truth_confidence")
                    or "INCOMPLETE_DEGRADED"
                ),
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                completed_at=persisted_position.broker_open_confirmed_at
                or persisted_position.open_time,
                opened_at=persisted_position.open_time,
                details={
                    **StrategyService._allocation_outcome_update(
                        stage="position_partially_opened_pending_review",
                        final_status=TradeIntentState.PARTIALLY_FILLED.value,
                        hard_risk_passed=True,
                        execution_submitted=True,
                        fill_status=TradeIntentState.PARTIALLY_FILLED.value,
                    ),
                    "risk_tracking": fill_risk_tracking,
                    "risk_reconciliation": StrategyService._build_risk_reconciliation(
                        intent=intent,
                        submitted_risk_tracking=submitted_risk_tracking,
                        fill_risk_tracking=fill_risk_tracking,
                        submitted_size=size_validation.normalized_size,
                        filled_size=filled_size,
                        submitted_price=signal.observed_price,
                        fill_price=persisted_position.open_price,
                        live_position=persisted_position,
                        fill_status=order.status.value,
                    ),
                    "partial_fill": {
                        "submitted_size": size_validation.normalized_size,
                        "filled_size": filled_size,
                        "residual_size": residual_size,
                    },
                },
            )
            record_required_domain_event(
                session=trade_service.session,
                event_type="execution.partial_fill_requires_review",
                category="execution",
                severity="warning",
                source="strategy_service.execute_entry_signal",
                title="Entry partially filled",
                message=f"{signal.strategy_name} entry on {signal.instrument} partially filled and was restricted to EXITS_ONLY.",
                correlation_id=execution.client_request_id,
                strategy_name=signal.strategy_name,
                instrument=signal.instrument,
                position_id=persisted_position.id,
                execution_id=execution.id,
                actor_type="service",
                actor_id="strategy_service",
                payload_json={
                    "trade_intent_id": intent.id,
                    "previous_state": ExecutionStatus.FILL_PARTIAL.value,
                    "new_state": ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
                    "submitted_size": size_validation.normalized_size,
                    "filled_size": filled_size,
                    "residual_size": residual_size,
                },
            )
        else:
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.POSITION_OPENED,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                local_position_id=persisted_position.id,
                broker_reference=persisted_position.broker_reference,
                completed_at=persisted_position.broker_open_confirmed_at
                or persisted_position.open_time,
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                intended_risk_amount=intent.estimated_risk_amount,
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                fill_derived_risk_amount=fill_risk_tracking.get(
                    "fill_derived_risk_amount"
                ),
                risk_truth_confidence=str(
                    fill_risk_tracking.get("risk_truth_confidence")
                    or "INCOMPLETE_DEGRADED"
                ),
                reason="Position opened",
                details={
                    "risk_tracking": fill_risk_tracking,
                    "risk_reconciliation": fill_risk_reconciliation,
                },
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.POSITION_OPENED,
                broker_reference=persisted_position.broker_reference,
                position_id=persisted_position.id,
                submitted_risk_amount=submitted_risk_tracking.get(
                    "submitted_executable_risk_amount"
                ),
                fill_derived_risk_amount=fill_risk_tracking.get(
                    "fill_derived_risk_amount"
                ),
                risk_truth_confidence=str(
                    fill_risk_tracking.get("risk_truth_confidence")
                    or "INCOMPLETE_DEGRADED"
                ),
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                completed_at=persisted_position.broker_open_confirmed_at
                or persisted_position.open_time,
                opened_at=persisted_position.open_time,
                details={
                    **StrategyService._allocation_outcome_update(
                        stage="position_opened",
                        final_status=TradeIntentState.POSITION_OPENED.value,
                        hard_risk_passed=True,
                        execution_submitted=True,
                        fill_status=TradeIntentState.FILLED.value,
                    ),
                    "risk_tracking": fill_risk_tracking,
                    "risk_reconciliation": StrategyService._build_risk_reconciliation(
                        intent=intent,
                        submitted_risk_tracking=submitted_risk_tracking,
                        fill_risk_tracking=fill_risk_tracking,
                        submitted_size=size_validation.normalized_size,
                        filled_size=filled_size,
                        submitted_price=signal.observed_price,
                        fill_price=persisted_position.open_price,
                        live_position=persisted_position,
                        fill_status=order.status.value,
                    ),
                },
            )
        if bool(
            (fill_risk_reconciliation.get("flags") or {}).get(
                "material_execution_drift"
            )
        ):
            record_required_domain_event(
                session=trade_service.session,
                event_type="allocation.execution_drift_detected",
                category="allocation",
                severity=(
                    "error"
                    if bool(
                        (fill_risk_reconciliation.get("flags") or {}).get(
                            "critical_execution_drift"
                        )
                    )
                    else "warning"
                ),
                source="strategy_service.execute_entry_signal",
                title="Execution drift exceeded tolerance",
                message=f"Execution drift exceeded tolerance for {signal.instrument}.",
                correlation_id=execution.client_request_id,
                strategy_name=signal.strategy_name,
                instrument=signal.instrument,
                position_id=persisted_position.id,
                execution_id=execution.id,
                actor_type="service",
                actor_id="strategy_service",
                payload_json={
                    "trade_intent_id": intent.id,
                    "risk_reconciliation": fill_risk_reconciliation,
                },
            )
        engine.strategy.on_position_opened(
            direction=signal.direction, entry_price=order.price
        )
        engine.current_position = clone_position(persisted_position)
        return clone_position(persisted_position)

    @staticmethod
    def _execute_exit_signal(
        *,
        engine,
        signal: ExitSignal,
        intent: TradeIntent,
        trade_service: TradeService,
        execution: Execution,
    ) -> Trade:
        if intent.state not in {
            TradeIntentState.PARTIALLY_FILLED.value,
            TradeIntentState.POSITION_OPENED.value,
            TradeIntentState.CLOSE_REQUESTED.value,
            TradeIntentState.SUBMITTED.value,
            TradeIntentState.ACKNOWLEDGED.value,
            TradeIntentState.EXTERNAL_POSITION_ADOPTED.value,
            TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
        }:
            raise ValueError(
                f"Exit execution requires an open linked trade intent; got {intent.state} for intent {intent.id}."
            )
        if engine.current_position is None:
            raise ValueError(
                f"No active engine position for {signal.strategy_name} on {signal.instrument}."
            )
        status = StrategyService._assert_market_status_allows_execution(
            engine=engine,
            instrument=signal.instrument,
            execution=execution,
            trade_service=trade_service,
            phase="exit_execution",
        )
        trade_service.transition_trade_intent(
            intent,
            state=TradeIntentState.CLOSE_REQUESTED,
            close_reason_code="strategy_exit_requested",
            close_reason="Strategy emitted exit signal.",
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            trade_intent_id=intent.id,
            submitted_at=utc_now(),
            client_request_id=execution.client_request_id,
            reason="Close order submitted",
            details={"market_status_execution_check": status.model_dump(mode="json")},
        )
        trade_service.transition_trade_intent(
            intent,
            state=TradeIntentState.SUBMITTED,
            submitted_at=execution.submitted_at,
        )
        started_at = perf_counter()
        try:
            closed_order = engine.broker.close_position(
                signal.instrument,
                broker_reference=engine.current_position.broker_reference,
                client_request_id=execution.client_request_id,
            )
        except Exception as exc:
            get_health_service().update_broker_state(
                connected=False, latency_ms=(perf_counter() - started_at) * 1000
            )
            get_health_service().record_order_failure()
            logger.error(
                "Close order failed",
                extra={
                    "event": "order_failed",
                    "strategy": signal.strategy_name,
                    "strategy_name": signal.strategy_name,
                    "instrument": signal.instrument,
                    "phase": "exit",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "event_category": "execution",
                    "event_type": "execution.order_failed",
                    "event_title": "Close order failed",
                    "correlation_id": execution.client_request_id,
                    "execution_id": execution.id,
                },
            )
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                trade_intent_id=intent.id,
                client_request_id=execution.client_request_id,
                error_message=str(exc),
                reason="Close request failed",
                requires_manual_review=True,
            )
            trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.CLOSE_REQUESTED,
                close_reason_code="close_submission_failed",
                close_reason="Close request failed.",
                details={"error_message": str(exc)},
            )
            raise
        get_health_service().update_broker_state(
            connected=True, latency_ms=(perf_counter() - started_at) * 1000
        )
        StrategyService._record_order_health(closed_order.status)

        StrategyService._transition_execution_from_broker_result(
            trade_service=trade_service,
            execution=execution,
            trade_intent=intent,
            order=closed_order,
            opened_reason="Close order acknowledged",
            completed_reason="Close fill received",
        )
        if closed_order.status is not BrokerOrderStatus.FILLED:
            previous_close_state = (
                ExecutionStatus.FILL_PARTIAL.value
                if closed_order.status is BrokerOrderStatus.PARTIALLY_FILLED
                else ExecutionStatus.ORDER_ACKNOWLEDGED.value
                if closed_order.status in AMBIGUOUS_BROKER_ORDER_STATUSES
                else ExecutionStatus.ORDER_ACKNOWLEDGED.value
            )
            StrategyService._record_close_broker_action_event(
                trade_service=trade_service,
                execution=execution,
                trade_intent=intent,
                trade=None,
                event_type="broker.close_requires_manual_review",
                severity="error",
                title="Broker close requires manual review",
                message=f"{signal.strategy_name} close on {signal.instrument} did not complete fully.",
                previous_state=previous_close_state,
                new_state=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
            )
            raise RuntimeError(
                f"Close order for {signal.instrument} did not complete fully."
            )
        pnl = StrategyService._calculate_open_pnl(
            direction=engine.current_position.direction,
            open_price=engine.current_position.open_price,
            current_price=closed_order.average_fill_price or closed_order.price,
            size=engine.current_position.size,
        )
        trade = Trade(
            trade_intent_id=intent.id,
            strategy_name=engine.current_position.strategy_name,
            family_name=engine.current_position.family_name,
            broker_reference=engine.current_position.broker_reference,
            close_broker_reference=closed_order.broker_reference,
            instrument=engine.current_position.instrument,
            direction=engine.current_position.direction,
            size=engine.current_position.size,
            open_price=engine.current_position.open_price,
            close_price=closed_order.average_fill_price or closed_order.price,
            open_time=engine.current_position.open_time,
            close_time=closed_order.executed_at,
            pnl=pnl,
            entry_risk_amount=engine.current_position.entry_risk_amount,
            risk_truth_confidence=engine.current_position.risk_truth_confidence,
            close_execution_source=closed_order.execution_source.value,
            account_type=engine.current_position.account_type,
        )
        engine.current_position.is_open = False
        engine.current_position.close_price = (
            closed_order.average_fill_price or closed_order.price
        )
        engine.current_position.close_time = closed_order.executed_at
        engine.current_position.pnl = pnl
        engine.strategy.on_position_closed()
        engine.current_position = None
        return trade

    @staticmethod
    def _assert_market_status_allows_execution(
        *,
        engine,
        instrument: str,
        execution: Execution,
        trade_service: TradeService,
        phase: str,
        trade_intent: TradeIntent | None = None,
    ) -> MarketStatus:
        status = get_market_status_service().get_status(
            instrument,
            broker=engine.broker,
            now=execution.last_transition_at or execution.signal_time or utc_now(),
            force_refresh=True,
        )
        if status.is_ok:
            return status

        logger.warning(
            "Execution blocked by market status",
            extra={
                "event": "market_status_blocked",
                "strategy": execution.strategy_name,
                "instrument": instrument,
                "phase": phase,
                "reason": status.reason,
                "market_status": status.model_dump(mode="json"),
                "client_request_id": execution.client_request_id,
            },
        )
        if trade_intent is not None:
            reason = f"Execution blocked by market status: {status.reason}"
            StrategyService._fail_entry_execution_revalidation(
                trade_service=trade_service,
                execution=execution,
                intent=trade_intent,
                reason=reason,
                reason_code="market_status_blocked",
                details={
                    "layer": "market_status",
                    "market_status": status.model_dump(mode="json"),
                },
            )
            raise RuntimeError(status.reason or "Execution blocked by market status.")
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.FAILED,
            client_request_id=execution.client_request_id,
            reason=f"Execution blocked by market status: {status.reason}",
            error_message=status.reason,
            requires_manual_review=False,
            details={"market_status_execution_check": status.model_dump(mode="json")},
        )
        raise RuntimeError(status.reason or "Execution blocked by market status.")

    @staticmethod
    def _record_order_health(order_status: BrokerOrderStatus) -> None:
        health_service = get_health_service()
        if order_status is BrokerOrderStatus.REJECTED:
            health_service.record_order_rejection()
        elif order_status in {BrokerOrderStatus.FAILED, BrokerOrderStatus.CANCELLED}:
            health_service.record_order_failure()

    @staticmethod
    def _broker_result_payload(
        order, *, client_request_id: str | None
    ) -> dict[str, object]:
        return {
            "status": order.status.value,
            "execution_source": order.execution_source.value,
            "client_request_id": client_request_id,
            "broker_reference": order.broker_reference,
            "requested_size": order.requested_size,
            "filled_size": order.filled_size,
            "average_fill_price": order.average_fill_price,
            "submitted_at": order.submitted_at.isoformat()
            if order.submitted_at is not None
            else None,
            "acknowledged_at": order.acknowledged_at.isoformat()
            if order.acknowledged_at is not None
            else None,
            "executed_at": order.executed_at.isoformat(),
            "reason": order.reason,
            "error_code": order.error_code,
            "error_message": order.error_message,
            "requires_manual_review": order.requires_manual_review,
        }

    @staticmethod
    def _position_sync_status_for_order(order) -> str:
        if order.execution_source is BrokerExecutionSource.BROKER_CONFIRMED:
            return "CONFIRMED"
        return order.execution_source.value

    @staticmethod
    def _record_close_broker_action_event(
        *,
        trade_service: TradeService,
        execution: Execution,
        trade_intent: TradeIntent,
        trade: Trade | None,
        event_type: str = "broker.close_confirmed",
        severity: str = "info",
        title: str = "Broker close confirmed",
        message: str | None = None,
        previous_state: str = ExecutionStatus.FILL_FULL.value,
        new_state: str = ExecutionStatus.CLOSE_CONFIRMED.value,
    ) -> None:
        broker_result = (execution.details or {}).get("broker_result")
        source = "strategy_service.execute_exit_signal"
        strategy_name = (
            trade.strategy_name if trade is not None else execution.strategy_name
        )
        instrument = trade.instrument if trade is not None else execution.instrument
        close_time = trade.close_time if trade is not None else execution.completed_at
        close_execution_source = (
            trade.close_execution_source if trade is not None else None
        ) or (
            str(broker_result.get("execution_source"))
            if isinstance(broker_result, dict)
            and broker_result.get("execution_source") is not None
            else BrokerExecutionSource.BROKER_CONFIRMED.value
        )
        try:
            record_required_domain_event(
                session=trade_service.session,
                event_type=event_type,
                category="execution",
                severity=severity,
                source=source,
                title=title,
                message=message or f"{strategy_name} close on {instrument} completed.",
                correlation_id=execution.client_request_id,
                strategy_name=strategy_name,
                instrument=instrument,
                position_id=execution.local_position_id,
                trade_id=trade.id if trade is not None else None,
                execution_id=execution.id,
                actor_type="service",
                actor_id="strategy_service",
                payload_json={
                    "trade_intent_id": trade_intent.id,
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "close_broker_reference": execution.broker_reference,
                    "execution_source": close_execution_source,
                    "broker_reference": trade.broker_reference
                    if trade is not None
                    else None,
                    "size": trade.size if trade is not None else execution.filled_size,
                    "close_price": trade.close_price
                    if trade is not None
                    else execution.average_fill_price,
                    "pnl": trade.pnl if trade is not None else None,
                    "broker_result": broker_result
                    if isinstance(broker_result, dict)
                    else {},
                },
                created_at=close_time,
            )
        except AuditEventPersistenceError:
            StrategyService._mark_execution_audit_persistence_failure(
                trade_service=trade_service,
                execution=execution,
                event_type=event_type,
                source=source,
                previous_state=previous_state,
                new_state=new_state,
            )

    @staticmethod
    def _mark_execution_audit_persistence_failure(
        *,
        trade_service: TradeService,
        execution: Execution,
        event_type: str,
        source: str,
        previous_state: str | None,
        new_state: str,
    ) -> None:
        details = dict(execution.details or {})
        failures = list(details.get("audit_event_failures") or [])
        failures.append(
            {
                "event_type": event_type,
                "source": source,
                "previous_state": previous_state,
                "new_state": new_state,
                "correlation_id": execution.client_request_id,
            }
        )
        details["domain_event_persistence_failed"] = True
        details["audit_event_failures"] = failures
        execution.details = details
        trade_service.session.add(execution)
        trade_service.session.commit()
        trade_service.session.refresh(execution)

    @staticmethod
    def _transition_execution_from_broker_result(
        *,
        trade_service: TradeService,
        execution: Execution,
        trade_intent: TradeIntent | None,
        order,
        opened_reason: str,
        completed_reason: str,
    ) -> None:
        intent_broker_reference_kwargs = (
            {"close_broker_reference": order.broker_reference}
            if execution.phase == ExecutionPhase.CLOSE.value
            else {"broker_reference": order.broker_reference}
        )
        client_request_id = order.client_request_id or execution.client_request_id
        broker_result = StrategyService._broker_result_payload(
            order, client_request_id=client_request_id
        )
        is_close_phase = execution.phase == ExecutionPhase.CLOSE.value
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_ACKNOWLEDGED,
            trade_intent_id=trade_intent.id if trade_intent is not None else None,
            client_request_id=client_request_id,
            broker_reference=order.broker_reference,
            submitted_at=order.submitted_at,
            acknowledged_at=order.acknowledged_at or order.executed_at,
            reason=order.reason or opened_reason,
            error_code=order.error_code,
            error_message=order.error_message,
            requires_manual_review=order.requires_manual_review,
            details={"broker_result": broker_result},
        )
        if trade_intent is not None:
            trade_service.transition_trade_intent(
                trade_intent,
                state=TradeIntentState.ACKNOWLEDGED,
                execution_client_request_id=client_request_id,
                acknowledged_at=order.acknowledged_at or order.executed_at,
                details={"broker_result": broker_result},
                **intent_broker_reference_kwargs,
            )
        if is_close_phase and order.status is not BrokerOrderStatus.FILLED:
            if order.status is BrokerOrderStatus.PARTIALLY_FILLED:
                trade_service.transition_execution(
                    execution,
                    status=ExecutionStatus.FILL_PARTIAL,
                    trade_intent_id=trade_intent.id if trade_intent is not None else None,
                    client_request_id=client_request_id,
                    broker_reference=order.broker_reference,
                    completed_at=order.executed_at,
                    filled_size=order.filled_size or order.size,
                    average_fill_price=order.average_fill_price or order.price,
                    reason=order.reason or "Close partially filled.",
                    error_code=order.error_code,
                    error_message=order.error_message,
                    requires_manual_review=True,
                    details={"broker_result": broker_result},
                )
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                trade_intent_id=trade_intent.id if trade_intent is not None else None,
                client_request_id=client_request_id,
                broker_reference=order.broker_reference,
                completed_at=order.executed_at,
                filled_size=order.filled_size or order.size,
                average_fill_price=order.average_fill_price or order.price,
                reason=order.reason or "Close did not complete fully.",
                error_code=order.error_code
                or (
                    "BROKER_CONFIRMATION_AMBIGUOUS"
                    if order.status in AMBIGUOUS_BROKER_ORDER_STATUSES
                    else "BROKER_CLOSE_INCOMPLETE"
                ),
                error_message=order.error_message,
                requires_manual_review=True,
                details={"broker_result": broker_result},
            )
            if trade_intent is not None:
                trade_service.transition_trade_intent(
                    trade_intent,
                    state=TradeIntentState.CLOSE_REQUESTED,
                    execution_client_request_id=client_request_id,
                    acknowledged_at=order.acknowledged_at or order.executed_at,
                    completed_at=order.executed_at,
                    close_reason_code="close_incomplete",
                    close_reason=order.reason or "Close did not complete fully.",
                    details={
                        **StrategyService._allocation_outcome_update(
                            stage="close_incomplete",
                            final_status=TradeIntentState.CLOSE_REQUESTED.value,
                            hard_risk_passed=True,
                            execution_submitted=True,
                            execution_blocked=True,
                            fill_status=execution.status,
                        ),
                        "broker_result": {
                            **broker_result,
                            "confirmation_ambiguous": order.status
                            in AMBIGUOUS_BROKER_ORDER_STATUSES,
                        },
                    },
                    **intent_broker_reference_kwargs,
                )
            return

        if order.status in AMBIGUOUS_BROKER_ORDER_STATUSES:
            broker_result = {**broker_result, "confirmation_ambiguous": True}
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                trade_intent_id=trade_intent.id if trade_intent is not None else None,
                client_request_id=client_request_id,
                broker_reference=order.broker_reference,
                acknowledged_at=order.acknowledged_at or order.executed_at,
                reason=order.reason
                or "Broker result is not final; manual review required.",
                error_code=order.error_code or "BROKER_CONFIRMATION_AMBIGUOUS",
                error_message=order.error_message,
                requires_manual_review=True,
                details={"broker_result": broker_result},
            )
            if trade_intent is not None:
                trade_service.transition_trade_intent(
                    trade_intent,
                    state=TradeIntentState.ACKNOWLEDGED,
                    execution_client_request_id=client_request_id,
                    acknowledged_at=order.acknowledged_at or order.executed_at,
                    decision_reason_code="broker_confirmation_ambiguous",
                    decision_reason=(
                        order.reason
                        or "Broker result is not final; manual review required."
                    ),
                    details={
                        **StrategyService._allocation_outcome_update(
                            stage="broker_confirmation_ambiguous",
                            final_status=TradeIntentState.ACKNOWLEDGED.value,
                            hard_risk_passed=True,
                            execution_submitted=True,
                            execution_blocked=True,
                            fill_status=ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
                        ),
                        "broker_result": broker_result,
                    },
                    **intent_broker_reference_kwargs,
                )
            return
        fill_status = (
            ExecutionStatus.FILL_PARTIAL
            if order.status is BrokerOrderStatus.PARTIALLY_FILLED
            else ExecutionStatus.FAILED
            if order.status in {BrokerOrderStatus.REJECTED, BrokerOrderStatus.FAILED}
            else ExecutionStatus.CANCELLED
            if order.status is BrokerOrderStatus.CANCELLED
            else ExecutionStatus.FILL_FULL
        )
        trade_service.transition_execution(
            execution,
            status=fill_status,
            trade_intent_id=trade_intent.id if trade_intent is not None else None,
            client_request_id=client_request_id,
            broker_reference=order.broker_reference,
            completed_at=order.executed_at,
            filled_size=order.filled_size or order.size,
            average_fill_price=order.average_fill_price or order.price,
            reason=order.reason or completed_reason,
            error_code=order.error_code,
            error_message=order.error_message,
            requires_manual_review=order.requires_manual_review,
            details={"broker_result": broker_result},
        )
        if trade_intent is not None:
            intent_state = (
                TradeIntentState.PARTIALLY_FILLED
                if order.status is BrokerOrderStatus.PARTIALLY_FILLED
                else TradeIntentState.FAILED
                if order.status
                in {BrokerOrderStatus.REJECTED, BrokerOrderStatus.FAILED}
                else TradeIntentState.CANCELLED
                if order.status is BrokerOrderStatus.CANCELLED
                else TradeIntentState.FILLED
            )
            trade_service.transition_trade_intent(
                trade_intent,
                state=intent_state,
                average_fill_price=order.average_fill_price or order.price,
                filled_size=order.filled_size or order.size,
                completed_at=order.executed_at,
                details=StrategyService._allocation_outcome_update(
                    stage=(
                        "fill_partial"
                        if order.status is BrokerOrderStatus.PARTIALLY_FILLED
                        else "broker_order_failed"
                        if order.status
                        in {BrokerOrderStatus.REJECTED, BrokerOrderStatus.FAILED}
                        else "broker_order_cancelled"
                        if order.status is BrokerOrderStatus.CANCELLED
                        else "fill_complete"
                    ),
                    final_status=intent_state.value,
                    hard_risk_passed=True,
                    execution_submitted=True,
                    execution_blocked=order.status
                    in {
                        BrokerOrderStatus.REJECTED,
                        BrokerOrderStatus.FAILED,
                        BrokerOrderStatus.CANCELLED,
                    },
                    fill_status=fill_status.value,
                )
                | {"broker_result": broker_result},
                **intent_broker_reference_kwargs,
            )

    @classmethod
    def _generate_client_request_id(cls, prefix: str) -> str:
        normalized_prefix = prefix[:3].lower()
        return f"{normalized_prefix}-{uuid4().hex[:26]}"

    @staticmethod
    def _entry_action_key(signal: EntrySignal) -> str:
        return (
            f"entry:{signal.strategy_name}:{signal.instrument}:{signal.direction.value}"
        )

    @staticmethod
    def _close_action_key(signal: ExitSignal) -> str:
        position_ref = (
            signal.position.broker_reference
            if signal.position is not None
            else "unknown"
        )
        return f"close:{signal.strategy_name}:{signal.instrument}:{position_ref}"

    @classmethod
    def _prepare_execution(
        cls,
        *,
        trade_service: TradeService,
        strategy_name: str,
        instrument: str,
        phase: str,
        signal_time: datetime,
        requested_size: float | None,
        requested_price: float | None,
        reason: str,
        details: dict[str, object],
        trade_intent_id: int | None = None,
        broker_reference: str | None = None,
        local_position_id: int | None = None,
    ) -> tuple[Execution, bool]:
        action_key = str(details["action_key"])
        reusable_execution = trade_service.find_latest_execution_for_action(
            strategy_name=strategy_name,
            instrument=instrument,
            phase=phase,
            action_key=action_key,
        )
        if (
            reusable_execution is not None
            and reusable_execution.status in cls.RETRYABLE_EXECUTION_STATUSES
        ):
            duplicate_attempt_count = (
                int(
                    (reusable_execution.details or {}).get("duplicate_attempt_count")
                    or 0
                )
                + 1
            )
            duplicate_details = {
                **details,
                "duplicate_action_detected": True,
                "duplicate_attempt_count": duplicate_attempt_count,
                "last_duplicate_detected_at": utc_now().isoformat(),
                "last_duplicate_status": reusable_execution.status,
            }
            if (
                phase == ExecutionPhase.ENTRY.value
                and reusable_execution.status in cls.UNSAFE_ENTRY_RETRY_STATUSES
            ):
                duplicate_details["blocked_duplicate_client_request_id"] = (
                    reusable_execution.client_request_id
                )
                record_required_domain_event(
                    session=trade_service.session,
                    event_type="execution.retry_suppressed",
                    category="execution",
                    severity="warning",
                    source="strategy_service.prepare_execution",
                    title="Duplicate entry retry suppressed",
                    message=(
                        "A duplicate entry request was blocked because the prior "
                        "entry may already have reached the broker."
                    ),
                    correlation_id=reusable_execution.client_request_id,
                    strategy_name=strategy_name,
                    instrument=instrument,
                    execution_id=reusable_execution.id,
                    actor_type="service",
                    actor_id="strategy_service",
                    payload_json={
                        **duplicate_details,
                        "previous_state": reusable_execution.status,
                        "new_state": ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
                    },
                )
                return (
                    trade_service.transition_execution(
                        reusable_execution,
                        status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                        trade_intent_id=trade_intent_id,
                        client_request_id=reusable_execution.client_request_id,
                        broker_reference=broker_reference,
                        local_position_id=local_position_id,
                        reason=(
                            "Duplicate entry retry blocked; prior entry may already "
                            "have reached the broker"
                        ),
                        requires_manual_review=True,
                        details={**duplicate_details, "duplicate_retry_blocked": True},
                    ),
                    False,
                )
            if (
                phase == ExecutionPhase.CLOSE.value
                and reusable_execution.status not in cls.SAFE_CLOSE_RETRY_STATUSES
            ):
                record_required_domain_event(
                    session=trade_service.session,
                    event_type="execution.retry_suppressed",
                    category="execution",
                    severity="warning",
                    source="strategy_service.prepare_execution",
                    title="Duplicate close retry suppressed",
                    message="A duplicate close request was blocked because the prior close may already have reached the broker.",
                    correlation_id=reusable_execution.client_request_id,
                    strategy_name=strategy_name,
                    instrument=instrument,
                    position_id=local_position_id,
                    execution_id=reusable_execution.id,
                    actor_type="service",
                    actor_id="strategy_service",
                    payload_json={
                        **duplicate_details,
                        "previous_state": reusable_execution.status,
                        "new_state": ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
                    },
                )
                return (
                    trade_service.transition_execution(
                        reusable_execution,
                        status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                        client_request_id=reusable_execution.client_request_id,
                        broker_reference=broker_reference,
                        local_position_id=local_position_id,
                        reason="Duplicate close retry blocked; prior close may already have reached the broker",
                        requires_manual_review=True,
                        details={**duplicate_details, "duplicate_retry_blocked": True},
                    ),
                    False,
                )
            return (
                trade_service.transition_execution(
                    reusable_execution,
                    status=reusable_execution.status,
                    trade_intent_id=trade_intent_id,
                    client_request_id=reusable_execution.client_request_id,
                    broker_reference=broker_reference,
                    local_position_id=local_position_id,
                    reason=f"{reason} retried with persisted client request id",
                    details=duplicate_details,
                ),
                True,
            )

        client_request_id = cls._generate_client_request_id(
            "ent" if phase == ExecutionPhase.ENTRY.value else "cls"
        )
        return (
            trade_service.create_execution(
                Execution(
                    trade_intent_id=trade_intent_id,
                    strategy_name=strategy_name,
                    instrument=instrument,
                    phase=phase,
                    status=ExecutionStatus.SUBMISSION_PENDING.value,
                    client_request_id=client_request_id,
                    broker_reference=broker_reference,
                    local_position_id=local_position_id,
                    signal_time=signal_time,
                    requested_size=requested_size,
                    requested_price=requested_price,
                    reason=reason,
                    details={**details, "duplicate_attempt_count": 0},
                )
            ),
            True,
        )

    @staticmethod
    def _runtime_authority_context(engine) -> dict[str, object]:
        startup_context = getattr(engine, "startup_context", None) or {}
        if not startup_context:
            return {}
        return dict(startup_context)

    @staticmethod
    def _resolve_price_snapshot(
        instrument: str, fallback_price: float | None = None
    ) -> dict[str, object]:
        from app.services.ig_streaming_service import get_ig_streaming_service

        streamed_price = get_ig_streaming_service().get_last_price(instrument)
        if streamed_price is not None:
            return {
                "price": streamed_price,
                "status": "LIVE",
                "error": None,
                "updated_at": get_ig_streaming_service().get_last_tick_at(instrument),
            }

        last_price = runtime_manager.get_last_price(instrument)
        if last_price is not None:
            updated_at = runtime_manager.get_last_price_updated_at(instrument)
            error = runtime_manager.get_price_error(instrument)
            if updated_at is None:
                status = "STALE" if error else "CACHED"
            else:
                age_seconds = (
                    datetime.now(UTC) - updated_at.astimezone(UTC)
                ).total_seconds()
                status = "STALE" if error or age_seconds > 10 else "POLLED"
            return {
                "price": last_price,
                "status": status,
                "error": error,
                "updated_at": updated_at,
            }

        if fallback_price is not None:
            return {
                "price": fallback_price,
                "status": "POSITION",
                "error": runtime_manager.get_price_error(instrument),
                "updated_at": runtime_manager.get_last_price_updated_at(instrument),
            }

        instrument_engines = runtime_manager.get_engines_for_instrument(instrument)
        if not instrument_engines:
            return {
                "price": None,
                "status": "STOPPED",
                "error": None,
                "updated_at": None,
            }
        return {
            "price": None,
            "status": "ERROR",
            "error": "No passive live price source is available for this runtime.",
            "updated_at": None,
        }
