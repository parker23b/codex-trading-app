from __future__ import annotations

from dataclasses import dataclass, field

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.trading_engine import TradingEngine
from app.strategies.base import PriceUpdate
from app.strategies.registry import StrategyMetadata, strategy_registry

logger = get_logger(__name__)


@dataclass
class StrategyRuntimeManager:
    """
    In-memory strategy runtime manager.

    This is intentionally separate from FastAPI routes so a future worker or
    WebSocket consumer can manage the same runtime contract.
    """

    engines: dict[str, TradingEngine] = field(default_factory=dict)
    strategy_assignments: dict[str, str] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)

    def list_registered_strategies(self) -> list[StrategyMetadata]:
        return strategy_registry.list_metadata()

    def start(self, strategy_name: str, instrument: str) -> None:
        existing_instrument = self.strategy_assignments.get(strategy_name)
        if existing_instrument is not None and existing_instrument != instrument:
            self.stop(existing_instrument)
        if instrument in self.engines:
            raise ValueError(f"Strategy already running for instrument '{instrument}'.")

        strategy = strategy_registry.create(strategy_name)
        engine = TradingEngine(strategy=strategy, broker=get_broker(), instrument=instrument)
        engine.start()
        self.engines[instrument] = engine
        self.strategy_assignments[strategy_name] = instrument
        logger.info("Runtime started", extra={"strategy": strategy_name, "instrument": instrument})

    def stop(self, instrument: str) -> None:
        engine = self.engines.pop(instrument, None)
        if engine is None:
            raise ValueError(f"No active strategy for instrument '{instrument}'.")
        engine.stop()
        self.strategy_assignments.pop(engine.strategy.name, None)
        logger.info("Runtime stopped", extra={"instrument": instrument})

    def process_price_update(self, instrument: str, price: float) -> object | None:
        engine = self.engines.get(instrument)
        if engine is None:
            raise ValueError(f"No active strategy for instrument '{instrument}'.")
        self.last_prices[instrument] = price
        return engine.process_price_update(PriceUpdate(instrument=instrument, price=price))

    def get_engine_for_strategy(self, strategy_name: str) -> TradingEngine | None:
        instrument = self.strategy_assignments.get(strategy_name)
        if instrument is None:
            return None
        return self.engines.get(instrument)

    def is_running(self, strategy_name: str) -> bool:
        return self.get_engine_for_strategy(strategy_name) is not None

    def get_last_price(self, instrument: str) -> float | None:
        return self.last_prices.get(instrument)


runtime_manager = StrategyRuntimeManager()
