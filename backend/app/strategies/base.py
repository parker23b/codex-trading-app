from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.broker import BrokerMarketDetails
from app.core.broker import OrderDirection


@dataclass(slots=True)
class PriceUpdate:
    instrument: str
    price: float
    bid: float | None = None
    ask: float | None = None
    high: float | None = None
    low: float | None = None
    market_status: str | None = None
    tradable: bool | None = None
    received_at: datetime | None = None

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    def executable_price(self, direction: OrderDirection) -> float:
        if direction is OrderDirection.BUY and self.ask is not None:
            return self.ask
        if direction is OrderDirection.SELL and self.bid is not None:
            return self.bid
        return self.price


@dataclass(slots=True)
class ScreeningSnapshot:
    instrument: str
    market_details: BrokerMarketDetails
    refreshed_at: datetime
    streamed: bool = False
    source_tier: str = "TIER2"


@dataclass(slots=True)
class PromotionIntent:
    scanner_name: str
    instrument: str
    score: float
    reason: str
    requested_frequency: str | None = None


class Strategy(ABC):
    """
    Pure strategy contract.

    Strategies receive market data and emit intent only. They are isolated from
    API, persistence, and broker-specific concerns.
    """

    name: str

    @abstractmethod
    def on_price_update(self, data: PriceUpdate) -> None:
        raise NotImplementedError

    @abstractmethod
    def should_enter_trade(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def should_exit_trade(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def entry_direction(self) -> OrderDirection:
        raise NotImplementedError

    def on_position_opened(self, *, direction: OrderDirection, entry_price: float) -> None:
        """
        Optional lifecycle hook invoked after the broker confirms a fill.

        Strategies can use this to align any internal state with the actual
        executed entry price rather than the signal price.
        """

    def on_position_closed(self) -> None:
        """Optional lifecycle hook invoked after the active position is closed."""

    def on_entry_failed(self) -> None:
        """Optional lifecycle hook invoked when an entry order fails."""

    def entry_signal_hints(self) -> dict[str, Any]:
        """
        Return optional non-binding alpha hints for the next entry signal.

        This is the clean handoff point from strategy logic into the external
        allocation/risk pipeline. Strategies may describe thesis, stop distance,
        or reward/risk context here, but the platform remains authoritative for
        sizing, admission, and execution.
        """

        return {}

    def export_state_snapshot(self) -> dict[str, Any]:
        """
        Return a JSON-serializable snapshot of internal strategy state.

        Strategies can override this to make rolling windows and cooldown state
        recoverable across process restarts.
        """

        return {}

    def restore_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore state previously returned by `export_state_snapshot()`."""


class ScreeningStrategy(ABC):
    """Tier 2 screening contract for requesting Tier 1 promotion only."""

    name: str

    @abstractmethod
    def evaluate(self, snapshot: ScreeningSnapshot) -> PromotionIntent | None:
        raise NotImplementedError
