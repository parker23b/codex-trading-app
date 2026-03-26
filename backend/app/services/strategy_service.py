from collections import defaultdict
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.broker import BrokerOrderStatus, OrderDirection, OrderRequest
from app.core.config import get_settings
from app.core.ig_broker import IGBrokerError
from app.core.signals import EntrySignal, ExitSignal, SignalStatus
from app.core.instrument_catalog import list_instruments
from app.core.runtime import runtime_manager
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus, Position, Trade, utc_now
from app.strategies.registry import strategy_registry
from app.services.portfolio_risk_service import PortfolioRiskService
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService


class StrategyService:
    def __init__(self, session: Session | None = None):
        self.session = session
        self.settings = get_settings()
        self.risk_service = PortfolioRiskService(session)
        self.runtime_state_service = RuntimeStateService(session) if session is not None else None

    def list_strategies(self) -> list[dict[str, object]]:
        if self.session is None:
            raise ValueError("A database session is required to list strategies.")

        trade_service = TradeService(self.session)
        trades = trade_service.list_trades()
        positions = trade_service.list_positions()
        open_positions_by_strategy: dict[str, list] = defaultdict(list)
        for position in positions:
            open_positions_by_strategy[position.strategy_name].append(position)
        trades_by_strategy: dict[str, list[float]] = defaultdict(list)
        for trade in trades:
            trades_by_strategy[trade.strategy_name].append(trade.pnl)

        strategies: list[dict[str, object]] = []
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
                    "active_instruments": [engine.instrument for _, engine in active_engines],
                    "active_runtime_count": len(active_engines),
                    "open_position_count": len(strategy_positions),
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
                            "value": parameter.value,
                            "step": parameter.step,
                        }
                        for parameter in metadata.parameters
                    ],
                }
            )
        return strategies

    def start_strategy(self, strategy_name: str, instrument: str) -> None:
        engine = runtime_manager.start(strategy_name=strategy_name, instrument=instrument)
        if self.runtime_state_service is not None:
            self.runtime_state_service.sync_engine_state(
                strategy_name=strategy_name,
                instrument=instrument,
                status="RUNNING",
                recovery_state="RUNNING",
                last_price_seen=runtime_manager.get_last_price(instrument),
                last_price_seen_at=runtime_manager.get_last_price_updated_at(instrument),
                current_position=engine.current_position,
            )

    def stop_strategy(self, instrument: str | None = None, strategy_name: str | None = None) -> None:
        stopped_engines = runtime_manager.stop(instrument=instrument, strategy_name=strategy_name)
        if self.runtime_state_service is not None:
            for engine in stopped_engines:
                self.runtime_state_service.mark_stopped(engine.runtime_id)

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
        if self.session is None:
            raise ValueError("A database session is required to process price updates.")

        trade_service = TradeService(self.session)
        open_positions = trade_service.list_positions()
        trades = trade_service.list_trades()
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
                )
        for update_result in update_results:
            engine = update_result.engine
            metadata = strategy_registry.get_metadata(engine.strategy.name)
            existing_position = trade_service.get_open_position(
                instrument,
                strategy_name=engine.strategy.name,
                broker_reference=engine.current_position.broker_reference if engine.current_position else None,
            )
            signal = update_result.signal

            if isinstance(signal, EntrySignal):
                execution = trade_service.create_execution(
                    Execution(
                        strategy_name=signal.strategy_name,
                        instrument=signal.instrument,
                        phase=ExecutionPhase.ENTRY.value,
                        status=ExecutionStatus.SIGNAL_GENERATED.value,
                        signal_time=signal.signal_at,
                        requested_size=signal.size,
                        requested_price=signal.observed_price,
                        reason="Entry signal generated",
                        details={
                            "direction": signal.direction.value,
                            "market_status": signal.market_status,
                            "tradable": signal.tradable,
                        },
                    )
                )
                signal.risk_percent = metadata.risk_per_trade if metadata else 0.0
                signal = self.risk_service.assess_entry(
                    signal,
                    open_positions=open_positions,
                    trades=trades,
                )
                if signal.status is SignalStatus.APPROVED:
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.RISK_APPROVED,
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
                    except Exception:
                        engine.current_position = None
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
                            )
                        open_positions = trade_service.list_positions()
                else:
                    trade_service.transition_execution(
                        execution,
                        status=ExecutionStatus.RISK_REJECTED,
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
                    instrument,
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
                execution = trade_service.create_execution(
                    Execution(
                        strategy_name=signal.strategy_name,
                        instrument=signal.instrument,
                        phase=ExecutionPhase.CLOSE.value,
                        status=ExecutionStatus.SIGNAL_GENERATED.value,
                        signal_time=signal.signal_at,
                        broker_reference=signal.position.broker_reference if signal.position is not None else None,
                        local_position_id=signal.position.id if signal.position is not None else None,
                        requested_size=signal.position.size if signal.position is not None else None,
                        requested_price=signal.observed_price,
                        reason="Exit signal generated",
                        details={
                            "market_status": signal.market_status,
                            "tradable": signal.tradable,
                        },
                    )
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
                    instrument,
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
        order_request = OrderRequest(
            instrument=signal.instrument,
            direction=signal.direction,
            size=signal.size,
            price=signal.observed_price,
            strategy_name=signal.strategy_name,
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            submitted_at=utc_now(),
            reason="Entry order submitted",
        )
        try:
            order = engine.broker.place_order(order_request)
        except Exception as exc:
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.FAILED,
                error_message=str(exc),
                reason="Entry order submission failed",
                requires_manual_review=False,
            )
            raise

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
            local_position_id=persisted_position.id,
            broker_reference=persisted_position.broker_reference,
            completed_at=persisted_position.broker_open_confirmed_at or persisted_position.open_time,
            average_fill_price=persisted_position.open_price,
            filled_size=persisted_position.size,
            reason="Position opened",
        )
        engine.strategy.on_position_opened(direction=signal.direction, entry_price=order.price)
        engine.current_position = persisted_position
        return persisted_position

    @staticmethod
    def _execute_exit_signal(*, engine, signal: ExitSignal, trade_service: TradeService, execution: Execution) -> Trade:
        if engine.current_position is None:
            raise ValueError(f"No active engine position for {signal.strategy_name} on {signal.instrument}.")
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.CLOSE_REQUESTED,
            reason="Close requested",
        )
        trade_service.transition_execution(
            execution,
            status=ExecutionStatus.ORDER_SUBMITTED,
            submitted_at=utc_now(),
            reason="Close order submitted",
        )
        try:
            closed_order = engine.broker.close_position(
                signal.instrument,
                broker_reference=engine.current_position.broker_reference,
            )
        except Exception as exc:
            trade_service.transition_execution(
                execution,
                status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
                error_message=str(exc),
                reason="Close request failed",
                requires_manual_review=True,
            )
            raise

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
            broker_reference=order.broker_reference,
            completed_at=order.executed_at,
            filled_size=order.filled_size or order.size,
            average_fill_price=order.average_fill_price or order.price,
            reason=order.reason or completed_reason,
            error_code=order.error_code,
            error_message=order.error_message,
            requires_manual_review=order.requires_manual_review,
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
                "updated_at": get_ig_streaming_service().get_health().last_tick_at,
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
