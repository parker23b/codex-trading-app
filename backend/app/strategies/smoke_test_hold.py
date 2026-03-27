from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class SmokeTestHoldStrategy(Strategy):
    """
    Minimal live-flow validation strategy.

    It enters after a small warmup, holds the position for a fixed number of
    minutes, exits, and then re-arms for the next cycle.
    """

    name = "smoke_test_hold"

    def __init__(
        self,
        *,
        warmup_ticks: int = 2,
        hold_minutes: float = 0.5,
        direction: OrderDirection = OrderDirection.BUY,
    ) -> None:
        if warmup_ticks < 1:
            raise ValueError("warmup_ticks must be at least 1")
        if hold_minutes <= 0:
            raise ValueError("hold_minutes must be greater than 0")

        self.warmup_ticks = warmup_ticks
        self.hold_minutes = hold_minutes
        self.direction = direction

        self.tick_count = 0
        self._opened_at: datetime | None = None
        self._last_update_at: datetime | None = None
        self._in_position = False

    def on_price_update(self, data: PriceUpdate) -> None:
        self.tick_count += 1
        self._last_update_at = data.received_at

    def should_enter_trade(self) -> bool:
        if self._in_position:
            return False
        return self.tick_count >= self.warmup_ticks

    def should_exit_trade(self) -> bool:
        if not self._in_position or self._opened_at is None or self._last_update_at is None:
            return False
        held_seconds = (self._last_update_at - self._opened_at).total_seconds()
        return held_seconds >= (self.hold_minutes * 60.0)

    def entry_direction(self) -> OrderDirection:
        return self.direction

    def on_position_opened(self, *, direction: OrderDirection, entry_price: float) -> None:
        self._in_position = True
        self._opened_at = self._last_update_at

    def on_position_closed(self) -> None:
        self._in_position = False
        self._opened_at = None

    def on_entry_failed(self) -> None:
        self._in_position = False
        self._opened_at = None

    def export_state_snapshot(self) -> dict[str, Any]:
        return {
            "tick_count": self.tick_count,
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
            "last_update_at": self._last_update_at.isoformat() if self._last_update_at else None,
            "in_position": self._in_position,
        }

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.tick_count = int(snapshot.get("tick_count") or 0)
        opened_at = snapshot.get("opened_at")
        last_update_at = snapshot.get("last_update_at")
        self._opened_at = datetime.fromisoformat(opened_at) if opened_at else None
        self._last_update_at = datetime.fromisoformat(last_update_at) if last_update_at else None
        self._in_position = bool(snapshot.get("in_position"))
