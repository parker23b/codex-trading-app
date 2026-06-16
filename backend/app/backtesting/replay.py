from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.backtesting.candles import HistoricalCandle
from app.backtesting.clock import SimulatedClock
from app.backtesting.execution import (
    ExecutionAssumptions,
    SimulatedExecutionAdapter,
    SimulatedOpenPositionResult,
    SimulatedPosition,
    SimulatedTradeResult,
)
from app.backtesting.metrics import (
    PERCENT_RISK_SIZING_ABSOLUTE_TOLERANCE,
    EquitySample,
    calculate_grouped_metrics,
    calculate_metrics,
)
from app.core.broker import OrderDirection
from app.core.strategy_evaluation import (
    StrategyDecision,
    StrategyDecisionKind,
    evaluate_strategy_update,
)
from app.strategies.base import PriceUpdate, Strategy


@dataclass(frozen=True, slots=True)
class ReplayConfiguration:
    starting_capital: float
    position_sizing_mode: str
    risk_configuration: dict[str, Any]
    execution_assumptions: ExecutionAssumptions
    open_position_treatment: str
    trading_start_at: datetime | None = None
    warmup_mode: str = "NONE"
    warmup_candle_count: int = 0


@dataclass(frozen=True, slots=True)
class ReplayWarning:
    code: str
    message: str
    instrument: str | None = None
    timestamp: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplayResult:
    trades: list[SimulatedTradeResult]
    equity: list[EquitySample]
    metrics: dict[str, object]
    metrics_by_instrument: dict[str, dict[str, object]]
    warnings: list[ReplayWarning]
    open_positions: list[SimulatedOpenPositionResult]
    effective_start_at: datetime
    effective_end_at: datetime
    pricing_modes: tuple[str, ...]


@dataclass(slots=True)
class _PendingOrder:
    decision: StrategyDecision
    created_at: datetime


class BacktestReplayEngine:
    """Chronological candle-close evaluation with next-candle-open execution."""

    def __init__(
        self,
        *,
        strategies: dict[str, Strategy],
        configuration: ReplayConfiguration,
        clock: SimulatedClock,
    ) -> None:
        self.strategies = strategies
        self.configuration = configuration
        self.clock = clock
        self.execution = SimulatedExecutionAdapter(configuration.execution_assumptions)
        for strategy in strategies.values():
            strategy.bind_clock(clock)

    def run(
        self, candles_by_instrument: dict[str, list[HistoricalCandle]]
    ) -> ReplayResult:
        events = sorted(
            (
                candle
                for instrument in sorted(candles_by_instrument)
                for candle in candles_by_instrument[instrument]
            ),
            key=lambda candle: (candle.timestamp, candle.instrument),
        )
        if not events:
            raise ValueError("Replay requires at least one candle.")
        trading_start_at = self.configuration.trading_start_at or events[0].timestamp
        if not any(candle.timestamp >= trading_start_at for candle in events):
            raise ValueError("Replay requires at least one tradable candle.")

        positions: dict[str, SimulatedPosition] = {}
        pending_entries: dict[str, _PendingOrder] = {}
        pending_exits: dict[str, _PendingOrder] = {}
        latest_candles: dict[str, HistoricalCandle] = {}
        trades: list[SimulatedTradeResult] = []
        equity: list[EquitySample] = []
        warnings: list[ReplayWarning] = []
        pricing_modes: set[str] = set()
        cash = self.configuration.starting_capital

        timestamps = sorted({candle.timestamp for candle in events})
        by_timestamp: dict[datetime, list[HistoricalCandle]] = {
            timestamp: [] for timestamp in timestamps
        }
        for candle in events:
            by_timestamp[candle.timestamp].append(candle)

        for timestamp in timestamps:
            self.clock.advance_to(timestamp)
            rows = sorted(by_timestamp[timestamp], key=lambda item: item.instrument)
            trading_active = timestamp >= trading_start_at
            close_timestamps = {candle.close_timestamp for candle in rows}
            if len(close_timestamps) != 1:
                raise ValueError(
                    "Candles sharing an open timestamp must share a close timestamp."
                )
            close_timestamp = next(iter(close_timestamps))
            for candle in rows:
                instrument = candle.instrument
                latest_candles[instrument] = candle
                pricing_modes.add(self.execution.pricing_mode(candle))

            if trading_active:
                # Execute every queued action at the shared candle open before any
                # strategy can observe the current candle's high, low, or close.
                for candle in rows:
                    instrument = candle.instrument
                    strategy = self.strategies[instrument]

                    if instrument in pending_exits and instrument in positions:
                        trade = self.execution.close_position(
                            position=positions.pop(instrument),
                            candle=candle,
                            exit_reason="STRATEGY_EXIT_NEXT_OPEN",
                        )
                        cash += self._cash_settlement(trade)
                        trades.append(trade)
                        strategy.on_position_closed()
                        del pending_exits[instrument]

                for candle in rows:
                    instrument = candle.instrument
                    strategy = self.strategies[instrument]
                    if instrument in pending_entries and instrument not in positions:
                        pending = pending_entries.pop(instrument)
                        size, sizing_metadata = self._position_size(
                            decision=pending.decision,
                            candle=candle,
                            equity=self._current_equity(
                                cash=cash,
                                positions=positions,
                                latest_candles=latest_candles,
                                open_timestamp=timestamp,
                            ),
                        )
                        if size <= 0:
                            strategy.on_entry_failed()
                            warnings.append(
                                ReplayWarning(
                                    code="ENTRY_REJECTED_SIZE",
                                    message="Signal was rejected because deterministic sizing returned zero.",
                                    instrument=instrument,
                                    timestamp=timestamp,
                                )
                            )
                        elif len(positions) >= int(
                            self.configuration.risk_configuration.get(
                                "max_open_positions", len(self.strategies)
                            )
                        ):
                            strategy.on_entry_failed()
                            warnings.append(
                                ReplayWarning(
                                    code="ENTRY_REJECTED_POSITION_LIMIT",
                                    message="Signal was rejected by the simulated open-position limit.",
                                    instrument=instrument,
                                    timestamp=timestamp,
                                )
                            )
                        else:
                            hints = pending.decision.hints
                            if pending.decision.direction is None:
                                raise ValueError(
                                    f"Entry decision for {instrument} has no direction."
                                )
                            position = self.execution.open_position(
                                instrument=instrument,
                                direction=pending.decision.direction,
                                size=size,
                                candle=candle,
                                stop_loss_price=(
                                    _optional_float(hints.get("stop_loss_price"))
                                    or _optional_float(
                                        sizing_metadata.get("sizing_stop_price")
                                    )
                                ),
                                take_profit_price=_optional_float(
                                    hints.get("take_profit_price")
                                ),
                                metadata={
                                    "signal_at": pending.created_at.isoformat(),
                                    **sizing_metadata,
                                },
                            )
                            positions[instrument] = position
                            cash -= position.entry_fee
                            strategy.on_position_opened(
                                direction=position.direction,
                                entry_price=position.open_price,
                            )

                for candle in rows:
                    instrument = candle.instrument
                    strategy = self.strategies[instrument]
                    position = positions.get(instrument)
                    if position is not None:
                        threshold_trade = self.execution.threshold_exit(
                            position=position, candle=candle
                        )
                        if threshold_trade is not None:
                            positions.pop(instrument)
                            cash += self._cash_settlement(threshold_trade)
                            trades.append(threshold_trade)
                            strategy.on_position_closed()
                            if threshold_trade.conservative_ambiguity:
                                warnings.append(
                                    ReplayWarning(
                                        code="CONSERVATIVE_INTRACANDLE_EXIT",
                                        message=(
                                            "Stop loss and take profit were both inside one candle; "
                                            "the less favorable stop-loss outcome was used."
                                        ),
                                        instrument=instrument,
                                        timestamp=timestamp,
                                        details={
                                            "trade_position_id": threshold_trade.position.id
                                        },
                                    )
                                )

            self.clock.advance_to(close_timestamp)
            for candle in rows:
                instrument = candle.instrument
                strategy = self.strategies[instrument]
                decision = evaluate_strategy_update(
                    strategy=strategy,
                    update=self._price_update(candle),
                    has_open_position=instrument in positions,
                )
                if trading_active and decision is not None:
                    if (
                        decision.kind is StrategyDecisionKind.ENTRY
                        and instrument not in positions
                        and instrument not in pending_entries
                    ):
                        pending_entries[instrument] = _PendingOrder(
                            decision=decision, created_at=close_timestamp
                        )
                    elif (
                        decision.kind is StrategyDecisionKind.EXIT
                        and instrument in positions
                        and instrument not in pending_exits
                    ):
                        pending_exits[instrument] = _PendingOrder(
                            decision=decision, created_at=close_timestamp
                        )

            if trading_active:
                equity_value = self._current_equity(
                    cash=cash,
                    positions=positions,
                    latest_candles=latest_candles,
                )
                equity.append(
                    EquitySample(
                        timestamp=close_timestamp,
                        cash=cash,
                        unrealized_pnl=equity_value - cash,
                        equity=equity_value,
                        open_position_count=len(positions),
                    )
                )

        final_timestamp = equity[-1].timestamp
        if positions and self.configuration.open_position_treatment == "CLOSE_AT_END":
            for instrument in sorted(list(positions)):
                candle = latest_candles[instrument]
                trade = self.execution.close_position(
                    position=positions.pop(instrument),
                    candle=candle,
                    exit_reason="END_OF_RUN",
                    at="close",
                    execution_time=final_timestamp,
                )
                cash += self._cash_settlement(trade)
                trades.append(trade)
                self.strategies[instrument].on_position_closed()
            equity[-1] = EquitySample(
                timestamp=final_timestamp,
                cash=cash,
                unrealized_pnl=0.0,
                equity=cash,
                open_position_count=0,
            )
        elif positions:
            warnings.append(
                ReplayWarning(
                    code="OPEN_POSITIONS_MARKED_AT_END",
                    message="Open positions remain marked to the final available candle.",
                    timestamp=final_timestamp,
                    details={"count": len(positions)},
                )
            )

        open_position_results = [
            self.execution.mark_open_position(
                position=positions[instrument],
                candle=latest_candles[instrument],
                mark_time=final_timestamp,
            )
            for instrument in sorted(positions)
        ]
        metrics = calculate_metrics(
            starting_capital=self.configuration.starting_capital,
            ending_cash=cash,
            trades=trades,
            equity=equity,
            open_positions=open_position_results,
            period_start=trading_start_at,
            period_end=final_timestamp,
            open_position_treatment=self.configuration.open_position_treatment,
        )
        grouped_metrics = calculate_grouped_metrics(
            starting_capital=self.configuration.starting_capital,
            trades=trades,
            open_positions=open_position_results,
            period_start=trading_start_at,
            period_end=final_timestamp,
            open_position_treatment=self.configuration.open_position_treatment,
        )
        for instrument in sorted(self.strategies):
            grouped_metrics.setdefault(
                instrument,
                calculate_metrics(
                    starting_capital=self.configuration.starting_capital,
                    ending_cash=self.configuration.starting_capital,
                    trades=[],
                    equity=[],
                    open_positions=[],
                    period_start=trading_start_at,
                    period_end=final_timestamp,
                    open_position_treatment=self.configuration.open_position_treatment,
                ),
            )
        return ReplayResult(
            trades=sorted(
                trades,
                key=lambda trade: (
                    trade.position.open_time,
                    trade.position.instrument,
                    trade.position.id,
                    trade.close_time,
                    trade.exit_reason,
                ),
            ),
            equity=sorted(equity, key=lambda sample: sample.timestamp),
            metrics=metrics,
            metrics_by_instrument=grouped_metrics,
            warnings=sorted(
                warnings,
                key=lambda warning: (
                    warning.timestamp or final_timestamp,
                    warning.instrument or "",
                    warning.code,
                    warning.message,
                ),
            ),
            open_positions=open_position_results,
            effective_start_at=timestamps[0],
            effective_end_at=final_timestamp,
            pricing_modes=tuple(sorted(pricing_modes)),
        )

    def _position_size(
        self,
        *,
        decision: StrategyDecision,
        candle: HistoricalCandle,
        equity: float,
    ) -> tuple[float, dict[str, object]]:
        mode = self.configuration.position_sizing_mode
        risk = self.configuration.risk_configuration
        if mode == "FIXED_UNITS":
            return float(risk.get("fixed_size", 1.0)), {}
        if mode != "PERCENT_RISK":
            raise ValueError(f"Unsupported position sizing mode '{mode}'.")
        if decision.direction is None:
            return 0.0, {}
        _, entry_fill, _, _, _ = self.execution.entry_projection(
            candle=candle,
            direction=decision.direction,
            size=1.0,
        )
        stop = _optional_float(decision.hints.get("stop_loss_price"))
        if stop is None:
            fallback_percent = float(risk.get("fallback_stop_percent", 0.5))
            stop_distance = entry_fill * fallback_percent / 100
            stop = (
                entry_fill - stop_distance
                if decision.direction is OrderDirection.BUY
                else entry_fill + stop_distance
            )
        if (
            stop <= 0
            or (decision.direction is OrderDirection.BUY and stop >= entry_fill)
            or (decision.direction is OrderDirection.SELL and stop <= entry_fill)
        ):
            return 0.0, {}
        risk_amount = equity * float(risk.get("risk_per_trade_percent", 0.5)) / 100
        max_size = risk.get("max_size")
        upper = (
            float(max_size)
            if max_size is not None
            else max(
                risk_amount / abs(entry_fill - stop),
                1.0,
            )
        )
        if max_size is None:
            while (
                self.execution.projected_stop_loss(
                    candle=candle,
                    direction=decision.direction,
                    stop_loss_price=stop,
                    size=upper,
                )
                <= risk_amount
                and upper < 1e18
            ):
                upper *= 2
        lower = 0.0
        for _ in range(80):
            candidate = (lower + upper) / 2
            projected_loss = self.execution.projected_stop_loss(
                candle=candle,
                direction=decision.direction,
                stop_loss_price=stop,
                size=candidate,
            )
            if projected_loss <= risk_amount:
                lower = candidate
            else:
                upper = candidate
        size = max(lower, 0.0)
        projected_loss = self.execution.projected_stop_loss(
            candle=candle,
            direction=decision.direction,
            stop_loss_price=stop,
            size=size,
        )
        return size, {
            "sizing_expected_entry_price": entry_fill,
            "sizing_stop_price": stop,
            "sizing_risk_budget": risk_amount,
            "sizing_projected_stop_loss": projected_loss,
            "sizing_absolute_tolerance": (PERCENT_RISK_SIZING_ABSOLUTE_TOLERANCE),
        }

    def _current_equity(
        self,
        *,
        cash: float,
        positions: dict[str, SimulatedPosition],
        latest_candles: dict[str, HistoricalCandle],
        open_timestamp: datetime | None = None,
    ) -> float:
        unrealized = 0.0
        for instrument, position in positions.items():
            candle = latest_candles.get(instrument)
            if candle is None:
                continue
            mark = self.execution.mark_price(
                position=position,
                candle=candle,
                at=(
                    "open"
                    if open_timestamp is not None and candle.timestamp == open_timestamp
                    else "close"
                ),
            )
            unrealized += (
                (mark - position.open_price) * position.size
                if position.direction is OrderDirection.BUY
                else (position.open_price - mark) * position.size
            )
        return cash + unrealized

    @staticmethod
    def _cash_settlement(trade: SimulatedTradeResult) -> float:
        exit_fee = trade.fees - trade.position.entry_fee
        return trade.gross_pnl - exit_fee

    @staticmethod
    def _price_update(candle: HistoricalCandle) -> PriceUpdate:
        reference = candle.mid or candle.trade
        if reference is not None:
            price = reference.close
            high = reference.high
            low = reference.low
        elif candle.bid is not None and candle.ask is not None:
            price = (candle.bid.close + candle.ask.close) / 2
            high = (candle.bid.high + candle.ask.high) / 2
            low = (candle.bid.low + candle.ask.low) / 2
        else:
            raise ValueError("Candle has no usable strategy price.")
        return PriceUpdate(
            instrument=candle.instrument,
            price=price,
            bid=candle.bid.close if candle.bid else None,
            ask=candle.ask.close if candle.ask else None,
            high=high,
            low=low,
            market_status="TRADEABLE",
            tradable=True,
            received_at=candle.close_timestamp,
        )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None
