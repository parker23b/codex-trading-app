from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


@dataclass(slots=True)
class Candle:
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float


class VolatilityAdjustedPullbackContinuationStrategy(Strategy):
    """
    Forex pullback-continuation strategy adapted for the app runtime.

    The original hypothesis was a EUR/USD overlap scalper. This implementation
    keeps the multi-timeframe trend/pullback/spread discipline, but removes the
    EUR/USD and session-window constraints so the runtime can evaluate any
    governed forex instrument throughout the day. The platform risk and
    allocation services remain authoritative for sizing and admission.
    """

    name = "volatility_adjusted_pullback_continuation"

    def __init__(
        self,
        *,
        regime_fast_window: int = 20,
        regime_slow_window: int = 50,
        regime_slope_window: int = 3,
        trigger_ema_window: int = 20,
        setup_ema_window: int = 50,
        atr_window: int = 14,
        volatility_window: int = 240,
        atr_min_percentile: float = 30.0,
        atr_max_percentile: float = 85.0,
        pullback_swing_window: int = 5,
        stop_buffer_pips: float = 0.5,
        min_stop_pips: float = 3.0,
        max_stop_pips: float = 8.0,
        max_spread_pips: float = 1.0,
        max_spread_stop_fraction: float = 0.20,
        take_profit_r_multiple: float = 1.25,
        breakeven_r_multiple: float = 0.8,
        time_stop_minutes: float = 20.0,
        tick_size: float | None = None,
        pip_size: float | None = None,
    ) -> None:
        if regime_fast_window >= regime_slow_window:
            raise ValueError(
                "regime_fast_window must be smaller than regime_slow_window"
            )
        if regime_slope_window < 1:
            raise ValueError("regime_slope_window must be at least 1")
        if trigger_ema_window < 2 or setup_ema_window < 2:
            raise ValueError("EMA windows must be at least 2")
        if atr_window < 2 or volatility_window < 2:
            raise ValueError("ATR windows must be at least 2")
        if not 0 <= atr_min_percentile <= atr_max_percentile <= 100:
            raise ValueError("ATR percentiles must be ordered between 0 and 100")
        if min_stop_pips <= 0 or max_stop_pips < min_stop_pips:
            raise ValueError("stop limits must be positive and ordered")
        if take_profit_r_multiple <= 0 or breakeven_r_multiple <= 0:
            raise ValueError("R multiples must be positive")

        self.regime_fast_window = regime_fast_window
        self.regime_slow_window = regime_slow_window
        self.regime_slope_window = regime_slope_window
        self.trigger_ema_window = trigger_ema_window
        self.setup_ema_window = setup_ema_window
        self.atr_window = atr_window
        self.volatility_window = volatility_window
        self.atr_min_percentile = atr_min_percentile
        self.atr_max_percentile = atr_max_percentile
        self.pullback_swing_window = pullback_swing_window
        self.stop_buffer_pips = stop_buffer_pips
        self.min_stop_pips = min_stop_pips
        self.max_stop_pips = max_stop_pips
        self.max_spread_pips = max_spread_pips
        self.max_spread_stop_fraction = max_spread_stop_fraction
        self.take_profit_r_multiple = take_profit_r_multiple
        self.breakeven_r_multiple = breakeven_r_multiple
        self.time_stop_minutes = time_stop_minutes
        self.configured_tick_size = tick_size
        self.configured_pip_size = pip_size

        self.minute_candles: deque[Candle] = deque(maxlen=5000)
        self.active_minute: Candle | None = None

        self.last_instrument: str | None = None
        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self.last_price: float | None = None
        self.last_market_status: str | None = None
        self.last_tradable: bool | None = None
        self.last_received_at: datetime | None = None

        self._pending_direction: OrderDirection | None = None
        self._pending_trigger_price: float | None = None
        self._pending_swing_price: float | None = None
        self._pending_confirmation_high: float | None = None
        self._pending_confirmation_low: float | None = None

        self._entry_direction: OrderDirection | None = None
        self._entry_price: float | None = None
        self._entry_time: datetime | None = None
        self._stop_loss: float | None = None
        self._take_profit: float | None = None
        self._risk_per_unit: float | None = None
        self._signal_stop_loss: float | None = None
        self._signal_take_profit: float | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        timestamp = (data.received_at or self.current_time()).astimezone(UTC)
        high = data.high if data.high is not None else data.price
        low = data.low if data.low is not None else data.price

        self.last_instrument = data.instrument
        self.last_price = data.price
        self.last_bid = data.bid
        self.last_ask = data.ask
        self.last_market_status = data.market_status
        self.last_tradable = data.tradable
        self.last_received_at = timestamp

        opened_at = timestamp.replace(second=0, microsecond=0)
        if self.active_minute is None:
            self.active_minute = Candle(
                opened_at=opened_at,
                open=data.price,
                high=high,
                low=low,
                close=data.price,
            )
            return

        if opened_at > self.active_minute.opened_at:
            self.minute_candles.append(self.active_minute)
            self.active_minute = Candle(
                opened_at=opened_at,
                open=data.price,
                high=high,
                low=low,
                close=data.price,
            )
            return

        self.active_minute.high = max(self.active_minute.high, high)
        self.active_minute.low = min(self.active_minute.low, low)
        self.active_minute.close = data.price

    def should_enter_trade(self) -> bool:
        self._signal_stop_loss = None
        self._signal_take_profit = None
        if self._entry_direction is not None and self._entry_price is not None:
            return False
        if self._entry_direction is not None:
            self._entry_direction = None
        if not self._market_allows_entry():
            self._clear_pending_entry()
            return False
        if not self._has_enough_data():
            return False

        bars_1m = list(self.minute_candles)
        bars_5m = self._aggregate_bars(5)
        bars_15m = self._aggregate_bars(15)
        if not bars_1m or not bars_5m or not bars_15m:
            return False

        long_regime = self._regime_passes(OrderDirection.BUY, bars_15m)
        short_regime = self._regime_passes(OrderDirection.SELL, bars_15m)
        if not long_regime and not short_regime:
            self._clear_pending_entry()
            return False
        if not self._volatility_passes(bars_5m):
            self._clear_pending_entry()
            return False

        latest_1m = bars_1m[-1]
        trigger_ema = self._ema([bar.close for bar in bars_1m], self.trigger_ema_window)
        setup_ema = self._ema([bar.close for bar in bars_5m], self.setup_ema_window)
        if trigger_ema is None or setup_ema is None:
            return False

        if self._pending_direction is None:
            if (
                long_regime
                and latest_1m.low <= trigger_ema
                and latest_1m.close >= setup_ema
            ):
                self._arm_entry(OrderDirection.BUY, latest_1m, bars_1m)
            elif (
                short_regime
                and latest_1m.high >= trigger_ema
                and latest_1m.close <= setup_ema
            ):
                self._arm_entry(OrderDirection.SELL, latest_1m, bars_1m)
            return False

        if self._pending_direction is OrderDirection.BUY and not long_regime:
            self._clear_pending_entry()
            return False
        if self._pending_direction is OrderDirection.SELL and not short_regime:
            self._clear_pending_entry()
            return False

        if not self._confirmation_still_valid(latest_1m, trigger_ema, setup_ema):
            return False

        if not self._pending_trigger_traded():
            return False

        return self._prepare_signal_prices()

    def should_exit_trade(self) -> bool:
        if self._entry_direction is None or self._entry_price is None:
            return False
        exit_price = self._current_exit_price()
        if exit_price is None:
            return False

        self._move_stop_to_breakeven(exit_price)

        if self._stop_loss is not None:
            if (
                self._entry_direction is OrderDirection.BUY
                and exit_price <= self._stop_loss
            ):
                return True
            if (
                self._entry_direction is OrderDirection.SELL
                and exit_price >= self._stop_loss
            ):
                return True

        if self._take_profit is not None:
            if (
                self._entry_direction is OrderDirection.BUY
                and exit_price >= self._take_profit
            ):
                return True
            if (
                self._entry_direction is OrderDirection.SELL
                and exit_price <= self._take_profit
            ):
                return True

        if self._entry_time is not None and self.last_received_at is not None:
            held_for = self.last_received_at - self._entry_time
            if held_for >= timedelta(minutes=self.time_stop_minutes):
                return True

        return False

    def entry_direction(self) -> OrderDirection:
        if self._entry_direction is None:
            raise ValueError(
                "No entry direction available. Evaluate entry signal first."
            )
        return self._entry_direction

    def on_position_opened(
        self, *, direction: OrderDirection, entry_price: float
    ) -> None:
        self._entry_direction = direction
        self._entry_price = entry_price
        self._entry_time = self.last_received_at or self.current_time()
        if self._signal_stop_loss is not None:
            self._stop_loss = self._signal_stop_loss
        elif direction is OrderDirection.BUY:
            self._stop_loss = entry_price - self._pip_size() * self.min_stop_pips
        else:
            self._stop_loss = entry_price + self._pip_size() * self.min_stop_pips

        self._risk_per_unit = abs(entry_price - self._stop_loss)
        if direction is OrderDirection.BUY:
            self._take_profit = entry_price + (
                self._risk_per_unit * self.take_profit_r_multiple
            )
        else:
            self._take_profit = entry_price - (
                self._risk_per_unit * self.take_profit_r_multiple
            )
        self._clear_pending_entry()

    def on_position_closed(self) -> None:
        self._entry_direction = None
        self._entry_price = None
        self._entry_time = None
        self._stop_loss = None
        self._take_profit = None
        self._risk_per_unit = None
        self._signal_stop_loss = None
        self._signal_take_profit = None
        self._clear_pending_entry()

    def on_entry_failed(self) -> None:
        self._clear_pending_entry()
        self._entry_direction = None
        self._entry_price = None
        self._entry_time = None
        self._signal_stop_loss = None
        self._signal_take_profit = None

    def entry_signal_hints(self) -> dict[str, Any]:
        if self._entry_direction is None:
            return {}
        hints: dict[str, Any] = {
            "expected_reward_risk": round(self.take_profit_r_multiple, 4),
            "thesis": (
                "all_day_forex_pullback_continuation_long"
                if self._entry_direction is OrderDirection.BUY
                else "all_day_forex_pullback_continuation_short"
            ),
            "max_hold_minutes": self.time_stop_minutes,
            "breakeven_r_multiple": self.breakeven_r_multiple,
        }
        if self._signal_stop_loss is not None:
            hints["stop_loss_price"] = round(self._signal_stop_loss, 8)
        if self._signal_take_profit is not None:
            hints["take_profit_price"] = round(self._signal_take_profit, 8)
        current_atr = self._current_atr(self._aggregate_bars(5))
        hints["volatility_estimate"] = (
            round(current_atr, 8) if current_atr is not None else None
        )
        return hints

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "minute_candles": [
                self._candle_to_dict(bar) for bar in self.minute_candles
            ],
            "active_minute": self._candle_to_dict(self.active_minute)
            if self.active_minute
            else None,
            "last_instrument": self.last_instrument,
            "last_bid": self.last_bid,
            "last_ask": self.last_ask,
            "last_price": self.last_price,
            "last_market_status": self.last_market_status,
            "last_tradable": self.last_tradable,
            "last_received_at": self.last_received_at.isoformat()
            if self.last_received_at
            else None,
            "pending_direction": self._pending_direction.value
            if self._pending_direction
            else None,
            "pending_trigger_price": self._pending_trigger_price,
            "pending_swing_price": self._pending_swing_price,
            "pending_confirmation_high": self._pending_confirmation_high,
            "pending_confirmation_low": self._pending_confirmation_low,
            "entry_direction": self._entry_direction.value
            if self._entry_direction
            else None,
            "entry_price": self._entry_price,
            "entry_time": self._entry_time.isoformat() if self._entry_time else None,
            "stop_loss": self._stop_loss,
            "take_profit": self._take_profit,
            "risk_per_unit": self._risk_per_unit,
            "signal_stop_loss": self._signal_stop_loss,
            "signal_take_profit": self._signal_take_profit,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.minute_candles = deque(
            (
                self._candle_from_dict(raw)
                for raw in snapshot.get("minute_candles") or []
            ),
            maxlen=5000,
        )
        active_minute = snapshot.get("active_minute")
        self.active_minute = (
            self._candle_from_dict(active_minute) if active_minute else None
        )
        self.last_instrument = snapshot.get("last_instrument")
        self.last_bid = snapshot.get("last_bid")
        self.last_ask = snapshot.get("last_ask")
        self.last_price = snapshot.get("last_price")
        self.last_market_status = snapshot.get("last_market_status")
        self.last_tradable = snapshot.get("last_tradable")
        self.last_received_at = self._parse_timestamp(snapshot.get("last_received_at"))
        pending_direction = snapshot.get("pending_direction")
        self._pending_direction = (
            OrderDirection(pending_direction) if pending_direction else None
        )
        self._pending_trigger_price = snapshot.get("pending_trigger_price")
        self._pending_swing_price = snapshot.get("pending_swing_price")
        self._pending_confirmation_high = snapshot.get("pending_confirmation_high")
        self._pending_confirmation_low = snapshot.get("pending_confirmation_low")
        entry_direction = snapshot.get("entry_direction")
        self._entry_direction = (
            OrderDirection(entry_direction) if entry_direction else None
        )
        self._entry_price = snapshot.get("entry_price")
        self._entry_time = self._parse_timestamp(snapshot.get("entry_time"))
        self._stop_loss = snapshot.get("stop_loss")
        self._take_profit = snapshot.get("take_profit")
        self._risk_per_unit = snapshot.get("risk_per_unit")
        self._signal_stop_loss = snapshot.get("signal_stop_loss")
        self._signal_take_profit = snapshot.get("signal_take_profit")

    def _has_enough_data(self) -> bool:
        return (
            len(self.minute_candles) >= self.trigger_ema_window
            and len(self._aggregate_bars(5))
            >= max(self.setup_ema_window, self.atr_window + self.volatility_window)
            and len(self._aggregate_bars(15))
            >= self.regime_slow_window + self.regime_slope_window
        )

    def _market_allows_entry(self) -> bool:
        if self.last_tradable is False:
            return False
        if self.last_market_status not in {None, "TRADEABLE"}:
            return False
        return True

    def _regime_passes(self, direction: OrderDirection, bars_15m: list[Candle]) -> bool:
        closes = [bar.close for bar in bars_15m]
        fast = self._ema(closes, self.regime_fast_window)
        slow = self._ema(closes, self.regime_slow_window)
        previous_fast_values = [
            self._ema(closes[:-offset], self.regime_fast_window)
            for offset in range(self.regime_slope_window, 0, -1)
        ]
        if (
            fast is None
            or slow is None
            or any(value is None for value in previous_fast_values)
        ):
            return False
        latest_close = closes[-1]
        if direction is OrderDirection.BUY:
            return (
                fast > slow
                and fast > float(previous_fast_values[0])
                and all(
                    float(left) < float(right)
                    for left, right in zip(
                        previous_fast_values, previous_fast_values[1:] + [fast]
                    )
                )
                and latest_close > fast
            )
        return (
            fast < slow
            and fast < float(previous_fast_values[0])
            and all(
                float(left) > float(right)
                for left, right in zip(
                    previous_fast_values, previous_fast_values[1:] + [fast]
                )
            )
            and latest_close < fast
        )

    def _volatility_passes(self, bars_5m: list[Candle]) -> bool:
        atr_values = self._atr_series(bars_5m)
        if len(atr_values) < self.volatility_window + 1:
            return False
        current_atr = atr_values[-1]
        history = atr_values[-(self.volatility_window + 1) : -1]
        percentile = self._percentile_rank(current_atr, history)
        return self.atr_min_percentile <= percentile <= self.atr_max_percentile

    def _arm_entry(
        self, direction: OrderDirection, candle: Candle, bars_1m: list[Candle]
    ) -> None:
        recent_bars = bars_1m[-self.pullback_swing_window :]
        tick = self._tick_size()
        self._pending_direction = direction
        if direction is OrderDirection.BUY:
            self._pending_confirmation_high = candle.high
            self._pending_confirmation_low = None
            self._pending_trigger_price = candle.high + tick
            self._pending_swing_price = min(bar.low for bar in recent_bars)
        else:
            self._pending_confirmation_high = None
            self._pending_confirmation_low = candle.low
            self._pending_trigger_price = candle.low - tick
            self._pending_swing_price = max(bar.high for bar in recent_bars)

    def _confirmation_still_valid(
        self, latest_1m: Candle, trigger_ema: float, setup_ema: float
    ) -> bool:
        if self._pending_direction is OrderDirection.BUY:
            if latest_1m.close < setup_ema:
                self._clear_pending_entry()
                return False
            if latest_1m.close > trigger_ema:
                return True
            return False
        if self._pending_direction is OrderDirection.SELL:
            if latest_1m.close > setup_ema:
                self._clear_pending_entry()
                return False
            if latest_1m.close < trigger_ema:
                return True
            return False
        return False

    def _pending_trigger_traded(self) -> bool:
        if (
            self._pending_direction is None
            or self._pending_trigger_price is None
            or self.last_price is None
        ):
            return False
        if self._pending_direction is OrderDirection.BUY:
            return self.last_price >= self._pending_trigger_price
        return self.last_price <= self._pending_trigger_price

    def _prepare_signal_prices(self) -> bool:
        if (
            self._pending_direction is None
            or self._pending_swing_price is None
            or self.last_price is None
        ):
            return False
        pip = self._pip_size()
        buffer = self.stop_buffer_pips * pip
        min_stop = self.min_stop_pips * pip
        max_stop = self.max_stop_pips * pip
        entry_price = self._current_entry_price(self._pending_direction)

        if self._pending_direction is OrderDirection.BUY:
            raw_stop_loss = self._pending_swing_price - buffer
            raw_stop_distance = entry_price - raw_stop_loss
            if raw_stop_distance <= 0 or raw_stop_distance > max_stop:
                self._clear_pending_entry()
                return False
            stop_distance = max(raw_stop_distance, min_stop)
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + (stop_distance * self.take_profit_r_multiple)
        else:
            raw_stop_loss = self._pending_swing_price + buffer
            raw_stop_distance = raw_stop_loss - entry_price
            if raw_stop_distance <= 0 or raw_stop_distance > max_stop:
                self._clear_pending_entry()
                return False
            stop_distance = max(raw_stop_distance, min_stop)
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - (stop_distance * self.take_profit_r_multiple)

        if self._spread_too_wide(stop_distance):
            self._clear_pending_entry()
            return False

        self._entry_direction = self._pending_direction
        self._signal_stop_loss = stop_loss
        self._signal_take_profit = take_profit
        return True

    def _spread_too_wide(self, stop_distance: float) -> bool:
        if self.last_bid is None or self.last_ask is None:
            return False
        spread = self.last_ask - self.last_bid
        return spread > self.max_spread_pips * self._pip_size() or spread > (
            stop_distance * self.max_spread_stop_fraction
        )

    def _current_entry_price(self, direction: OrderDirection) -> float:
        if direction is OrderDirection.BUY and self.last_ask is not None:
            return self.last_ask
        if direction is OrderDirection.SELL and self.last_bid is not None:
            return self.last_bid
        if self.last_price is None:
            raise ValueError("Last price is not set.")
        return self.last_price

    def _current_exit_price(self) -> float | None:
        if self._entry_direction is OrderDirection.BUY:
            return self.last_bid if self.last_bid is not None else self.last_price
        if self._entry_direction is OrderDirection.SELL:
            return self.last_ask if self.last_ask is not None else self.last_price
        return self.last_price

    def _move_stop_to_breakeven(self, exit_price: float) -> None:
        if (
            self._entry_direction is None
            or self._entry_price is None
            or self._risk_per_unit is None
        ):
            return
        if self._entry_direction is OrderDirection.BUY:
            move_in_r = (exit_price - self._entry_price) / self._risk_per_unit
            if move_in_r >= self.breakeven_r_multiple:
                self._stop_loss = max(
                    self._stop_loss or self._entry_price, self._entry_price
                )
            return
        move_in_r = (self._entry_price - exit_price) / self._risk_per_unit
        if move_in_r >= self.breakeven_r_multiple:
            self._stop_loss = min(
                self._stop_loss or self._entry_price, self._entry_price
            )

    def _aggregate_bars(self, minutes: int) -> list[Candle]:
        grouped: dict[datetime, list[Candle]] = {}
        for candle in self.minute_candles:
            bucket_minute = (candle.opened_at.minute // minutes) * minutes
            bucket = candle.opened_at.replace(
                minute=bucket_minute, second=0, microsecond=0
            )
            grouped.setdefault(bucket, []).append(candle)
        bars: list[Candle] = []
        for bucket, candles in sorted(grouped.items()):
            if len(candles) < minutes:
                continue
            bars.append(
                Candle(
                    opened_at=bucket,
                    open=candles[0].open,
                    high=max(candle.high for candle in candles),
                    low=min(candle.low for candle in candles),
                    close=candles[-1].close,
                )
            )
        return bars

    @staticmethod
    def _ema(values: list[float], window: int) -> float | None:
        if len(values) < window:
            return None
        multiplier = 2 / (window + 1)
        ema = values[-window]
        for value in values[-window + 1 :]:
            ema = ((value - ema) * multiplier) + ema
        return ema

    def _atr_series(self, bars: list[Candle]) -> list[float]:
        if len(bars) <= self.atr_window:
            return []
        true_ranges = [
            max(
                bar.high - bar.low,
                abs(bar.high - bars[index - 1].close),
                abs(bar.low - bars[index - 1].close),
            )
            for index, bar in enumerate(bars[1:], start=1)
        ]
        if len(true_ranges) < self.atr_window:
            return []
        return [
            fmean(true_ranges[start : start + self.atr_window])
            for start in range(0, len(true_ranges) - self.atr_window + 1)
        ]

    def _current_atr(self, bars: list[Candle]) -> float | None:
        values = self._atr_series(bars)
        return values[-1] if values else None

    @staticmethod
    def _percentile_rank(value: float, history: list[float]) -> float:
        if not history:
            return 0.0
        below = len([item for item in history if item < value])
        equal = len([item for item in history if item == value])
        return ((below + (0.5 * equal)) / len(history)) * 100.0

    def _pip_size(self) -> float:
        if self.configured_pip_size is not None:
            return self.configured_pip_size
        instrument = (self.last_instrument or "").upper()
        return 0.01 if "JPY" in instrument else 0.0001

    def _tick_size(self) -> float:
        if self.configured_tick_size is not None:
            return self.configured_tick_size
        return self._pip_size() / 10

    def _clear_pending_entry(self) -> None:
        self._pending_direction = None
        self._pending_trigger_price = None
        self._pending_swing_price = None
        self._pending_confirmation_high = None
        self._pending_confirmation_low = None

    @staticmethod
    def _candle_to_dict(candle: Candle | None) -> dict[str, object] | None:
        if candle is None:
            return None
        return {
            "opened_at": candle.opened_at.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
        }

    @classmethod
    def _candle_from_dict(cls, raw: dict[str, object]) -> Candle:
        return Candle(
            opened_at=cls._parse_timestamp(raw.get("opened_at"))
            or datetime.fromtimestamp(0, tz=UTC),
            open=float(raw["open"]),
            high=float(raw["high"]),
            low=float(raw["low"]),
            close=float(raw["close"]),
        )

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
