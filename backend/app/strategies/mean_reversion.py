from __future__ import annotations

from collections import deque
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(self, window_size: int = 20, entry_threshold: float = 0.0015, exit_threshold: float = 0.0004):
        self.window_size = window_size
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.prices: deque[float] = deque(maxlen=window_size)
        self.last_price: float | None = None
        self._entry_direction: OrderDirection | None = None

    def on_price_update(self, data: PriceUpdate) -> None:
        self.last_price = data.price
        self.prices.append(data.price)

    def should_enter_trade(self) -> bool:
        if not self._has_enough_data():
            return False

        deviation = self._deviation_from_mean()
        if deviation >= self.entry_threshold:
            self._entry_direction = OrderDirection.SELL
            return True
        if deviation <= -self.entry_threshold:
            self._entry_direction = OrderDirection.BUY
            return True
        return False

    def should_exit_trade(self) -> bool:
        if not self._has_enough_data() or self._entry_direction is None:
            return False

        return abs(self._deviation_from_mean()) <= self.exit_threshold

    def entry_direction(self) -> OrderDirection:
        if self._entry_direction is None:
            raise ValueError("No entry direction available. Evaluate entry signal first.")
        return self._entry_direction

    def _has_enough_data(self) -> bool:
        return len(self.prices) == self.window_size and self.last_price is not None

    def _deviation_from_mean(self) -> float:
        mean_price = sum(self.prices) / len(self.prices)
        assert self.last_price is not None
        return (self.last_price - mean_price) / mean_price

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "prices": list(self.prices),
            "last_price": self.last_price,
            "entry_direction": self._entry_direction.value if self._entry_direction else None,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        prices = snapshot.get("prices") or []
        self.prices = deque((float(price) for price in prices), maxlen=self.window_size)
        self.last_price = snapshot.get("last_price")
        direction = snapshot.get("entry_direction")
        self._entry_direction = OrderDirection(direction) if direction else None
