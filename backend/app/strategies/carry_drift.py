from __future__ import annotations

from collections import deque
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class CarryDriftStrategy(Strategy):
    name = "carry_drift"

    def __init__(
        self, trend_window: int = 12, pullback_threshold: float = 0.0015
    ) -> None:
        self.trend_window = trend_window
        self.pullback_threshold = pullback_threshold
        self.prices: deque[float] = deque(maxlen=trend_window)
        self._entry_direction: OrderDirection | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        self.prices.append(data.price)

    def should_enter_trade(self) -> bool:
        if len(self.prices) < self.trend_window:
            return False

        initial_price = self.prices[0]
        current_price = self.prices[-1]
        trend = (current_price - initial_price) / initial_price
        if trend >= self.pullback_threshold:
            self._entry_direction = OrderDirection.BUY
            return True
        if trend <= -self.pullback_threshold:
            self._entry_direction = OrderDirection.SELL
            return True
        return False

    def should_exit_trade(self) -> bool:
        if len(self.prices) < self.trend_window or self._entry_direction is None:
            return False

        average_price = sum(self.prices) / len(self.prices)
        current_price = self.prices[-1]
        if self._entry_direction is OrderDirection.BUY:
            return current_price < average_price
        return current_price > average_price

    def entry_direction(self) -> OrderDirection:
        if self._entry_direction is None:
            raise ValueError("No drift direction available.")
        return self._entry_direction

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "prices": list(self.prices),
            "entry_direction": self._entry_direction.value
            if self._entry_direction
            else None,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        prices = snapshot.get("prices") or []
        self.prices = deque(
            (float(price) for price in prices), maxlen=self.trend_window
        )
        direction = snapshot.get("entry_direction")
        self._entry_direction = OrderDirection(direction) if direction else None
