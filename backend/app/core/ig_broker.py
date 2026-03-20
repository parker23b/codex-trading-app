from __future__ import annotations

from uuid import uuid4

from app.core.broker import (
    AccountType,
    Broker,
    BrokerOrderResult,
    BrokerPosition,
    OrderRequest,
    now_utc,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class IGBroker(Broker):
    """
    Stub IG broker adapter.

    This class already conforms to the broker interface so it can be replaced
    with real IG API integration later without changing the trading engine.
    """

    def __init__(self, account_type: AccountType):
        self._account_type = account_type
        self._positions: dict[str, BrokerPosition] = {}

    @property
    def account_type(self) -> AccountType:
        return self._account_type

    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        logger.info(
            "Stub order placed via IG broker",
            extra={"instrument": order.instrument, "direction": order.direction.value},
        )
        executed_at = now_utc()
        self._positions[order.instrument] = BrokerPosition(
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            open_price=order.price,
            opened_at=executed_at,
        )
        return BrokerOrderResult(
            broker_reference=f"ig-{uuid4()}",
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            price=order.price,
            executed_at=executed_at,
        )

    def close_position(self, instrument: str) -> BrokerOrderResult:
        position = self._positions.pop(instrument, None)
        if position is None:
            raise ValueError(f"No open position for instrument '{instrument}'.")

        logger.info("Stub position closed via IG broker", extra={"instrument": instrument})
        return BrokerOrderResult(
            broker_reference=f"ig-{uuid4()}",
            instrument=position.instrument,
            direction=position.direction,
            size=position.size,
            price=position.open_price,
            executed_at=now_utc(),
        )

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

