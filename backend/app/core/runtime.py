from __future__ import annotations

from dataclasses import dataclass, field

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.trading_engine import TradingEngine
from app.strategies.base import PriceUpdate
from app.strategies.registry import strategy_registry

logger = get_logger(__name__)


@dataclass
class StrategyRuntimeManager:
    """
    In-memory strategy runtime manager.

    This is intentionally separate from FastAPI routes so a future worker or
    WebSocket consumer can manage the same runtime contract.
    """

    engines: dict[str, TradingEngine] = field(default_factory=dict)

    def list_strategies(self) -> list[dict[str, str]]:
        return [
            {"name": name, "description": description}
            for name, description in strategy_registry.describe().items()
        ]

    def start(self, strategy_name: str, instrument: str) -> None:
        if instrument in self.engines:
            raise ValueError(f"Strategy already running for instrument '{instrument}'.")

        strategy = strategy_registry.create(strategy_name)
        engine = TradingEngine(strategy=strategy, broker=get_broker(), instrument=instrument)
        engine.start()
        self.engines[instrument] = engine
        logger.info("Runtime started", extra={"strategy": strategy_name, "instrument": instrument})

    def stop(self, instrument: str) -> None:
        engine = self.engines.pop(instrument, None)
        if engine is None:
            raise ValueError(f"No active strategy for instrument '{instrument}'.")
        engine.stop()
        logger.info("Runtime stopped", extra={"instrument": instrument})

    def process_price_update(self, instrument: str, price: float) -> object | None:
        engine = self.engines.get(instrument)
        if engine is None:
            raise ValueError(f"No active strategy for instrument '{instrument}'.")
        return engine.process_price_update(PriceUpdate(instrument=instrument, price=price))


runtime_manager = StrategyRuntimeManager()

