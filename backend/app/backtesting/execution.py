from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from math import isfinite
from typing import Any

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.core.broker import OrderDirection


@dataclass(frozen=True, slots=True)
class ExecutionAssumptions:
    spread_model: str = "DATASET"
    spread_value: float = 0.0
    slippage_model: str = "NONE"
    slippage_value: float = 0.0
    fee_model: str = "NONE"
    fee_value: float = 0.0


@dataclass(slots=True)
class SimulatedPosition:
    id: int
    instrument: str
    direction: OrderDirection
    size: float
    open_time: datetime
    open_price: float
    entry_reference_price: float
    entry_fee: float
    entry_spread_cost: float
    entry_slippage_cost: float
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulatedTradeResult:
    position: SimulatedPosition
    close_time: datetime
    close_price: float
    gross_pnl: float
    fees: float
    spread_cost: float
    slippage_cost: float
    net_pnl: float
    exit_reason: str
    conservative_ambiguity: bool
    pricing_mode: str


@dataclass(frozen=True, slots=True)
class SimulatedOpenPositionResult:
    position: SimulatedPosition
    mark_time: datetime
    mark_price: float
    unrealized_pnl: float
    open_position_value: float
    pricing_mode: str


class SimulatedExecutionAdapter:
    def __init__(self, assumptions: ExecutionAssumptions) -> None:
        self._validate_assumptions(assumptions)
        self.assumptions = assumptions
        self._position_ids = count(1)

    def open_position(
        self,
        *,
        instrument: str,
        direction: OrderDirection,
        size: float,
        candle: HistoricalCandle,
        stop_loss_price: float | None,
        take_profit_price: float | None,
        metadata: dict[str, Any] | None = None,
    ) -> SimulatedPosition:
        reference, fill, fee, spread_cost, slippage_cost = self.entry_projection(
            candle=candle,
            direction=direction,
            size=size,
        )
        return SimulatedPosition(
            id=next(self._position_ids),
            instrument=instrument,
            direction=direction,
            size=size,
            open_time=candle.timestamp,
            open_price=fill,
            entry_reference_price=reference,
            entry_fee=fee,
            entry_spread_cost=spread_cost,
            entry_slippage_cost=slippage_cost,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            metadata=dict(metadata or {}),
        )

    def entry_projection(
        self,
        *,
        candle: HistoricalCandle,
        direction: OrderDirection,
        size: float,
    ) -> tuple[float, float, float, float, float]:
        reference = self._reference_price(candle, at="open")
        executable, spread_per_unit = self._execution_price(
            candle=candle,
            direction=direction,
            at="open",
        )
        fill, slippage_cost = self._apply_slippage(
            executable, direction=direction, size=size
        )
        return (
            reference,
            fill,
            self._fee(fill, size),
            spread_per_unit * size,
            slippage_cost,
        )

    def projected_stop_loss(
        self,
        *,
        candle: HistoricalCandle,
        direction: OrderDirection,
        stop_loss_price: float,
        size: float,
    ) -> float:
        if size <= 0:
            return 0.0
        _, entry_fill, entry_fee, _, _ = self.entry_projection(
            candle=candle,
            direction=direction,
            size=size,
        )
        close_direction = (
            OrderDirection.SELL
            if direction is OrderDirection.BUY
            else OrderDirection.BUY
        )
        stop_fill, _ = self._apply_slippage(
            stop_loss_price,
            direction=close_direction,
            size=size,
        )
        exit_fee = self._fee(stop_fill, size)
        price_loss = (
            (entry_fill - stop_fill) * size
            if direction is OrderDirection.BUY
            else (stop_fill - entry_fill) * size
        )
        return max(price_loss, 0.0) + entry_fee + exit_fee

    def close_position(
        self,
        *,
        position: SimulatedPosition,
        candle: HistoricalCandle,
        exit_reason: str,
        trigger_price: float | None = None,
        conservative_ambiguity: bool = False,
        at: str = "open",
        execution_time: datetime | None = None,
    ) -> SimulatedTradeResult:
        close_direction = (
            OrderDirection.SELL
            if position.direction is OrderDirection.BUY
            else OrderDirection.BUY
        )
        if trigger_price is None:
            executable, spread_per_unit = self._execution_price(
                candle=candle,
                direction=close_direction,
                at=at,
            )
        else:
            executable = trigger_price
            spread_per_unit = self._estimated_half_spread(
                candle=candle,
                reference_price=trigger_price,
                at=at,
            )
        fill, exit_slippage_cost = self._apply_slippage(
            executable, direction=close_direction, size=position.size
        )
        exit_fee = self._fee(fill, position.size)
        gross_pnl = (
            (fill - position.open_price) * position.size
            if position.direction is OrderDirection.BUY
            else (position.open_price - fill) * position.size
        )
        fees = position.entry_fee + exit_fee
        spread_cost = position.entry_spread_cost + spread_per_unit * position.size
        slippage_cost = position.entry_slippage_cost + exit_slippage_cost
        return SimulatedTradeResult(
            position=position,
            close_time=execution_time
            or (candle.close_timestamp if at == "close" else candle.timestamp),
            close_price=fill,
            gross_pnl=gross_pnl,
            fees=fees,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            net_pnl=gross_pnl - fees,
            exit_reason=exit_reason,
            conservative_ambiguity=conservative_ambiguity,
            pricing_mode=self.pricing_mode(candle),
        )

    def threshold_exit(
        self,
        *,
        position: SimulatedPosition,
        candle: HistoricalCandle,
    ) -> SimulatedTradeResult | None:
        bar = self._exit_bar(candle, position.direction)
        stop = position.stop_loss_price
        target = position.take_profit_price
        if position.direction is OrderDirection.BUY:
            stop_hit = stop is not None and bar.low <= stop
            target_hit = target is not None and bar.high >= target
        else:
            stop_hit = stop is not None and bar.high >= stop
            target_hit = target is not None and bar.low <= target
        if not stop_hit and not target_hit:
            return None
        ambiguous = stop_hit and target_hit
        if stop_hit:
            assert stop is not None
            trigger = stop
            if position.direction is OrderDirection.BUY and bar.open <= stop:
                trigger = bar.open
            elif position.direction is OrderDirection.SELL and bar.open >= stop:
                trigger = bar.open
            return self.close_position(
                position=position,
                candle=candle,
                exit_reason=(
                    "STOP_LOSS_CONSERVATIVE_INTRACANDLE" if ambiguous else "STOP_LOSS"
                ),
                trigger_price=trigger,
                conservative_ambiguity=ambiguous,
                execution_time=candle.close_timestamp,
            )
        assert target is not None
        return self.close_position(
            position=position,
            candle=candle,
            exit_reason="TAKE_PROFIT",
            trigger_price=target,
            execution_time=candle.close_timestamp,
        )

    def mark_price(
        self,
        *,
        position: SimulatedPosition,
        candle: HistoricalCandle,
        at: str = "close",
    ) -> float:
        bar = self._exit_bar(candle, position.direction)
        return getattr(bar, at)

    def mark_open_position(
        self,
        *,
        position: SimulatedPosition,
        candle: HistoricalCandle,
        mark_time: datetime,
    ) -> SimulatedOpenPositionResult:
        mark = self.mark_price(position=position, candle=candle)
        unrealized = (
            (mark - position.open_price) * position.size
            if position.direction is OrderDirection.BUY
            else (position.open_price - mark) * position.size
        )
        return SimulatedOpenPositionResult(
            position=position,
            mark_time=mark_time,
            mark_price=mark,
            unrealized_pnl=unrealized,
            open_position_value=abs(mark * position.size),
            pricing_mode=self.pricing_mode(candle),
        )

    def pricing_mode(self, candle: HistoricalCandle) -> str:
        if candle.bid is not None and candle.ask is not None:
            return "HISTORICAL_BID_ASK"
        if candle.mid is not None:
            return "MID_WITH_SYNTHETIC_SPREAD"
        return "TRADE_WITH_SYNTHETIC_SPREAD"

    def _execution_price(
        self,
        *,
        candle: HistoricalCandle,
        direction: OrderDirection,
        at: str,
    ) -> tuple[float, float]:
        if candle.bid is not None and candle.ask is not None:
            reference = self._reference_price(candle, at=at)
            price = (
                getattr(candle.ask, at)
                if direction is OrderDirection.BUY
                else getattr(candle.bid, at)
            )
            return price, abs(price - reference)
        if self.assumptions.spread_model == "DATASET":
            raise ValueError(
                "Dataset lacks bid/ask candles; an explicit synthetic spread is required."
            )
        reference = self._reference_price(candle, at=at)
        half_spread = self._spread_amount(reference) / 2
        price = (
            reference + half_spread
            if direction is OrderDirection.BUY
            else reference - half_spread
        )
        return price, half_spread

    def _exit_bar(
        self, candle: HistoricalCandle, direction: OrderDirection
    ) -> PriceBar:
        if candle.bid is not None and candle.ask is not None:
            return candle.bid if direction is OrderDirection.BUY else candle.ask
        source = candle.mid or candle.trade
        if source is None:
            raise ValueError("Candle has no usable price component.")
        if self.assumptions.spread_model == "DATASET":
            raise ValueError(
                "Dataset lacks bid/ask candles; an explicit synthetic spread is required."
            )
        half_spread = self._spread_amount(source.close) / 2
        adjustment = -half_spread if direction is OrderDirection.BUY else half_spread
        return PriceBar(
            open=source.open + adjustment,
            high=source.high + adjustment,
            low=source.low + adjustment,
            close=source.close + adjustment,
        )

    @staticmethod
    def _reference_price(candle: HistoricalCandle, *, at: str) -> float:
        if candle.mid is not None:
            return getattr(candle.mid, at)
        if candle.trade is not None:
            return getattr(candle.trade, at)
        if candle.bid is not None and candle.ask is not None:
            return (getattr(candle.bid, at) + getattr(candle.ask, at)) / 2
        raise ValueError("Candle has no usable reference price.")

    def _spread_amount(self, reference_price: float) -> float:
        model = self.assumptions.spread_model
        value = self.assumptions.spread_value
        if model == "FIXED_PRICE":
            return value
        if model == "FIXED_BPS":
            return reference_price * value / 10_000
        if model == "NONE":
            return 0.0
        raise ValueError(f"Unsupported spread model '{model}'.")

    def _estimated_half_spread(
        self,
        *,
        candle: HistoricalCandle,
        reference_price: float,
        at: str,
    ) -> float:
        if candle.bid is not None and candle.ask is not None:
            return abs(getattr(candle.ask, at) - getattr(candle.bid, at)) / 2
        return self._spread_amount(reference_price) / 2

    def _apply_slippage(
        self,
        price: float,
        *,
        direction: OrderDirection,
        size: float,
    ) -> tuple[float, float]:
        model = self.assumptions.slippage_model
        value = self.assumptions.slippage_value
        if model == "NONE":
            amount = 0.0
        elif model == "FIXED_PRICE":
            amount = value
        elif model == "FIXED_BPS":
            amount = price * value / 10_000
        else:
            raise ValueError(f"Unsupported slippage model '{model}'.")
        fill = price + amount if direction is OrderDirection.BUY else price - amount
        return fill, amount * size

    def _fee(self, price: float, size: float) -> float:
        model = self.assumptions.fee_model
        value = self.assumptions.fee_value
        if model == "NONE":
            return 0.0
        if model == "FIXED_PER_ORDER":
            return value
        if model == "PER_UNIT":
            return value * size
        if model == "BPS_NOTIONAL":
            return price * size * value / 10_000
        raise ValueError(f"Unsupported fee model '{model}'.")

    @staticmethod
    def _validate_assumptions(assumptions: ExecutionAssumptions) -> None:
        allowed = {
            "spread_model": {"DATASET", "FIXED_PRICE", "FIXED_BPS", "NONE"},
            "slippage_model": {"NONE", "FIXED_PRICE", "FIXED_BPS"},
            "fee_model": {"NONE", "FIXED_PER_ORDER", "PER_UNIT", "BPS_NOTIONAL"},
        }
        for field_name, options in allowed.items():
            value = getattr(assumptions, field_name)
            if value not in options:
                raise ValueError(f"Unsupported {field_name} '{value}'.")
        for field_name in ("spread_value", "slippage_value", "fee_value"):
            value = getattr(assumptions, field_name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative.")
