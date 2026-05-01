from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class BadTradeFlowStrategy(Strategy):
    """
    Deliberately poor strategy for exercising the order/trade pipeline.

    It opens often, holds only briefly, and chooses direction from very short
    term price movement so the app can be tested end-to-end under high churn.
    """

    name = "bad_trade_flow"

    def __init__(
        self,
        warmup_ticks: int = 3,
        hold_seconds: float = 3.0,
        lookback_ticks: int = 3,
    ) -> None:
        if warmup_ticks < 1:
            raise ValueError("warmup_ticks must be at least 1")
        if hold_seconds <= 0:
            raise ValueError("hold_seconds must be greater than 0")
        if lookback_ticks < 1:
            raise ValueError("lookback_ticks must be at least 1")

        self.warmup_ticks = warmup_ticks
        self.hold_seconds = hold_seconds
        self.lookback_ticks = lookback_ticks
        self.tick_count = 0
        self.prices: deque[float] = deque(maxlen=lookback_ticks + 2)
        self._opened_at: datetime | None = None
        self._last_update_at: datetime | None = None
        self._in_position = False
        self._entry_direction: OrderDirection | None = None
        self._next_direction = OrderDirection.BUY

    def on_price_update(self, data: PriceUpdate) -> None:
        self.tick_count += 1
        self.prices.append(data.price)
        self._last_update_at = data.received_at

    def should_enter_trade(self) -> bool:
        if self._in_position:
            return False
        if self.tick_count < self.warmup_ticks:
            return False
        if len(self.prices) <= self.lookback_ticks:
            return False

        movement = self._recent_movement()
        if movement > 0:
            self._entry_direction = OrderDirection.BUY
        elif movement < 0:
            self._entry_direction = OrderDirection.SELL
        else:
            self._entry_direction = self._next_direction
        return True

    def should_exit_trade(self) -> bool:
        if (
            not self._in_position
            or self._opened_at is None
            or self._last_update_at is None
        ):
            return False
        held_seconds = (self._last_update_at - self._opened_at).total_seconds()
        return held_seconds >= self.hold_seconds

    def entry_direction(self) -> OrderDirection:
        if self._entry_direction is None:
            raise ValueError(
                "No entry direction available. Evaluate entry signal first."
            )
        return self._entry_direction

    def on_position_opened(
        self, *, direction: OrderDirection, entry_price: float
    ) -> None:
        self._in_position = True
        self._opened_at = self._last_update_at
        self._entry_direction = direction
        self._next_direction = (
            OrderDirection.SELL
            if direction is OrderDirection.BUY
            else OrderDirection.BUY
        )

    def on_position_closed(self) -> None:
        self._in_position = False
        self._opened_at = None
        self._entry_direction = None

    def _recent_movement(self) -> float:
        start_price = self.prices[-(self.lookback_ticks + 1)]
        end_price = self.prices[-1]
        return (end_price - start_price) / start_price

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "tick_count": self.tick_count,
            "prices": list(self.prices),
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
            "last_update_at": self._last_update_at.isoformat()
            if self._last_update_at
            else None,
            "in_position": self._in_position,
            "entry_direction": self._entry_direction.value
            if self._entry_direction
            else None,
            "next_direction": self._next_direction.value,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.tick_count = int(snapshot.get("tick_count") or 0)
        prices = snapshot.get("prices") or []
        self.prices = deque(
            (float(price) for price in prices), maxlen=self.lookback_ticks + 2
        )
        opened_at = snapshot.get("opened_at")
        last_update_at = snapshot.get("last_update_at")
        self._opened_at = datetime.fromisoformat(opened_at) if opened_at else None
        self._last_update_at = (
            datetime.fromisoformat(last_update_at) if last_update_at else None
        )
        self._in_position = bool(snapshot.get("in_position"))
        entry_direction = snapshot.get("entry_direction")
        self._entry_direction = (
            OrderDirection(entry_direction) if entry_direction else None
        )
        next_direction = snapshot.get("next_direction")
        if next_direction:
            self._next_direction = OrderDirection(next_direction)
