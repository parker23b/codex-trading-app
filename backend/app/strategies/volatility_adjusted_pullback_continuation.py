from __future__ import annotations

from collections import deque
from statistics import fmean
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class VolatilityAdjustedPullbackContinuationStrategy(Strategy):
    """
    FX continuation strategy that waits for a pullback inside a higher-timeframe
    trend, then enters when momentum re-accelerates with supportive volatility.
    """

    name = "volatility_adjusted_pullback_continuation"

    def __init__(
        self,
        *,
        htf_fast_window: int = 20,
        htf_slow_window: int = 50,
        slope_window: int = 5,
        slope_threshold: float = 0.0,
        pullback_window: int = 20,
        local_structure_window: int = 5,
        atr_window: int = 14,
        volatility_window: int = 50,
        pullback_threshold: float = 0.0015,
        stop_atr_multiple: float = 0.5,
        trailing_atr_multiple: float = 0.75,
        risk_reward_multiple: float = 2.0,
        breakeven_r_multiple: float = 1.0,
        max_spread_threshold: float = 0.00012,
    ) -> None:
        if htf_fast_window >= htf_slow_window:
            raise ValueError("htf_fast_window must be smaller than htf_slow_window")
        if slope_window < 1 or pullback_window < 2 or local_structure_window < 2:
            raise ValueError("window sizes must be at least 1 or 2 as appropriate")
        if atr_window < 2 or volatility_window < 2:
            raise ValueError("atr_window and volatility_window must be at least 2")

        self.htf_fast_window = htf_fast_window
        self.htf_slow_window = htf_slow_window
        self.slope_window = slope_window
        self.slope_threshold = slope_threshold
        self.pullback_window = pullback_window
        self.local_structure_window = local_structure_window
        self.atr_window = atr_window
        self.volatility_window = volatility_window
        self.pullback_threshold = pullback_threshold
        self.stop_atr_multiple = stop_atr_multiple
        self.trailing_atr_multiple = trailing_atr_multiple
        self.risk_reward_multiple = risk_reward_multiple
        self.breakeven_r_multiple = breakeven_r_multiple
        self.max_spread_threshold = max_spread_threshold

        max_window = max(
            htf_slow_window + slope_window + 5,
            pullback_window + local_structure_window + 5,
            atr_window + volatility_window + 5,
        )
        self.prices: deque[float] = deque(maxlen=max_window)
        self.highs: deque[float] = deque(maxlen=max_window)
        self.lows: deque[float] = deque(maxlen=max_window)

        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self.last_price: float | None = None
        self.last_market_status: str | None = None
        self.last_tradable: bool | None = None

        self._entry_direction: OrderDirection | None = None
        self._entry_price: float | None = None
        self._stop_loss: float | None = None
        self._take_profit: float | None = None
        self._risk_per_unit: float | None = None
        self._highest_price_since_entry: float | None = None
        self._lowest_price_since_entry: float | None = None
        self._signal_stop_loss: float | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        high = data.high if data.high is not None else data.price
        low = data.low if data.low is not None else data.price

        self.last_price = data.price
        self.last_bid = data.bid
        self.last_ask = data.ask
        self.last_market_status = data.market_status
        self.last_tradable = data.tradable

        self.prices.append(data.price)
        self.highs.append(high)
        self.lows.append(low)

        if self._entry_price is None:
            return

        if self._entry_direction is OrderDirection.BUY:
            self._highest_price_since_entry = max(
                self._highest_price_since_entry or data.price, high
            )
        elif self._entry_direction is OrderDirection.SELL:
            self._lowest_price_since_entry = min(
                self._lowest_price_since_entry or data.price, low
            )

    def should_enter_trade(self) -> bool:
        self._signal_stop_loss = None
        if not self._has_enough_data():
            return False
        if self._spread_too_wide():
            return False
        if self.last_tradable is False:
            return False
        if self.last_market_status not in {None, "TRADEABLE"}:
            return False

        current_price = self._current_reference_price()
        atr = self._current_atr()
        atr_mean = self._atr_mean()
        if current_price is None or atr is None or atr_mean is None:
            return False

        fast_sma = self._sma(self.htf_fast_window)
        slow_sma = self._sma(self.htf_slow_window)
        if fast_sma is None or slow_sma is None:
            return False

        fast_sma_prev = self._sma(self.htf_fast_window, offset=1)
        slow_sma_prev = self._sma(self.htf_slow_window, offset=1)
        if fast_sma_prev is None or slow_sma_prev is None:
            return False

        trend_up = (
            fast_sma > slow_sma and (fast_sma - fast_sma_prev) >= self.slope_threshold
        )
        trend_down = (
            fast_sma < slow_sma and (fast_sma - fast_sma_prev) <= -self.slope_threshold
        )
        volatility_ok = atr > atr_mean

        prior_highs = list(self.highs)[-(self.pullback_window + 1) : -1]
        prior_lows = list(self.lows)[-(self.pullback_window + 1) : -1]
        if (
            len(prior_highs) < self.pullback_window
            or len(prior_lows) < self.pullback_window
        ):
            return False

        recent_structure_highs = list(self.highs)[
            -(self.local_structure_window + 1) : -1
        ]
        recent_structure_lows = list(self.lows)[-(self.local_structure_window + 1) : -1]
        recent_high = max(prior_highs)
        recent_low = min(prior_lows)
        recent_local_high = max(recent_structure_highs)
        recent_local_low = min(recent_structure_lows)

        pullback_low = min(recent_structure_lows)
        pullback_high = max(recent_structure_highs)
        long_pullback_depth = (
            (recent_high - pullback_low) / recent_high if recent_high else 0.0
        )
        short_pullback_depth = (
            (pullback_high - recent_low) / recent_low if recent_low else 0.0
        )

        long_signal = (
            trend_up
            and volatility_ok
            and long_pullback_depth > self.pullback_threshold
            and current_price > recent_local_high
        )
        if long_signal:
            swing_low = min(list(self.lows)[-(self.local_structure_window + 1) : -1])
            stop_loss = swing_low - (self.stop_atr_multiple * atr)
            if stop_loss < current_price:
                self._entry_direction = OrderDirection.BUY
                self._signal_stop_loss = stop_loss
                return True

        short_signal = (
            trend_down
            and volatility_ok
            and short_pullback_depth > self.pullback_threshold
            and current_price < recent_local_low
        )
        if short_signal:
            swing_high = max(list(self.highs)[-(self.local_structure_window + 1) : -1])
            stop_loss = swing_high + (self.stop_atr_multiple * atr)
            if stop_loss > current_price:
                self._entry_direction = OrderDirection.SELL
                self._signal_stop_loss = stop_loss
                return True

        return False

    def should_exit_trade(self) -> bool:
        if self._entry_direction is None or self._entry_price is None:
            return False

        exit_price = self._current_exit_price()
        if exit_price is None:
            return False

        current_atr = self._current_atr()
        if current_atr is not None:
            self._update_dynamic_risk(exit_price=exit_price, atr=current_atr)

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
        self._highest_price_since_entry = entry_price
        self._lowest_price_since_entry = entry_price

        current_atr = self._current_atr() or 0.0
        configured_stop = self._signal_stop_loss
        if configured_stop is None:
            if direction is OrderDirection.BUY:
                configured_stop = entry_price - max(
                    current_atr * self.stop_atr_multiple, entry_price * 0.001
                )
            else:
                configured_stop = entry_price + max(
                    current_atr * self.stop_atr_multiple, entry_price * 0.001
                )

        self._stop_loss = configured_stop
        if direction is OrderDirection.BUY:
            self._risk_per_unit = max(entry_price - configured_stop, 1e-9)
            self._take_profit = entry_price + (
                self._risk_per_unit * self.risk_reward_multiple
            )
        else:
            self._risk_per_unit = max(configured_stop - entry_price, 1e-9)
            self._take_profit = entry_price - (
                self._risk_per_unit * self.risk_reward_multiple
            )
        self._signal_stop_loss = None

    def on_position_closed(self) -> None:
        self._entry_direction = None
        self._entry_price = None
        self._stop_loss = None
        self._take_profit = None
        self._risk_per_unit = None
        self._highest_price_since_entry = None
        self._lowest_price_since_entry = None
        self._signal_stop_loss = None

    def entry_signal_hints(self) -> dict[str, Any]:
        current_price = self._current_reference_price()
        if self._entry_direction is None or current_price is None:
            return {}
        stop_loss_price = self._signal_stop_loss
        if stop_loss_price is None:
            return {}
        risk_per_unit = abs(current_price - stop_loss_price)
        if risk_per_unit <= 0:
            return {}
        if self._entry_direction is OrderDirection.BUY:
            take_profit_price = current_price + (
                risk_per_unit * self.risk_reward_multiple
            )
            thesis = "higher_timeframe_trend_pullback_continuation_long"
        else:
            take_profit_price = current_price - (
                risk_per_unit * self.risk_reward_multiple
            )
            thesis = "higher_timeframe_trend_pullback_continuation_short"
        current_atr = self._current_atr()
        return {
            "stop_loss_price": round(stop_loss_price, 8),
            "take_profit_price": round(take_profit_price, 8),
            "expected_reward_risk": round(self.risk_reward_multiple, 4),
            "volatility_estimate": round(current_atr, 8)
            if current_atr is not None
            else None,
            "thesis": thesis,
        }

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "prices": list(self.prices),
            "highs": list(self.highs),
            "lows": list(self.lows),
            "last_bid": self.last_bid,
            "last_ask": self.last_ask,
            "last_price": self.last_price,
            "last_market_status": self.last_market_status,
            "last_tradable": self.last_tradable,
            "entry_direction": self._entry_direction.value
            if self._entry_direction
            else None,
            "entry_price": self._entry_price,
            "stop_loss": self._stop_loss,
            "take_profit": self._take_profit,
            "risk_per_unit": self._risk_per_unit,
            "highest_price_since_entry": self._highest_price_since_entry,
            "lowest_price_since_entry": self._lowest_price_since_entry,
            "signal_stop_loss": self._signal_stop_loss,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.prices = deque(
            (float(price) for price in snapshot.get("prices") or []),
            maxlen=self.prices.maxlen,
        )
        self.highs = deque(
            (float(high) for high in snapshot.get("highs") or []),
            maxlen=self.highs.maxlen,
        )
        self.lows = deque(
            (float(low) for low in snapshot.get("lows") or []), maxlen=self.lows.maxlen
        )
        self.last_bid = snapshot.get("last_bid")
        self.last_ask = snapshot.get("last_ask")
        self.last_price = snapshot.get("last_price")
        self.last_market_status = snapshot.get("last_market_status")
        self.last_tradable = snapshot.get("last_tradable")
        direction = snapshot.get("entry_direction")
        self._entry_direction = OrderDirection(direction) if direction else None
        self._entry_price = snapshot.get("entry_price")
        self._stop_loss = snapshot.get("stop_loss")
        self._take_profit = snapshot.get("take_profit")
        self._risk_per_unit = snapshot.get("risk_per_unit")
        self._highest_price_since_entry = snapshot.get("highest_price_since_entry")
        self._lowest_price_since_entry = snapshot.get("lowest_price_since_entry")
        self._signal_stop_loss = snapshot.get("signal_stop_loss")

    def _has_enough_data(self) -> bool:
        minimum_points = max(
            self.htf_slow_window + self.slope_window,
            self.pullback_window + 1,
            self.local_structure_window + 1,
            self.atr_window + self.volatility_window,
        )
        return len(self.prices) >= minimum_points

    def _sma(self, window: int, *, offset: int = 0) -> float | None:
        values = list(self.prices)
        end = len(values) - offset
        start = end - window
        if start < 0 or end <= 0:
            return None
        return fmean(values[start:end])

    def _true_range_at(self, index: int) -> float | None:
        highs = list(self.highs)
        lows = list(self.lows)
        closes = list(self.prices)
        if index <= 0 or index >= len(highs):
            return None
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]
        return max(high - low, abs(high - previous_close), abs(low - previous_close))

    def _atr_series(self) -> list[float]:
        if len(self.prices) <= self.atr_window:
            return []
        true_ranges = [
            tr
            for tr in (
                self._true_range_at(index) for index in range(1, len(self.prices))
            )
            if tr is not None
        ]
        if len(true_ranges) < self.atr_window:
            return []
        return [
            fmean(true_ranges[start : start + self.atr_window])
            for start in range(0, len(true_ranges) - self.atr_window + 1)
        ]

    def _current_atr(self) -> float | None:
        atr_series = self._atr_series()
        return atr_series[-1] if atr_series else None

    def _atr_mean(self) -> float | None:
        atr_series = self._atr_series()
        if len(atr_series) < self.volatility_window:
            return None
        historical = atr_series[-self.volatility_window : -1]
        if not historical:
            return None
        return fmean(historical)

    def _spread_too_wide(self) -> bool:
        if self.last_bid is None or self.last_ask is None:
            return False
        return (self.last_ask - self.last_bid) > self.max_spread_threshold

    def _current_reference_price(self) -> float | None:
        return self.last_price

    def _current_exit_price(self) -> float | None:
        if self._entry_direction is OrderDirection.BUY:
            return self.last_bid if self.last_bid is not None else self.last_price
        if self._entry_direction is OrderDirection.SELL:
            return self.last_ask if self.last_ask is not None else self.last_price
        return self.last_price

    def _update_dynamic_risk(self, *, exit_price: float, atr: float) -> None:
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
            if self._highest_price_since_entry is not None:
                trailing_stop = self._highest_price_since_entry - (
                    atr * self.trailing_atr_multiple
                )
                self._stop_loss = max(self._stop_loss or trailing_stop, trailing_stop)
            return

        move_in_r = (self._entry_price - exit_price) / self._risk_per_unit
        if move_in_r >= self.breakeven_r_multiple:
            self._stop_loss = min(
                self._stop_loss or self._entry_price, self._entry_price
            )
        if self._lowest_price_since_entry is not None:
            trailing_stop = self._lowest_price_since_entry + (
                atr * self.trailing_atr_multiple
            )
            self._stop_loss = min(self._stop_loss or trailing_stop, trailing_stop)
