from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlmodel import Session, select

from app.core.broker import BrokerOrderStatus, OrderDirection, OrderRequest
from app.core.config import get_settings
from app.core.ig_broker import IGBrokerError
from app.core.logging import get_logger
from app.core.signals import EntrySignal, ExitSignal, SignalCandidate, SignalStatus, TradeAllocationDecision
from app.core.instrument_catalog import list_instruments
from app.core.runtime import runtime_manager
from app.models.strategy_deployment import StrategyDeployment
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus, Position, Trade, clone_position, utc_now
from app.strategies.registry import strategy_registry
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.market_status_service import MarketStatus, get_market_status_service
from app.services.portfolio_risk_service import PortfolioRiskService
from app.services.runtime_state_service import RuntimeStateService
from app.services.strategy_governance_service import StrategyGovernanceService
from app.services.trade_allocator_service import TradeAllocatorService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class StrategyService:
    RETRYABLE_EXECUTION_STATUSES = {
        ExecutionStatus.SIGNAL_GENERATED.value,
        ExecutionStatus.RISK_APPROVED.value,
        ExecutionStatus.CLOSE_REQUESTED.value,
        ExecutionStatus.ORDER_SUBMITTED.value,
        ExecutionStatus.ORDER_ACKNOWLEDGED.value,
        ExecutionStatus.FILL_PARTIAL.value,
        ExecutionStatus.FAILED.value,
        ExecutionStatus.NEEDS_MANUAL_REVIEW.value,
    }
    SAFE_CLOSE_RETRY_STATUSES = {
        ExecutionStatus.SIGNAL_GENERATED.value,
        ExecutionStatus.CLOSE_REQUESTED.value,
    }

    def __init__(self, session: Session | None = None):
        self.session = session
        self.settings = get_settings()
        self.event_service = domain_event_service
        self.health_service = get_health_service()
        self.market_status_service = get_market_status_service()
        self.risk_service = PortfolioRiskService(session)
        self.trade_allocator = TradeAllocatorService(session)
        self.runtime_state_service = RuntimeStateService(session) if session is not None else None

    def list_strategies(self) -> list[dict[str, object]]:
        if self.session is None:
            raise ValueError("A database session is required to list strategies.")

        trade_service = TradeService(self.session)
        trades = trade_service.list_trades()
        positions = trade_service.list_positions()
        executions = trade_service.list_executions(limit=250)
        open_positions_by_strategy: dict[str, list] = defaultdict(list)
        for position in positions:
            open_positions_by_strategy[position.strategy_name].append(position)
        trades_by_strategy: dict[str, list[float]] = defaultdict(list)
        for trade in trades:
            trades_by_strategy[trade.strategy_name].append(trade.pnl)
        latest_execution_warning_by_key: dict[tuple[str, str], Execution] = {}
        for execution in executions:
            if execution.status not in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value, ExecutionStatus.RISK_REJECTED.value}:
                continue
            key = (execution.strategy_name, execution.instrument)
            if key not in latest_execution_warning_by_key:
                latest_execution_warning_by_key[key] = execution

        strategies: list[dict[str, object]] = []
        governance_by_name = {
            record.strategy_name: record
            for record in StrategyGovernanceService(self.session).list_strategies()
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
            primary_instrument = primary_engine.instrument if primary_engine else metadata.default_instrument
            primary_warning = latest_execution_warning_by_key.get((metadata.name, primary_instrument))
            governance = governance_by_name.get(metadata.name)
            deployment = deployment_by_name.get(metadata.name)
            primary_runtime = runtimes_by_key.get((metadata.name, primary_instrument))
            active_parameter_values = (
                primary_runtime.parameters
                if primary_runtime is not None and primary_runtime.parameters
                else {
                    parameter.key: parameter.value
                    for parameter in metadata.parameters
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
                    "price_status": price_snapshot["status"] if price_snapshot else "STOPPED",
                    "price_error": price_snapshot["error"] if price_snapshot else None,
                    "last_price_updated_at": price_snapshot["updated_at"] if price_snapshot else None,
                    "trade_count": trade_count,
                    "win_rate": round((win_count / trade_count) * 100, 2) if trade_count else 0.0,
                    "account_type": self.settings.broker_mode,
                    "position_size": metadata.position_size,
                    "risk_per_trade": metadata.risk_per_trade,
                    "supported_asset_classes": list(metadata.supported_asset_classes),
                    "available_profiles": [profile.name for profile in metadata.parameter_profiles],
                    "governance_approval_state": governance.approval_state if governance is not None else "UNKNOWN",
                    "autonomous_operation_allowed": (
                        governance.autonomous_operation_allowed if governance is not None else False
                    ),
                    "emergency_stop": governance.emergency_stop if governance is not None else False,
                    "deployment_state": deployment.state if deployment is not None else "UNASSIGNED",
                    "deployment_profile": deployment.selected_profile if deployment is not None else None,
                    "deployment_parameters": deployment.selected_profile_parameters if deployment is not None else {},
                    "deployment_instrument": deployment.selected_instrument if deployment is not None else None,
                    "deployment_reason": (
                        deployment.blocked_reason
                        or deployment.degraded_reason
                        or deployment.suitability_reason
                        if deployment is not None
                        else None
                    ),
                    "active_instruments": [engine.instrument for _, engine in active_engines],
                    "active_runtime_count": len(active_engines),
                    "open_position_count": len(strategy_positions),
                    "warning_message": (
                        primary_warning.error_message or primary_warning.reason
                        if primary_warning is not None
                        else None
                    ),
                    "warning_instrument": primary_warning.instrument if primary_warning is not None else None,
                    "warning_status": primary_warning.status if primary_warning is not None else None,
                    "active_runtimes": [
                        {
                            "strategy_name": metadata.name,
                            "instrument": engine.instrument,
                            "runtime_key": f"{metadata.name}:{engine.instrument}",
                            "has_open_position": engine.current_position is not None,
                            "broker_reference": engine.current_position.broker_reference if engine.current_position else None,
                            "direction": engine.current_position.direction if engine.current_position else None,
                            "current_price": engine.current_position.current_price if engine.current_position else None,
                            "unrealized_pnl": engine.current_position.unrealized_pnl if engine.current_position else None,
                            "recovery_state": (
                                runtimes_by_key.get((metadata.name, engine.instrument)).recovery_state
                                if runtimes_by_key.get((metadata.name, engine.instrument)) is not None
                                else "EPHEMERAL"
                            ),
                            "control_mode": (
                                runtimes_by_key.get((metadata.name, engine.instrument)).control_mode
                                if runtimes_by_key.get((metadata.name, engine.instrument)) is not None
                                else "EPHEMERAL"
                            ),
                            "deployment_id": (
                                runtimes_by_key.get((metadata.name, engine.instrument)).deployment_id
                                if runtimes_by_key.get((metadata.name, engine.instrument)) is not None
                                else None
                            ),
                            "recovery_reason": (
                                runtimes_by_key.get((metadata.name, engine.instrument)).recovery_reason
                                if runtimes_by_key.get((metadata.name, engine.instrument)) is not None
                                else None
                            ),
                        }
                        for _, engine in active_engines
                    ],
                    "open_positions": [
                        {
                            "broker_reference": position.broker_reference,
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
                            "runtime_id": runtime.runtime_id,
                            "instrument": runtime.instrument,
                            "status": runtime.status,
                            "recovery_state": runtime.recovery_state,
                            "recovery_reason": runtime.recovery_reason,
                            "last_heartbeat_at": runtime.last_heartbeat_at,
                            "last_price_seen": runtime.last_price_seen,
                            "last_price_seen_at": runtime.last_price_seen_at,
                            "control_mode": runtime.control_mode,
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
                            "value": active_parameter_values.get(parameter.key, parameter.value),
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
        deployment_id: int | None = None,
        profile_name: str | None = None,
        strategy_parameters: dict[str, object] | None = None,
    ) -> None:
        engine = runtime_manager.start(
            strategy_name=strategy_name,
            instrument=instrument,
            profile_name=profile_name,
            strategy_parameters=strategy_parameters,
        )
        if self.runtime_state_service is not None:
            self.runtime_state_service.sync_engine_state(
                strategy_name=strategy_name,
                instrument=instrument,
                status="RUNNING",
                recovery_state="RUNNING",
                control_mode=control_mode,
                deployment_id=deployment_id,
                active_profile_name=engine.active_profile_name,
                parameters=engine.strategy_parameters,
                last_price_seen=runtime_manager.get_last_price(instrument),
                last_price_seen_at=runtime_manager.get_last_price_updated_at(instrument),
                current_position=engine.current_position,
            )
        self.event_service.record_event(
            event_type="strategy.runtime_started",
            category="strategy",
            severity="info",
            source="strategy_service.start_strategy",
            title="Strategy runtime started",
            message=f"{strategy_name} started on {instrument}.",
            runtime_id=engine.runtime_id,
            strategy_name=strategy_name,
            instrument=instrument,
            payload_json={
                "status": "RUNNING",
                "control_mode": control_mode,
                "deployment_id": deployment_id,
                "active_profile_name": engine.active_profile_name,
                "strategy_parameters": engine.strategy_parameters,
            },
        )
        self._refresh_paused_strategy_count()

    def stop_strategy(self, instrument: str | None = None, strategy_name: str | None = None) -> None:
        stopped_engines = runtime_manager.stop(instrument=instrument, strategy_name=strategy_name)
        if self.runtime_state_service is not None:
            for engine in stopped_engines:
                self.runtime_state_service.mark_stopped(engine.runtime_id)
        for engine in stopped_engines:
            self.event_service.record_event(
                event_type="strategy.runtime_stopped",
                category="strategy",
                severity="info",
                source="strategy_service.stop_strategy",
                title="Strategy runtime stopped",
                message=f"{engine.strategy.name} stopped on {engine.instrument}.",
                runtime_id=engine.runtime_id,
                strategy_name=engine.strategy.name,
                instrument=engine.instrument,
                payload_json={"status": "STOPPED"},
            )
        self._refresh_paused_strategy_count()

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
        candidates = self.allocate_signal_candidates(candidates, received_at=received_at)
        self.orchestrate_signal_candidates(
            candidates,
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
            raise ValueError("A database session is required to evaluate price updates.")

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
                    metadata=strategy_registry.get_metadata(update_result.engine.strategy.name),
                )
            )
        return candidates

    def allocate_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[SignalCandidate]:
        if not self.settings.trade_allocator_enabled:
            return candidates

        decisions = self.trade_allocator.allocate(candidates, received_at=received_at)
        selected_candidates: list[SignalCandidate] = []
        for decision in decisions:
            if decision.selected:
                self._record_allocator_selection(decision)
                selected_candidates.append(decision.candidate)
                continue
            self._record_allocator_rejection(decision)
        return selected_candidates

    def orchestrate_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        price: float,
        bid: float | None = None,
        ask: float | None = None,
        received_at: datetime | None = None,
    ) -> None:
        if self.session is None:
            raise ValueError("A database session is required to orchestrate signal candidates.")

        trade_service = TradeService(self.session)
        open_positions = trade_service.list_positions()
        trades = trade_service.list_trades()

        for candidate in candidates:
            engine = candidate.engine
            metadata = candidate.metadata
            existing_position = trade_service.get_open_position(
                candidate.instrument,
                strategy_name=engine.strategy.name,
                broker_reference=engine.current_position.broker_reference if engine.current_position else None,
            )
            signal = candidate.signal

            if isinstance(signal, EntrySignal):
                execution, should_submit = self._prepare_execution(
                    trade_service=trade_service,
                    strategy_name=signal.strategy_name,
                    instrument=signal.instrument,
                    phase=ExecutionPhase.ENTRY.value,
                    signal_time=signal.signal_at,
                    requested_size=signal.size,
                    requested_price=signal.observed_price,
                    reason="Entry signal generated",
                    details={
                        "action_key": self._entry_action_key(signal),
                        "direction": signal.direction.value,
                        "market_status": signal.market_status,
                        "tradable": signal.tradable,
                    },
                )
                if not should_submit:
                    continue
                self.event_service.record_event(
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
                    payload_json={
                        "direction": signal.direction.value,
                        "observed_price": signal.observed_price,
                        "size": signal.size,
                        "market_status": signal.market_status,
                        "tradable": signal.tradable,
                        "source_tier": candidate.source_tier,
                    },
                    created_at=signal.signal_at,
                )
                signal.risk_percent = metadata.risk_per_trade if metadata else 0.0
                signal = self._apply_market_status_gate(engine=engine, signal=signal)
                if signal.status is not SignalStatus.REJECTED:
                    signal = self.risk_service.assess_entry(
                        signal,
                        open_positions=open_positions,
                        trades=trades,
                    )
                if signal.status is SignalStatus.APPROVED:
                    signal = self._apply_broker_entry_constraints(engine=engine, signal=signal)
                if signal.status is SignalStatus.APPROVED:
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.RISK_APPROVED,
                        client_request_id=execution.client_request_id,
                        reason=signal.reason or "Risk approved",
                        details={
                            "risk_percent": signal.risk_percent,
                            "risk_rejection_layer": signal.rejection_layer,
                            "risk_audit_summary": signal.audit_summary,
                            "risk_audit_trail": signal.audit_trail,
                        },
                    )
                    try:
                        created_position = self._execute_entry_signal(
                            engine=engine,
                            signal=signal,
                            trade_service=trade_service,
                            execution=execution,
                        )
                    except Exception as exc:
                        engine.current_position = None
                        engine.strategy.on_entry_failed()
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
                                last_price_seen=price,
                                last_price_seen_at=received_at or datetime.now(UTC),
                                current_position=created_position,
                                current_position_broker_reference=created_position.broker_reference,
                            )
                        open_positions = trade_service.list_positions()
                else:
                    logger.info(
                        "Entry signal rejected by risk controls",
                        extra={
                            "strategy": signal.strategy_name,
                            "instrument": signal.instrument,
                            "reason": signal.reason,
                            "rejection_layer": signal.rejection_layer,
                        },
                    )
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.RISK_REJECTED,
                        client_request_id=execution.client_request_id,
                        reason=signal.reason or "Risk rejected",
                        requires_manual_review=False,
                        details={
                            "risk_percent": signal.risk_percent,
                            "risk_rejection_layer": signal.rejection_layer,
                            "risk_audit_summary": signal.audit_summary,
                            "risk_audit_trail": signal.audit_trail,
                        },
                    )
                    engine.current_position = None

            if engine.current_position is not None:
                existing_position = trade_service.get_open_position(
                    candidate.instrument,
                    strategy_name=engine.strategy.name,
                    broker_reference=engine.current_position.broker_reference,
                )

                risk_percent = metadata.risk_per_trade if metadata else 0.0
                mark_price = self._mark_price(direction=engine.current_position.direction, price=price, bid=bid, ask=ask)
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
                    engine.current_position.reason = f"{engine.strategy.name} signal active"
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
                execution, should_submit = self._prepare_execution(
                    trade_service=trade_service,
                    strategy_name=signal.strategy_name,
                    instrument=signal.instrument,
                    phase=ExecutionPhase.CLOSE.value,
                    signal_time=signal.signal_at,
                    requested_size=signal.position.size if signal.position is not None else None,
                    requested_price=signal.observed_price,
                    reason="Exit signal generated",
                    broker_reference=signal.position.broker_reference if signal.position is not None else None,
                    local_position_id=signal.position.id if signal.position is not None else None,
                    details={
                        "action_key": self._close_action_key(signal),
                        "market_status": signal.market_status,
                        "tradable": signal.tradable,
                    },
                )
                if not should_submit:
                    continue
                self.event_service.record_event(
                    event_type="strategy.exit_candidate",
                    category="strategy",
                    severity="info",
                    source="strategy_service.process_price_update",
                    title="Strategy produced exit candidate",
                    message=f"{signal.strategy_name} proposed an exit on {signal.instrument}.",
                    correlation_id=execution.client_request_id,
                    strategy_name=signal.strategy_name,
                    instrument=signal.instrument,
                    position_id=signal.position.id if signal.position is not None else None,
                    execution_id=execution.id,
                    payload_json={
                        "observed_price": signal.observed_price,
                        "market_status": signal.market_status,
                        "tradable": signal.tradable,
                        "broker_reference": signal.position.broker_reference if signal.position is not None else None,
                        "source_tier": candidate.source_tier,
                    },
                    created_at=signal.signal_at,
                )
                try:
                    trade = self._execute_exit_signal(
                        engine=engine,
                        signal=signal,
                        trade_service=trade_service,
                        execution=execution,
                    )
                except Exception:
                    continue
                trade.outcome = "win" if trade.pnl > 0 else "loss"
                risk_budget = metadata.risk_per_trade if metadata and metadata.risk_per_trade else 1.0
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
                        broker_sync_status="CONFIRMED",
                        broker_confirmed_at=trade.close_time,
                    )
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.CLOSE_CONFIRMED,
                        client_request_id=execution.client_request_id,
                        local_position_id=closed_position.id,
                        completed_at=trade.close_time,
                        average_fill_price=trade.close_price,
                        filled_size=trade.size,
                        reason="Position close confirmed",
                    )
                persisted_trade = trade_service.record_trade(trade)
                trade_service.transition_execution(
                    execution,
                    status=ExecutionStatus.CLOSE_CONFIRMED,
                    client_request_id=execution.client_request_id,
                    local_trade_id=persisted_trade.id,
                    completed_at=trade.close_time,
                    average_fill_price=trade.close_price,
                    filled_size=trade.size,
                    reason="Position close confirmed",
                )
                if self.runtime_state_service is not None:
                    self.runtime_state_service.sync_engine_state(
                        strategy_name=engine.strategy.name,
                        instrument=engine.instrument,
                        status="RUNNING",
                        recovery_state="RUNNING",
                        last_price_seen=trade.close_price,
                        last_price_seen_at=trade.close_time,
                        current_position=None,
                    )
                open_positions = trade_service.list_positions()
                trades = trade_service.list_trades()
        self._refresh_paused_strategy_count()

    def _record_allocator_rejection(self, decision: TradeAllocationDecision) -> None:
        signal = decision.candidate.signal
        if not isinstance(signal, EntrySignal):
            return
        self.event_service.record_event(
            event_type="strategy.trade_allocator_rejected",
            category="strategy",
            severity="info",
            source="strategy_service.allocate_signal_candidates",
            title="Trade allocator rejected signal candidate",
            message=f"{signal.strategy_name} entry on {signal.instrument} was filtered before execution orchestration.",
            strategy_name=signal.strategy_name,
            instrument=signal.instrument,
            payload_json={
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "score": decision.score,
                "direction": signal.direction.value,
                "observed_price": signal.observed_price,
                "source_tier": decision.candidate.source_tier,
            },
            created_at=signal.signal_at,
        )

    def _record_allocator_selection(self, decision: TradeAllocationDecision) -> None:
        signal = decision.candidate.signal
        if not isinstance(signal, EntrySignal):
            return
        self.event_service.record_event(
            event_type="strategy.trade_allocator_selected",
            category="strategy",
            severity="info",
            source="strategy_service.allocate_signal_candidates",
            title="Trade allocator selected signal candidate",
            message=f"{signal.strategy_name} entry on {signal.instrument} advanced to risk and execution orchestration.",
            strategy_name=signal.strategy_name,
            instrument=signal.instrument,
            payload_json={
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "score": decision.score,
                "direction": signal.direction.value,
                "observed_price": signal.observed_price,
                "source_tier": decision.candidate.source_tier,
            },
            created_at=signal.signal_at,
        )

    @staticmethod
    def _apply_broker_entry_constraints(*, engine, signal: EntrySignal) -> EntrySignal:
        try:
            market_details = engine.broker.get_market_details(signal.instrument)
        except Exception as exc:
            logger.warning(
                "Unable to load broker market details during entry validation",
                extra={
                    "strategy": signal.strategy_name,
                    "instrument": signal.instrument,
                    "error": str(exc),
                },
            )
            return signal

        min_deal_size = market_details.min_deal_size
        if min_deal_size is None or signal.size >= min_deal_size:
            return signal

        reason = (
            f"Requested size {signal.size} is below broker minimum deal size "
            f"{min_deal_size} for {signal.instrument}."
        )
        audit_trail = list(signal.audit_trail)
        audit_trail.append(
            {
                "layer": "broker_constraints",
                "status": "REJECTED",
                "passed": False,
                "reason": reason,
                "checks": [
                    {
                        "code": "min_deal_size",
                        "passed": False,
                        "reason": reason,
                        "actual": signal.size,
                        "limit": min_deal_size,
                    }
                ],
            }
        )
        audit_summary = dict(signal.audit_summary)
        audit_summary.update(
            {
                "approved": False,
                "rejection_layer": "broker_constraints",
                "min_deal_size": min_deal_size,
            }
        )
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=reason,
            rejection_layer="broker_constraints",
            audit_trail=audit_trail,
            audit_summary=audit_summary,
        )

    def _apply_market_status_gate(self, *, engine, signal: EntrySignal) -> EntrySignal:
        status = self.market_status_service.get_status(signal.instrument, broker=engine.broker, now=signal.signal_at)
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
    def _calculate_open_pnl(*, direction: str, open_price: float, current_price: float, size: float) -> float:
        multiplier = 1 if direction == "BUY" else -1
        return (current_price - open_price) * size * multiplier

    @staticmethod
    def _mark_price(*, direction: str, price: float, bid: float | None, ask: float | None) -> float:
        if direction == "BUY" and bid is not None:
            return bid
        if direction == "SELL" and ask is not None:
            return ask
        return price

    @staticmethod
    def _execute_entry_signal(*, engine, signal: EntrySignal, trade_service: TradeService, execution: Execution) -> Position:
        status = StrategyService._assert_market_status_allows_execution(
            engine=engine,
            instrument=signal.instrument,
            execution=execution,
            trade_service=trade_service,
            phase="entry_execution",
        )
        order_request = OrderRequest(
            instrument=signal.instrument,
            direction=signal.direction,
            size=signal.size,
            price=signal.observed_price,
            strategy_name=signal.strategy_name,
            client_request_id=execution.client_request_id,
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            submitted_at=utc_now(),
            client_request_id=execution.client_request_id,
            reason="Entry order submitted",
            details={"market_status_execution_check": status.model_dump(mode="json")},
        )
        started_at = perf_counter()
        try:
            order = engine.broker.place_order(order_request)
        except Exception as exc:
            get_health_service().update_broker_state(connected=False, latency_ms=(perf_counter() - started_at) * 1000)
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
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                client_request_id=execution.client_request_id,
                error_message=str(exc),
                reason="Entry order submission failed",
                requires_manual_review=False,
            )
            raise
        get_health_service().update_broker_state(connected=True, latency_ms=(perf_counter() - started_at) * 1000)
        StrategyService._record_order_health(order.status)

        StrategyService._transition_execution_from_broker_result(
            trade_service=trade_service,
            execution=execution,
            order=order,
            opened_reason="Entry order acknowledged",
            completed_reason="Entry fill received",
        )
        filled_size = order.filled_size or order.size
        if order.status in {BrokerOrderStatus.REJECTED, BrokerOrderStatus.FAILED, BrokerOrderStatus.CANCELLED} or filled_size <= 0:
            raise RuntimeError(f"Entry order for {signal.instrument} did not produce an open fill.")
        engine.current_position = Position(
            instrument=signal.instrument,
            broker_reference=order.broker_reference,
            direction=signal.direction.value,
            size=filled_size,
            open_price=order.average_fill_price or order.price,
            open_time=order.executed_at,
            strategy_name=signal.strategy_name,
            account_type=engine.broker.account_type.value,
            is_open=True,
            risk_percent=signal.risk_percent,
            current_price=order.average_fill_price or order.price,
            unrealized_pnl=0.0,
            reason=f"{signal.strategy_name} entry approved",
        )
        persisted_position = trade_service.record_broker_position(engine.current_position)
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.POSITION_OPENED,
            client_request_id=execution.client_request_id,
            local_position_id=persisted_position.id,
            broker_reference=persisted_position.broker_reference,
            completed_at=persisted_position.broker_open_confirmed_at or persisted_position.open_time,
            average_fill_price=persisted_position.open_price,
            filled_size=persisted_position.size,
            reason="Position opened",
        )
        engine.strategy.on_position_opened(direction=signal.direction, entry_price=order.price)
        engine.current_position = clone_position(persisted_position)
        return clone_position(persisted_position)

    @staticmethod
    def _execute_exit_signal(*, engine, signal: ExitSignal, trade_service: TradeService, execution: Execution) -> Trade:
        if engine.current_position is None:
            raise ValueError(f"No active engine position for {signal.strategy_name} on {signal.instrument}.")
        status = StrategyService._assert_market_status_allows_execution(
            engine=engine,
            instrument=signal.instrument,
            execution=execution,
            trade_service=trade_service,
            phase="exit_execution",
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.CLOSE_REQUESTED,
            client_request_id=execution.client_request_id,
            reason="Close requested",
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            submitted_at=utc_now(),
            client_request_id=execution.client_request_id,
            reason="Close order submitted",
            details={"market_status_execution_check": status.model_dump(mode="json")},
        )
        started_at = perf_counter()
        try:
            closed_order = engine.broker.close_position(
                signal.instrument,
                broker_reference=engine.current_position.broker_reference,
                client_request_id=execution.client_request_id,
            )
        except Exception as exc:
            get_health_service().update_broker_state(connected=False, latency_ms=(perf_counter() - started_at) * 1000)
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
                client_request_id=execution.client_request_id,
                error_message=str(exc),
                reason="Close request failed",
                requires_manual_review=True,
            )
            raise
        get_health_service().update_broker_state(connected=True, latency_ms=(perf_counter() - started_at) * 1000)
        StrategyService._record_order_health(closed_order.status)

        StrategyService._transition_execution_from_broker_result(
            trade_service=trade_service,
            execution=execution,
            order=closed_order,
            opened_reason="Close order acknowledged",
            completed_reason="Close fill received",
        )
        if closed_order.status is not BrokerOrderStatus.FILLED:
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                client_request_id=execution.client_request_id,
                completed_at=closed_order.executed_at,
                reason="Close did not complete fully",
                requires_manual_review=True,
            )
            raise RuntimeError(f"Close order for {signal.instrument} did not complete fully.")
        pnl = StrategyService._calculate_open_pnl(
            direction=engine.current_position.direction,
            open_price=engine.current_position.open_price,
            current_price=closed_order.average_fill_price or closed_order.price,
            size=engine.current_position.size,
        )
        trade = Trade(
            strategy_name=engine.current_position.strategy_name,
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
            account_type=engine.current_position.account_type,
        )
        engine.current_position.is_open = False
        engine.current_position.close_price = closed_order.average_fill_price or closed_order.price
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
    ) -> MarketStatus:
        status = get_market_status_service().get_status(
            instrument,
            broker=engine.broker,
            now=execution.last_transition_at or execution.signal_time or utc_now(),
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
    def _transition_execution_from_broker_result(
        *,
        trade_service: TradeService,
        execution: Execution,
        order,
        opened_reason: str,
        completed_reason: str,
    ) -> None:
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_ACKNOWLEDGED,
            client_request_id=order.client_request_id,
            broker_reference=order.broker_reference,
            submitted_at=order.submitted_at,
            acknowledged_at=order.acknowledged_at or order.executed_at,
            reason=order.reason or opened_reason,
            error_code=order.error_code,
            error_message=order.error_message,
            requires_manual_review=order.requires_manual_review,
        )
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
            client_request_id=order.client_request_id,
            broker_reference=order.broker_reference,
            completed_at=order.executed_at,
            filled_size=order.filled_size or order.size,
            average_fill_price=order.average_fill_price or order.price,
            reason=order.reason or completed_reason,
            error_code=order.error_code,
            error_message=order.error_message,
            requires_manual_review=order.requires_manual_review,
        )

    @classmethod
    def _generate_client_request_id(cls, prefix: str) -> str:
        normalized_prefix = prefix[:3].lower()
        return f"{normalized_prefix}-{uuid4().hex[:26]}"

    @staticmethod
    def _entry_action_key(signal: EntrySignal) -> str:
        return f"entry:{signal.strategy_name}:{signal.instrument}:{signal.direction.value}"

    @staticmethod
    def _close_action_key(signal: ExitSignal) -> str:
        position_ref = signal.position.broker_reference if signal.position is not None else "unknown"
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
        if reusable_execution is not None and reusable_execution.status in cls.RETRYABLE_EXECUTION_STATUSES:
            duplicate_attempt_count = int((reusable_execution.details or {}).get("duplicate_attempt_count") or 0) + 1
            duplicate_details = {
                **details,
                "duplicate_action_detected": True,
                "duplicate_attempt_count": duplicate_attempt_count,
                "last_duplicate_detected_at": utc_now().isoformat(),
                "last_duplicate_status": reusable_execution.status,
            }
            if phase == ExecutionPhase.CLOSE.value and reusable_execution.status not in cls.SAFE_CLOSE_RETRY_STATUSES:
                domain_event_service.record_event(
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
                    payload_json=duplicate_details,
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
                    client_request_id=reusable_execution.client_request_id,
                    broker_reference=broker_reference,
                    local_position_id=local_position_id,
                    reason=f"{reason} retried with persisted client request id",
                    details=duplicate_details,
                ),
                True,
            )

        client_request_id = cls._generate_client_request_id("ent" if phase == ExecutionPhase.ENTRY.value else "cls")
        return (
            trade_service.create_execution(
                Execution(
                    strategy_name=strategy_name,
                    instrument=instrument,
                    phase=phase,
                    status=ExecutionStatus.SIGNAL_GENERATED.value,
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
    def _resolve_price_snapshot(instrument: str, fallback_price: float | None = None) -> dict[str, object]:
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
                age_seconds = (datetime.now(UTC) - updated_at.astimezone(UTC)).total_seconds()
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
        engine = instrument_engines[0][1] if instrument_engines else None
        if engine is None:
            return {"price": None, "status": "STOPPED", "error": None, "updated_at": None}
        try:
            price = engine.broker.get_latest_price(instrument)
            return {"price": price, "status": "REST", "error": None, "updated_at": None}
        except IGBrokerError as exc:
            return {"price": None, "status": "ERROR", "error": str(exc), "updated_at": None}
