from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.broker import Broker
from app.core.logging import get_logger
from app.core.signals import EntrySignal, ExitSignal, SignalKind
from app.models.trade import Position
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
    trade_size: float = 0.0
    active_profile_name: str | None = None
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    runtime_mode: str = "NORMAL"
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

    def process_price_update(
        self, update: PriceUpdate
    ) -> EntrySignal | ExitSignal | None:
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

        if (
            self.runtime_mode != "EXITS_ONLY"
            and self.current_position is None
            and self.strategy.should_enter_trade()
        ):
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
            # This is the raw alpha signal boundary. The engine packages strategy
            # intent into an `EntrySignal`, but it is only a proposal; sizing,
            # admission, and execution authority now live in TradeDecisionService.
            signal = EntrySignal(
                kind=SignalKind.ENTRY,
                strategy_name=self.strategy.name,
                instrument=self.instrument,
                observed_price=update.price,
                signal_at=signal_time,
                direction=direction,
                size=0.0,
                risk_percent=0.0,
                bid=update.bid,
                ask=update.ask,
                market_status=update.market_status,
                tradable=update.tradable,
            )
            return self._apply_entry_signal_hints(signal)

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
            # Exit signals are also emitted as raw strategy intent and later
            # linked back to the authoritative TradeIntent lifecycle.
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

    def _apply_entry_signal_hints(self, signal: EntrySignal) -> EntrySignal:
        hints = self.strategy.entry_signal_hints() or {}
        if not hints:
            return signal
        strategy_metadata = dict(signal.strategy_metadata)
        for key, value in hints.items():
            if key == "stop_loss_price":
                signal.stop_loss_price = float(value) if value is not None else None
            elif key == "take_profit_price":
                signal.take_profit_price = float(value) if value is not None else None
            elif key == "expected_reward_risk":
                signal.expected_reward_risk = (
                    float(value) if value is not None else None
                )
            elif key == "volatility_estimate":
                signal.volatility_estimate = float(value) if value is not None else None
            elif key == "thesis":
                signal.thesis = str(value) if value is not None else None
            elif value is not None:
                strategy_metadata[key] = value
        signal.strategy_metadata = strategy_metadata
        return signal
