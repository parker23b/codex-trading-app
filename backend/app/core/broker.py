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


class BrokerOrderStatus(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(slots=True)
class OrderRequest:
    instrument: str
    direction: OrderDirection
    size: float
    price: float
    strategy_name: str


@dataclass(slots=True)
class BrokerPosition:
    broker_reference: str
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
    status: BrokerOrderStatus = BrokerOrderStatus.FILLED
    requested_size: float | None = None
    filled_size: float | None = None
    average_fill_price: float | None = None
    submitted_at: datetime | None = None
    acknowledged_at: datetime | None = None
    reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    requires_manual_review: bool = False


@dataclass(slots=True)
class BrokerAccountSummary:
    account_id: str
    balance: float
    available: float
    profit_loss: float
    equity: float
    account_type: AccountType


@dataclass(slots=True)
class BrokerMarketDetails:
    instrument: str
    name: str
    bid: float | None
    offer: float | None
    high: float | None
    low: float | None
    percentage_change: float | None
    net_change: float | None
    market_status: str | None
    update_time: str | None
    tradable: bool
    min_deal_size: float | None = None
    min_normal_stop_or_limit_distance: float | None = None
    market_order_preference: str | None = None


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
    def close_position(self, instrument: str, *, broker_reference: str | None = None) -> BrokerOrderResult:
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

    @abstractmethod
    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
