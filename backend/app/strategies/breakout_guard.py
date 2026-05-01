from __future__ import annotations

from collections import deque
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class BreakoutGuardStrategy(Strategy):
    name = "breakout_guard"

    def __init__(
        self, breakout_window: int = 15, volatility_floor: float = 0.003
    ) -> None:
        self.breakout_window = breakout_window
        self.volatility_floor = volatility_floor
        self.prices: deque[float] = deque(maxlen=breakout_window)
        self._entry_direction: OrderDirection | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        self.prices.append(data.price)

    def should_enter_trade(self) -> bool:
        if len(self.prices) < self.breakout_window:
            return False

        current_price = self.prices[-1]
        trailing_prices = list(self.prices)[:-1]
        midpoint = sum(self.prices) / len(self.prices)
        realized_range = (max(self.prices) - min(self.prices)) / midpoint
        if realized_range < self.volatility_floor:
            return False

        if current_price > max(trailing_prices):
            self._entry_direction = OrderDirection.BUY
            return True
        if current_price < min(trailing_prices):
            self._entry_direction = OrderDirection.SELL
            return True
        return False

    def should_exit_trade(self) -> bool:
        if len(self.prices) < self.breakout_window or self._entry_direction is None:
            return False

        current_price = self.prices[-1]
        midpoint = sum(self.prices) / len(self.prices)
        if self._entry_direction is OrderDirection.BUY:
            return current_price < midpoint
        return current_price > midpoint

    def entry_direction(self) -> OrderDirection:
        if self._entry_direction is None:
            raise ValueError("No breakout direction available.")
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
            (float(price) for price in prices), maxlen=self.breakout_window
        )
        direction = snapshot.get("entry_direction")
        self._entry_direction = OrderDirection(direction) if direction else None
