from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

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
