from __future__ import annotations

from collections import deque
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class FxMicroPullbackStrategy(Strategy):
    """
    Short-term FX strategy designed to capture small continuation moves.

    Core idea:
    - Identify a short-term trend using fast and slow EMAs.
    - Wait for a shallow pullback against that trend.
    - Enter when momentum resumes in the trend direction.
    - Exit quickly on a small extension or when momentum fades.
    """

    name = "fx_micro_pullback"

    def __init__(
        self,
        fast_window: int = 8,
        slow_window: int = 21,
        trend_threshold: float = 0.00015,
        max_spread_threshold: float = 0.00012,
        pullback_threshold: float = 0.00035,
        rejoin_threshold: float = 0.00008,
        take_profit_threshold: float = 0.00045,
        max_adverse_threshold: float = 0.00040,
        momentum_window: int = 3,
    ) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        if momentum_window < 1:
            raise ValueError("momentum_window must be at least 1")

        self.fast_window = fast_window
        self.slow_window = slow_window
        self.trend_threshold = trend_threshold
        self.max_spread_threshold = max_spread_threshold
        self.pullback_threshold = pullback_threshold
        self.rejoin_threshold = rejoin_threshold
        self.take_profit_threshold = take_profit_threshold
        self.max_adverse_threshold = max_adverse_threshold
        self.momentum_window = momentum_window

        self.prices: deque[float] = deque(maxlen=slow_window + momentum_window + 5)
        self.last_price: float | None = None
        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self._entry_direction: OrderDirection | None = None
        self._entry_price: float | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        self.last_price = data.price
        self.last_bid = data.bid
        self.last_ask = data.ask
        self.prices.append(data.price)

    def should_enter_trade(self) -> bool:
        if not self._has_enough_data():
            return False
        if self._spread_too_wide():
            return False

        fast_ema = self._ema(self.fast_window)
        slow_ema = self._ema(self.slow_window)
        trend_strength = (fast_ema - slow_ema) / slow_ema

        if self.last_price is None:
            return False
        pullback_from_fast = (self.last_price - fast_ema) / fast_ema
        momentum = self._recent_momentum()

        if (
            trend_strength >= self.trend_threshold
            and pullback_from_fast <= -self.pullback_threshold
            and momentum >= self.rejoin_threshold
        ):
            self._entry_direction = OrderDirection.BUY
            return True

        if (
            trend_strength <= -self.trend_threshold
            and pullback_from_fast >= self.pullback_threshold
            and momentum <= -self.rejoin_threshold
        ):
            self._entry_direction = OrderDirection.SELL
            return True

        return False

    def should_exit_trade(self) -> bool:
        if not self._has_enough_data():
            return False
        if (
            self._entry_direction is None
            or self._entry_price is None
            or self.last_price is None
        ):
            return False

        fast_ema = self._ema(self.fast_window)
        slow_ema = self._ema(self.slow_window)
        trend_strength = (fast_ema - slow_ema) / slow_ema
        momentum = self._recent_momentum()
        pnl_move = self._move_from_entry()

        if self._entry_direction == OrderDirection.BUY:
            if pnl_move >= self.take_profit_threshold:
                return True
            if pnl_move <= -self.max_adverse_threshold:
                return True
            if momentum <= 0:
                return True
            if trend_strength <= 0:
                return True

        if self._entry_direction == OrderDirection.SELL:
            if pnl_move >= self.take_profit_threshold:
                return True
            if pnl_move <= -self.max_adverse_threshold:
                return True
            if momentum >= 0:
                return True
            if trend_strength >= 0:
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

    def on_position_closed(self) -> None:
        self._entry_direction = None
        self._entry_price = None

    def entry_signal_hints(self) -> dict[str, Any]:
        if not self._has_enough_data():
            return {}
        hints: dict[str, Any] = {
            "expected_reward_risk": round(
                self.take_profit_threshold / max(self.max_adverse_threshold, 1e-9), 4
            ),
            "volatility_estimate": round(abs(self._recent_momentum()), 8),
        }
        if self._entry_direction is OrderDirection.BUY:
            hints["thesis"] = "short_term_trend_continuation_long"
        elif self._entry_direction is OrderDirection.SELL:
            hints["thesis"] = "short_term_trend_continuation_short"
        return hints

    def _has_enough_data(self) -> bool:
        required = self.slow_window + self.momentum_window
        return len(self.prices) >= required and self.last_price is not None

    def _ema(self, window: int) -> float:
        prices = list(self.prices)[-window:]
        multiplier = 2 / (window + 1)

        ema = prices[0]
        for price in prices[1:]:
            ema = ((price - ema) * multiplier) + ema
        return ema

    def _recent_momentum(self) -> float:
        prices = list(self.prices)
        start_price = prices[-(self.momentum_window + 1)]
        end_price = prices[-1]
        return (end_price - start_price) / start_price

    def _move_from_entry(self) -> float:
        if self._entry_price is None:
            raise ValueError("Entry price is not set.")
        current_exit_price = self._current_exit_price()
        raw_move = (current_exit_price - self._entry_price) / self._entry_price

        if self._entry_direction == OrderDirection.BUY:
            return raw_move
        if self._entry_direction == OrderDirection.SELL:
            return -raw_move

        raise ValueError("Entry direction is not set.")

    def _spread_too_wide(self) -> bool:
        spread = self._current_spread()
        return spread is not None and spread > self.max_spread_threshold

    def _current_spread(self) -> float | None:
        if self.last_bid is None or self.last_ask is None:
            return None
        return self.last_ask - self.last_bid

    def _current_exit_price(self) -> float:
        if self._entry_direction == OrderDirection.BUY and self.last_bid is not None:
            return self.last_bid
        if self._entry_direction == OrderDirection.SELL and self.last_ask is not None:
            return self.last_ask
        if self.last_price is None:
            raise ValueError("Last price is not set.")
        return self.last_price

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "prices": list(self.prices),
            "last_price": self.last_price,
            "last_bid": self.last_bid,
            "last_ask": self.last_ask,
            "entry_direction": self._entry_direction.value
            if self._entry_direction
            else None,
            "entry_price": self._entry_price,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        prices = snapshot.get("prices") or []
        self.prices = deque(
            (float(price) for price in prices),
            maxlen=self.slow_window + self.momentum_window + 5,
        )
        self.last_price = snapshot.get("last_price")
        self.last_bid = snapshot.get("last_bid")
        self.last_ask = snapshot.get("last_ask")
        direction = snapshot.get("entry_direction")
        self._entry_direction = OrderDirection(direction) if direction else None
        self._entry_price = snapshot.get("entry_price")
