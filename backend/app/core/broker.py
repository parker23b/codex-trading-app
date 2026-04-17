from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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


class BrokerSizingPrecision(str, Enum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    UNSUPPORTED = "UNSUPPORTED"


class BrokerSizingMode(str, Enum):
    EXACT_POINT_VALUE = "EXACT_POINT_VALUE"
    EXACT_CONTRACT_RISK = "EXACT_CONTRACT_RISK"
    APPROXIMATE_PRICE_DELTA = "APPROXIMATE_PRICE_DELTA"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(slots=True)
class OrderRequest:
    instrument: str
    direction: OrderDirection
    size: float
    price: float
    strategy_name: str
    client_request_id: str | None = None


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
    client_request_id: str | None = None
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
    size_step: float | None = None
    min_normal_stop_or_limit_distance: float | None = None
    market_order_preference: str | None = None
    base_currency: str | None = None
    quote_currency: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerRiskSizingQuote:
    instrument: str
    precision: BrokerSizingPrecision
    mode: BrokerSizingMode
    sizing_available: bool
    reason_code: str
    reason: str
    entry_price: float
    risk_amount: float
    requested_size: float = 0.0
    normalized_size: float = 0.0
    risk_per_unit: float | None = None
    stop_distance_price: float | None = None
    sizing_method: str | None = None
    min_stop_distance: float | None = None
    normalization: BrokerSizeNormalization | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerSizeNormalization:
    instrument: str
    requested_size: float
    normalized_size: float
    accepted: bool
    reason_code: str
    reason: str
    min_deal_size: float | None = None
    size_step: float | None = None
    details: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


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
    def close_position(
        self,
        instrument: str,
        *,
        broker_reference: str | None = None,
        client_request_id: str | None = None,
    ) -> BrokerOrderResult:
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

    @abstractmethod
    def quote_risk_sized_order(
        self,
        instrument: str,
        *,
        entry_price: float,
        risk_amount: float,
        stop_loss_price: float | None = None,
        fallback_stop_distance: float | None = None,
    ) -> BrokerRiskSizingQuote:
        raise NotImplementedError

    @abstractmethod
    def normalize_order_size(self, instrument: str, requested_size: float) -> BrokerSizeNormalization:
        raise NotImplementedError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
