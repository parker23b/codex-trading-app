from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from app.core.broker import Broker, OrderDirection
from app.core.logging import get_logger
from app.core.signals import EntrySignal, ExitSignal, SignalKind
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
    runtime_id: str = field(default_factory=lambda: str(uuid4()))
    trade_size: float = 1.0
    active: bool = False
    current_position: Position | None = field(default=None, init=False)
    last_heartbeat_at: datetime | None = field(default=None, init=False)

    def start(self) -> None:
        self.active = True
        self.last_heartbeat_at = datetime.now(UTC)
        logger.info("Strategy engine started", extra={"instrument": self.instrument})

    def stop(self) -> None:
        self.active = False
        self.last_heartbeat_at = datetime.now(UTC)
        logger.info("Strategy engine stopped", extra={"instrument": self.instrument})

    def process_price_update(self, update: PriceUpdate) -> EntrySignal | ExitSignal | None:
        if not self.active:
            return None
        signal_time = update.received_at or datetime.now(UTC)
        self.last_heartbeat_at = signal_time

        logger.debug(
            "Broker price tick received",
            extra={
                "strategy": self.strategy.name,
                "instrument": self.instrument,
                "price": update.price,
                "bid": update.bid,
                "ask": update.ask,
                "spread": update.spread,
            },
        )
        self.strategy.on_price_update(update)

        if self.current_position is None and self.strategy.should_enter_trade():
            direction = self.strategy.entry_direction()
            logger.info(
                "Strategy entry candidate emitted",
                extra={
                    "strategy": self.strategy.name,
                    "instrument": self.instrument,
                    "direction": direction.value,
                    "price": update.price,
                    "bid": update.bid,
                    "ask": update.ask,
                    "spread": update.spread,
                },
            )
            return EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=self.strategy.name,
                instrument=self.instrument,
                observed_price=update.price,
                signal_at=signal_time,
                direction=direction,
                size=self.trade_size,
                risk_percent=0.0,
                bid=update.bid,
                ask=update.ask,
                market_status=update.market_status,
                tradable=update.tradable,
            )

        if self.current_position is not None and self.strategy.should_exit_trade():
            logger.info(
                "Strategy exit candidate emitted",
                extra={
                    "strategy": self.strategy.name,
                    "instrument": self.instrument,
                    "price": update.price,
                    "bid": update.bid,
                    "ask": update.ask,
                    "spread": update.spread,
                },
            )
            return ExitSignal(
                kind=SignalKind.EXIT,
                strategy_name=self.strategy.name,
                instrument=self.instrument,
                observed_price=update.price,
                signal_at=signal_time,
                position=self.current_position,
                bid=update.bid,
                ask=update.ask,
                market_status=update.market_status,
                tradable=update.tradable,
            )

        logger.debug(
            "Strategy evaluated with no trade action",
            extra={
                "strategy": self.strategy.name,
                "instrument": self.instrument,
                "price": update.price,
                "bid": update.bid,
                "ask": update.ask,
                "spread": update.spread,
                "state": "in_position" if self.current_position is not None else "flat",
            },
        )
        return None
