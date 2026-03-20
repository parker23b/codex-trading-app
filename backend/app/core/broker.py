from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class AccountType(str, Enum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(slots=True)
class OrderRequest:
    instrument: str
    direction: OrderDirection
    size: float
    price: float
    strategy_name: str


@dataclass(slots=True)
class BrokerPosition:
    instrument: str
    direction: OrderDirection
    size: float
    open_price: float
    opened_at: datetime


@dataclass(slots=True)
class BrokerOrderResult:
    broker_reference: str
    instrument: str
    direction: OrderDirection
    size: float
    price: float
    executed_at: datetime


@dataclass(slots=True)
class BrokerAccountSummary:
    account_id: str
    balance: float
    available: float
    profit_loss: float
    equity: float
    account_type: AccountType


class Broker(ABC):
    """Execution contract implemented by concrete broker adapters."""

    @property
    @abstractmethod
    def account_type(self) -> AccountType:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, instrument: str) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, instrument: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_account_summary(self) -> BrokerAccountSummary:
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
