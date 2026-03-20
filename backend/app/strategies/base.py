from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.broker import OrderDirection


@dataclass(slots=True)
class PriceUpdate:
    instrument: str
    price: float


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

