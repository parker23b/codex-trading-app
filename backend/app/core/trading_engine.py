from __future__ import annotations

from dataclasses import dataclass, field

from app.core.broker import Broker, OrderDirection, OrderRequest
from app.core.logging import get_logger
from app.models.trade import Position, Trade
from app.strategies.base import PriceUpdate, Strategy

logger = get_logger(__name__)


@dataclass(slots=True)
class TradingEngine:
    """
    Core trading coordinator.

    The engine is intentionally independent from FastAPI so it can be reused
    by APIs, workers, schedulers, or real-time stream processors.
    """

    strategy: Strategy
    broker: Broker
    instrument: str
    trade_size: float = 1.0
    active: bool = False
    current_position: Position | None = field(default=None, init=False)

    def start(self) -> None:
        self.active = True
        logger.info("Strategy engine started", extra={"instrument": self.instrument})

    def stop(self) -> None:
        self.active = False
        logger.info("Strategy engine stopped", extra={"instrument": self.instrument})

    def process_price_update(self, update: PriceUpdate) -> Trade | None:
        if not self.active:
            return None

        logger.info(
            "Broker price tick received",
            extra={"strategy": self.strategy.name, "instrument": self.instrument, "price": update.price},
        )
        self.strategy.on_price_update(update)

        if self.current_position is None and self.strategy.should_enter_trade():
            direction = self.strategy.entry_direction()
            logger.info(
                "Strategy entry decision emitted",
                extra={"strategy": self.strategy.name, "instrument": self.instrument, "direction": direction.value},
            )
            order = self.broker.place_order(
                OrderRequest(
                    instrument=self.instrument,
                    direction=direction,
                    size=self.trade_size,
                    price=update.price,
                    strategy_name=self.strategy.name,
                )
            )
            self.current_position = Position(
                instrument=self.instrument,
                direction=direction.value,
                size=self.trade_size,
                open_price=order.price,
                open_time=order.executed_at,
                strategy_name=self.strategy.name,
                account_type=self.broker.account_type.value,
                is_open=True,
            )
            logger.info("Opened position", extra={"instrument": self.instrument})
            return None

        if self.current_position is not None and self.strategy.should_exit_trade():
            logger.info(
                "Strategy exit decision emitted",
                extra={"strategy": self.strategy.name, "instrument": self.instrument},
            )
            closed_order = self.broker.close_position(self.instrument)
            pnl = self._calculate_pnl(
                direction=OrderDirection(self.current_position.direction),
                open_price=self.current_position.open_price,
                close_price=closed_order.price,
                size=self.current_position.size,
            )
            trade = Trade(
                strategy_name=self.current_position.strategy_name,
                instrument=self.current_position.instrument,
                direction=self.current_position.direction,
                size=self.current_position.size,
                open_price=self.current_position.open_price,
                close_price=closed_order.price,
                open_time=self.current_position.open_time,
                close_time=closed_order.executed_at,
                pnl=pnl,
                account_type=self.current_position.account_type,
            )
            self.current_position.is_open = False
            self.current_position.close_price = closed_order.price
            self.current_position.close_time = closed_order.executed_at
            self.current_position.pnl = pnl
            logger.info("Closed position", extra={"instrument": self.instrument, "pnl": pnl})
            self.current_position = None
            return trade

        logger.info(
            "Strategy evaluated with no trade action",
            extra={
                "strategy": self.strategy.name,
                "instrument": self.instrument,
                "price": update.price,
                "has_position": self.current_position is not None,
            },
        )

        return None

    @staticmethod
    def _calculate_pnl(
        *,
        direction: OrderDirection,
        open_price: float,
        close_price: float,
        size: float,
    ) -> float:
        price_delta = close_price - open_price
        signed_delta = price_delta if direction is OrderDirection.BUY else -price_delta
        return signed_delta * size
