from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    def __init__(self, initial_time: datetime) -> None:
        self._current = self._as_utc(initial_time)

    def now(self) -> datetime:
        return self._current

    def advance_to(self, value: datetime) -> None:
        candidate = self._as_utc(value)
        if candidate < self._current:
            raise ValueError("Simulated clock cannot move backwards.")
        self._current = candidate

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Simulated time must include a timezone.")
        return value.astimezone(UTC)
