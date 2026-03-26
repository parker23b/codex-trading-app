from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from app.strategies.breakout_guard import BreakoutGuardStrategy
from app.strategies.bad_trade_flow import BadTradeFlowStrategy
from app.strategies.carry_drift import CarryDriftStrategy
from app.strategies.fx_micro_pullback import FxMicroPullbackStrategy
from app.strategies.base import Strategy
from app.strategies.mean_reversion import MeanReversionStrategy


@dataclass(frozen=True, slots=True)
class StrategyParameterDefinition:
    key: str
    label: str
    value: float
    step: float | None = None


@dataclass(frozen=True, slots=True)
class StrategyMetadata:
    name: str
    description: str
    default_instrument: str
    position_size: float
    risk_per_trade: float
    parameters: tuple[StrategyParameterDefinition, ...]


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Callable[[], Strategy]] = {}
        self._metadata: dict[str, StrategyMetadata] = {}

    def register(self, metadata: StrategyMetadata, factory: Callable[[], Strategy]) -> None:
        name = metadata.name
        self._strategies[name] = factory
        self._metadata[name] = metadata

    def create(self, name: str) -> Strategy:
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' is not registered.")
        return self._strategies[name]()

    def list_metadata(self) -> list[StrategyMetadata]:
        return list(self._metadata.values())

    def get_metadata(self, name: str) -> StrategyMetadata:
        if name not in self._metadata:
            raise ValueError(f"Strategy '{name}' is not registered.")
        return self._metadata[name]


strategy_registry = StrategyRegistry()
strategy_registry.register(
    metadata=StrategyMetadata(
        name=MeanReversionStrategy.name,
        description="Buys when price is sufficiently below the rolling mean and sells when above it.",
        default_instrument="IX.D.FTSE.DAILY.IP",
        position_size=1.0,
        risk_per_trade=0.8,
        parameters=(
            StrategyParameterDefinition(key="window", label="Window", value=20, step=1),
            StrategyParameterDefinition(key="entry_threshold", label="Entry Threshold", value=1.2, step=0.1),
            StrategyParameterDefinition(key="exit_threshold", label="Exit Threshold", value=0.3, step=0.1),
        ),
    ),
    factory=MeanReversionStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=BreakoutGuardStrategy.name,
        description="Trades directional breaks only when volatility and trend filters align.",
        default_instrument="IX.D.NASDAQ.DAILY.IP",
        position_size=0.8,
        risk_per_trade=1.1,
        parameters=(
            StrategyParameterDefinition(key="breakout_window", label="Breakout Window", value=15, step=1),
            StrategyParameterDefinition(key="atr_filter", label="ATR Filter", value=1.4, step=0.1),
            StrategyParameterDefinition(key="stop_multiple", label="Stop Multiple", value=1.8, step=0.1),
        ),
    ),
    factory=BreakoutGuardStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=CarryDriftStrategy.name,
        description="Follows session trend drift with a tighter mean-reentry stop discipline.",
        default_instrument="IX.D.DAX.DAILY.IP",
        position_size=0.6,
        risk_per_trade=0.7,
        parameters=(
            StrategyParameterDefinition(key="trend_window", label="Trend Window", value=34, step=1),
            StrategyParameterDefinition(key="reentry_buffer", label="Reentry Buffer", value=0.6, step=0.1),
            StrategyParameterDefinition(key="take_profit", label="Take Profit", value=2.3, step=0.1),
        ),
    ),
    factory=CarryDriftStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=FxMicroPullbackStrategy.name,
        description="Follows short-term FX trend continuation after shallow pullbacks and quick momentum rejoin.",
        default_instrument="CS.D.EURUSD.MINI.IP",
        position_size=0.5,
        risk_per_trade=0.4,
        parameters=(
            StrategyParameterDefinition(key="fast_window", label="Fast EMA", value=8, step=1),
            StrategyParameterDefinition(key="slow_window", label="Slow EMA", value=21, step=1),
            StrategyParameterDefinition(key="trend_threshold", label="Trend Filter", value=1.5, step=0.1),
            StrategyParameterDefinition(key="max_spread_threshold", label="Max Spread", value=1.2, step=0.1),
        ),
    ),
    factory=FxMicroPullbackStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=BadTradeFlowStrategy.name,
        description="Deliberately bad high-churn strategy for validating order, position, and trade flow.",
        default_instrument="CS.D.EURUSD.MINI.IP",
        position_size=0.2,
        risk_per_trade=0.1,
        parameters=(
            StrategyParameterDefinition(key="warmup_ticks", label="Warmup Ticks", value=3, step=1),
            StrategyParameterDefinition(key="hold_seconds", label="Hold Seconds", value=3, step=0.5),
            StrategyParameterDefinition(key="lookback_ticks", label="Lookback Ticks", value=3, step=1),
        ),
    ),
    factory=BadTradeFlowStrategy,
)
