from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeAlias
from uuid import uuid4

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.signals import EntrySignal, ExitSignal
from app.core.trading_engine import TradingEngine
from app.models.trade import Position, clone_position
from app.strategies.base import PriceUpdate
from app.strategies.registry import StrategyMetadata, strategy_registry

logger = get_logger(__name__)

RuntimeKey: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class EngineUpdateResult:
    key: RuntimeKey
    engine: TradingEngine
    signal: EntrySignal | ExitSignal | None


@dataclass
class StrategyRuntimeManager:
    """
    In-memory strategy runtime manager.

    This is intentionally separate from FastAPI routes so a future worker or
    WebSocket consumer can manage the same runtime contract.
    """

    engines: dict[RuntimeKey, TradingEngine] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    last_price_updated_at: dict[str, datetime] = field(default_factory=dict)
    last_price_errors: dict[str, str] = field(default_factory=dict)

    def list_registered_strategies(self) -> list[StrategyMetadata]:
        return strategy_registry.list_metadata()

    @staticmethod
    def make_key(strategy_name: str, instrument: str) -> RuntimeKey:
        return (strategy_name, instrument)

    def start(
        self,
        strategy_name: str,
        instrument: str,
        *,
        runtime_id: str | None = None,
        strategy_snapshot: dict[str, object] | None = None,
        current_position: Position | None = None,
        activate: bool = True,
    ) -> TradingEngine:
        key = self.make_key(strategy_name, instrument)
        if key in self.engines:
            raise ValueError(f"Strategy '{strategy_name}' is already running for instrument '{instrument}'.")

        metadata = strategy_registry.get_metadata(strategy_name)
        strategy = strategy_registry.create(strategy_name)
        if strategy_snapshot:
            strategy.restore_state_snapshot(strategy_snapshot)
        engine = TradingEngine(
            strategy=strategy,
            broker=get_broker(),
            instrument=instrument,
            runtime_id=runtime_id or str(uuid4()),
        )
        engine.trade_size = metadata.position_size
        engine.current_position = clone_position(current_position)
        if activate:
            engine.start()
        self.engines[key] = engine
        logger.info("Runtime started", extra={"strategy": strategy_name, "instrument": instrument})
        return engine

    def stop(
        self,
        *,
        instrument: str | None = None,
        strategy_name: str | None = None,
    ) -> list[TradingEngine]:
        if instrument is None and strategy_name is None:
            raise ValueError("Either instrument or strategy_name must be provided.")

        matching_keys = self.find_engine_keys(strategy_name=strategy_name, instrument=instrument)
        if not matching_keys:
            parts: list[str] = []
            if strategy_name is not None:
                parts.append(f"strategy '{strategy_name}'")
            if instrument is not None:
                parts.append(f"instrument '{instrument}'")
            detail = " and ".join(parts) if parts else "requested runtime"
            raise ValueError(f"No active strategy for {detail}.")

        stopped_engines: list[TradingEngine] = []
        for key in matching_keys:
            engine = self.engines.pop(key)
            engine.stop()
            stopped_engines.append(engine)
            logger.info(
                "Runtime stopped",
                extra={"strategy": engine.strategy.name, "instrument": engine.instrument},
            )

        if instrument is not None and not self.get_engines_for_instrument(instrument):
            self.last_price_errors.pop(instrument, None)
        return stopped_engines

    def process_price_update(
        self,
        instrument: str,
        price: float,
        *,
        bid: float | None = None,
        ask: float | None = None,
        high: float | None = None,
        low: float | None = None,
        market_status: str | None = None,
        tradable: bool | None = None,
        received_at: datetime | None = None,
    ) -> list[EngineUpdateResult]:
        engines = self.get_engines_for_instrument(instrument)
        if not engines:
            raise ValueError(f"No active strategy for instrument '{instrument}'.")
        self.last_prices[instrument] = price
        self.last_price_updated_at[instrument] = received_at or datetime.now(UTC)
        self.last_price_errors.pop(instrument, None)

        update = PriceUpdate(
            instrument=instrument,
            price=price,
            bid=bid,
            ask=ask,
            high=high,
            low=low,
            market_status=market_status,
            tradable=tradable,
            received_at=received_at or datetime.now(UTC),
        )
        results: list[EngineUpdateResult] = []
        for key, engine in engines:
            results.append(
                EngineUpdateResult(
                    key=key,
                    engine=engine,
                    signal=engine.process_price_update(update),
                )
            )
        return results

    def get_engine_for_strategy(self, strategy_name: str) -> TradingEngine | None:
        engines = self.get_engines_for_strategy(strategy_name)
        return engines[0][1] if engines else None

    def get_engine(self, strategy_name: str, instrument: str) -> TradingEngine | None:
        return self.engines.get(self.make_key(strategy_name, instrument))

    def get_engines_for_strategy(self, strategy_name: str) -> list[tuple[RuntimeKey, TradingEngine]]:
        return [
            (key, engine)
            for key, engine in self.engines.items()
            if key[0] == strategy_name
        ]

    def get_engines_for_instrument(self, instrument: str) -> list[tuple[RuntimeKey, TradingEngine]]:
        return [
            (key, engine)
            for key, engine in self.engines.items()
            if key[1] == instrument
        ]

    def find_engine_keys(
        self,
        *,
        strategy_name: str | None = None,
        instrument: str | None = None,
    ) -> list[RuntimeKey]:
        return [
            key
            for key in self.engines
            if (strategy_name is None or key[0] == strategy_name)
            and (instrument is None or key[1] == instrument)
        ]

    def list_active_instruments(self) -> list[str]:
        return sorted({instrument for _, instrument in self.engines})

    def is_running(self, strategy_name: str) -> bool:
        return bool(self.get_engines_for_strategy(strategy_name))

    def get_last_price(self, instrument: str) -> float | None:
        return self.last_prices.get(instrument)

    def get_last_price_updated_at(self, instrument: str) -> datetime | None:
        return self.last_price_updated_at.get(instrument)

    def set_price_error(self, instrument: str, error: str) -> None:
        self.last_price_errors[instrument] = error

    def get_price_error(self, instrument: str) -> str | None:
        return self.last_price_errors.get(instrument)

    def load_cached_price(
        self,
        instrument: str,
        *,
        price: float | None,
        updated_at: datetime | None,
    ) -> None:
        if price is None:
            return
        self.last_prices[instrument] = price
        if updated_at is not None:
            self.last_price_updated_at[instrument] = updated_at.astimezone(UTC)


runtime_manager = StrategyRuntimeManager()
