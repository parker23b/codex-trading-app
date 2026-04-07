from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.broker import (
    AccountType,
    Broker,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerPosition,
    OrderDirection,
    OrderRequest,
)


@dataclass
class FakeBroker(Broker):
    _account_type: AccountType = AccountType.DEMO
    remote_positions: list[BrokerPosition] = field(default_factory=list)
    market_details_by_instrument: dict[str, BrokerMarketDetails] = field(default_factory=dict)
    place_order_outcomes: list[BrokerOrderResult | Exception] = field(default_factory=list)
    close_position_outcomes: list[BrokerOrderResult | Exception] = field(default_factory=list)
    placed_orders: list[OrderRequest] = field(default_factory=list)
    close_requests: list[dict[str, str | None]] = field(default_factory=list)
    latest_prices: dict[str, float] = field(default_factory=dict)

    @property
    def account_type(self) -> AccountType:
        return self._account_type

    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        self.placed_orders.append(order)
        if not self.place_order_outcomes:
            raise AssertionError("No fake place_order outcome was queued.")
        outcome = self.place_order_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close_position(
        self,
        instrument: str,
        *,
        broker_reference: str | None = None,
        client_request_id: str | None = None,
    ) -> BrokerOrderResult:
        self.close_requests.append(
            {
                "instrument": instrument,
                "broker_reference": broker_reference,
                "client_request_id": client_request_id,
            }
        )
        if not self.close_position_outcomes:
            raise AssertionError("No fake close_position outcome was queued.")
        outcome = self.close_position_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_positions(self) -> list[BrokerPosition]:
        return list(self.remote_positions)

    def get_latest_price(self, instrument: str) -> float:
        return self.latest_prices.get(instrument, 100.0)

    def get_account_summary(self) -> BrokerAccountSummary:
        return BrokerAccountSummary(
            account_id="fake-account",
            balance=100_000.0,
            available=100_000.0,
            profit_loss=0.0,
            equity=100_000.0,
            account_type=self.account_type,
        )

    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        if instrument in self.market_details_by_instrument:
            return self.market_details_by_instrument[instrument]
        price = self.get_latest_price(instrument)
        return BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=price - 0.1,
            offer=price + 0.1,
            high=price + 1.0,
            low=price - 1.0,
            percentage_change=0.0,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time=datetime.now(UTC).isoformat(),
            tradable=True,
        )


def make_order_result(
    *,
    broker_reference: str,
    instrument: str,
    direction: OrderDirection,
    size: float,
    price: float,
    executed_at: datetime,
    client_request_id: str | None = None,
    average_fill_price: float | None = None,
) -> BrokerOrderResult:
    return BrokerOrderResult(
        broker_reference=broker_reference,
        instrument=instrument,
        direction=direction,
        size=size,
        price=price,
        executed_at=executed_at,
        client_request_id=client_request_id,
        filled_size=size,
        average_fill_price=average_fill_price or price,
        submitted_at=executed_at,
        acknowledged_at=executed_at,
    )


def make_broker_position(
    *,
    broker_reference: str,
    instrument: str,
    direction: OrderDirection,
    size: float,
    open_price: float,
    opened_at: datetime,
) -> BrokerPosition:
    return BrokerPosition(
        broker_reference=broker_reference,
        instrument=instrument,
        direction=direction,
        size=size,
        open_price=open_price,
        opened_at=opened_at,
    )
