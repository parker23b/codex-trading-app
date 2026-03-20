from __future__ import annotations

from collections.abc import Callable

from app.strategies.base import Strategy
from app.strategies.mean_reversion import MeanReversionStrategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Callable[[], Strategy]] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, factory: Callable[[], Strategy], description: str) -> None:
        self._strategies[name] = factory
        self._descriptions[name] = description

    def create(self, name: str) -> Strategy:
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' is not registered.")
        return self._strategies[name]()

    def describe(self) -> dict[str, str]:
        return dict(self._descriptions)


strategy_registry = StrategyRegistry()
strategy_registry.register(
    name=MeanReversionStrategy.name,
    factory=MeanReversionStrategy,
    description="Buys when price is sufficiently below the rolling mean and sells when above it.",
)

