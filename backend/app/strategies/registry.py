from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from app.strategies.activity_surveillance_scanner import ActivitySurveillanceScanner
from app.strategies.breakout_guard import BreakoutGuardStrategy
from app.strategies.bad_trade_flow import BadTradeFlowStrategy
from app.strategies.carry_drift import CarryDriftStrategy
from app.strategies.fx_micro_pullback import FxMicroPullbackStrategy
from app.strategies.base import ScreeningStrategy, Strategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.smoke_test_hold import SmokeTestHoldStrategy
from app.strategies.volatility_adjusted_pullback_continuation import (
    VolatilityAdjustedPullbackContinuationStrategy,
)


@dataclass(frozen=True, slots=True)
class StrategyParameterDefinition:
    key: str
    label: str
    value: float
    step: float | None = None
    constructor_key: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyParameterProfile:
    name: str
    description: str
    parameter_values: dict[str, float]


@dataclass(frozen=True, slots=True)
class ResolvedStrategyProfile:
    strategy_name: str
    profile_name: str
    parameter_values: dict[str, float]
    constructor_kwargs: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StrategyMetadata:
    name: str
    description: str
    default_instrument: str
    position_size: float
    risk_per_trade: float
    parameters: tuple[StrategyParameterDefinition, ...]
    family_name: str | None = None
    supported_asset_classes: tuple[str, ...] = ()
    parameter_profiles: tuple[StrategyParameterProfile, ...] = ()


@dataclass(frozen=True, slots=True)
class ScreeningStrategyMetadata:
    name: str
    description: str
    promotion_threshold: float
    refresh_tier: str = "TIER2"


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Callable[..., Strategy]] = {}
        self._metadata: dict[str, StrategyMetadata] = {}
        self._screening_strategies: dict[str, Callable[[], ScreeningStrategy]] = {}
        self._screening_metadata: dict[str, ScreeningStrategyMetadata] = {}

    def register(self, metadata: StrategyMetadata, factory: Callable[..., Strategy]) -> None:
        name = metadata.name
        self._strategies[name] = factory
        self._metadata[name] = metadata

    def create(self, name: str, *, parameters: dict[str, Any] | None = None) -> Strategy:
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' is not registered.")
        return self._strategies[name](**(parameters or {}))

    def list_metadata(self) -> list[StrategyMetadata]:
        return list(self._metadata.values())

    def get_metadata(self, name: str) -> StrategyMetadata:
        if name not in self._metadata:
            raise ValueError(f"Strategy '{name}' is not registered.")
        return self._metadata[name]

    def resolve_profile(self, strategy_name: str, profile_name: str | None = None) -> ResolvedStrategyProfile:
        metadata = self.get_metadata(strategy_name)
        available_profiles = {
            profile.name: profile
            for profile in metadata.parameter_profiles
        }
        target_profile_name = profile_name or (metadata.parameter_profiles[0].name if metadata.parameter_profiles else "default")
        profile = available_profiles.get(target_profile_name)
        if profile is None:
            raise ValueError(f"Profile '{target_profile_name}' is not approved for strategy '{strategy_name}'.")
        constructor_kwargs: dict[str, Any] = {}
        resolved_values: dict[str, float] = {}
        for definition in metadata.parameters:
            value = profile.parameter_values.get(definition.key, definition.value)
            resolved_values[definition.key] = value
            constructor_kwargs[definition.constructor_key or definition.key] = value
        return ResolvedStrategyProfile(
            strategy_name=strategy_name,
            profile_name=target_profile_name,
            parameter_values=resolved_values,
            constructor_kwargs=constructor_kwargs,
        )

    def register_scanner(
        self,
        metadata: ScreeningStrategyMetadata,
        factory: Callable[[], ScreeningStrategy],
    ) -> None:
        self._screening_strategies[metadata.name] = factory
        self._screening_metadata[metadata.name] = metadata

    def create_scanner(self, name: str) -> ScreeningStrategy:
        if name not in self._screening_strategies:
            raise ValueError(f"Screening strategy '{name}' is not registered.")
        return self._screening_strategies[name]()

    def list_screening_metadata(self) -> list[ScreeningStrategyMetadata]:
        return list(self._screening_metadata.values())

    def create_screeners(self) -> list[ScreeningStrategy]:
        return [factory() for factory in self._screening_strategies.values()]


strategy_registry = StrategyRegistry()
strategy_registry.register(
    metadata=StrategyMetadata(
        name=MeanReversionStrategy.name,
        description="Buys when price is sufficiently below the rolling mean and sells when above it.",
        default_instrument="IX.D.FTSE.DAILY.IP",
        position_size=1.0,
        risk_per_trade=0.8,
        family_name="mean_reversion",
        parameters=(
            StrategyParameterDefinition(key="window_size", label="Window", value=20, step=1),
            StrategyParameterDefinition(key="entry_threshold", label="Entry Threshold", value=0.0015, step=0.0001),
            StrategyParameterDefinition(key="exit_threshold", label="Exit Threshold", value=0.0004, step=0.0001),
        ),
        supported_asset_classes=("FOREX", "INDICES"),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Baseline production profile.",
                parameter_values={"window_size": 20, "entry_threshold": 0.0015, "exit_threshold": 0.0004},
            ),
            StrategyParameterProfile(
                name="fast",
                description="Faster-reacting governed profile.",
                parameter_values={"window_size": 12, "entry_threshold": 0.001, "exit_threshold": 0.00025},
            ),
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
        family_name="breakout",
        parameters=(
            StrategyParameterDefinition(key="breakout_window", label="Breakout Window", value=15, step=1),
            StrategyParameterDefinition(key="volatility_floor", label="Volatility Floor", value=0.003, step=0.0001),
        ),
        supported_asset_classes=("FOREX", "INDICES", "COMMODITIES"),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Baseline production profile.",
                parameter_values={"breakout_window": 15, "volatility_floor": 0.003},
            ),
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
        family_name="trend",
        parameters=(
            StrategyParameterDefinition(key="trend_window", label="Trend Window", value=34, step=1),
            StrategyParameterDefinition(key="pullback_threshold", label="Pullback Threshold", value=0.0015, step=0.0001),
        ),
        supported_asset_classes=("FOREX", "INDICES"),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Baseline production profile.",
                parameter_values={"trend_window": 34, "pullback_threshold": 0.0015},
            ),
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
        family_name="fx_pullback",
        parameters=(
            StrategyParameterDefinition(key="fast_window", label="Fast EMA", value=8, step=1),
            StrategyParameterDefinition(key="slow_window", label="Slow EMA", value=21, step=1),
            StrategyParameterDefinition(key="trend_threshold", label="Trend Filter", value=0.00015, step=0.00001),
            StrategyParameterDefinition(key="max_spread_threshold", label="Max Spread", value=0.00012, step=0.00001),
            StrategyParameterDefinition(key="pullback_threshold", label="Pullback Depth", value=0.00035, step=0.00001),
        ),
        supported_asset_classes=("FOREX",),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Baseline production profile.",
                parameter_values={
                    "fast_window": 8,
                    "slow_window": 21,
                    "trend_threshold": 0.00015,
                    "max_spread_threshold": 0.00012,
                    "pullback_threshold": 0.00035,
                },
            ),
        ),
    ),
    factory=FxMicroPullbackStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=VolatilityAdjustedPullbackContinuationStrategy.name,
        description="Trades FX pullback continuation only when higher-timeframe trend, structure, and volatility re-acceleration align.",
        default_instrument="CS.D.EURUSD.MINI.IP",
        position_size=0.4,
        risk_per_trade=0.5,
        family_name="fx_pullback",
        parameters=(
            StrategyParameterDefinition(key="htf_fast_window", label="HTF Fast SMA", value=20, step=1),
            StrategyParameterDefinition(key="htf_slow_window", label="HTF Slow SMA", value=50, step=1),
            StrategyParameterDefinition(key="pullback_threshold", label="Pullback Depth", value=0.0015, step=0.0001),
            StrategyParameterDefinition(key="max_spread_threshold", label="Max Spread", value=0.00012, step=0.00001),
        ),
        supported_asset_classes=("FOREX",),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Baseline production profile.",
                parameter_values={
                    "htf_fast_window": 20,
                    "htf_slow_window": 50,
                    "pullback_threshold": 0.0015,
                    "max_spread_threshold": 0.00012,
                },
            ),
        ),
    ),
    factory=VolatilityAdjustedPullbackContinuationStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=BadTradeFlowStrategy.name,
        description="Deliberately bad high-churn strategy for validating order, position, and trade flow.",
        default_instrument="CS.D.EURUSD.MINI.IP",
        position_size=0.2,
        risk_per_trade=0.1,
        family_name="ops_validation",
        parameters=(
            StrategyParameterDefinition(key="warmup_ticks", label="Warmup Ticks", value=3, step=1),
            StrategyParameterDefinition(key="hold_seconds", label="Hold Seconds", value=3, step=0.5),
            StrategyParameterDefinition(key="lookback_ticks", label="Lookback Ticks", value=3, step=1),
        ),
        supported_asset_classes=("FOREX",),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Flow validation profile.",
                parameter_values={"warmup_ticks": 3, "hold_seconds": 3, "lookback_ticks": 3},
            ),
        ),
    ),
    factory=BadTradeFlowStrategy,
)
strategy_registry.register(
    metadata=StrategyMetadata(
        name=SmokeTestHoldStrategy.name,
        description="One-shot live smoke test that opens a single position, holds for a few minutes, then closes.",
        default_instrument="CS.D.EURUSD.MINI.IP",
        position_size=0.2,
        risk_per_trade=0.1,
        family_name="ops_validation",
        parameters=(
            StrategyParameterDefinition(key="warmup_ticks", label="Warmup Ticks", value=2, step=1),
            StrategyParameterDefinition(key="hold_minutes", label="Hold Minutes", value=0.5, step=0.5),
        ),
        supported_asset_classes=("FOREX",),
        parameter_profiles=(
            StrategyParameterProfile(
                name="default",
                description="Smoke-test profile.",
                parameter_values={"warmup_ticks": 2, "hold_minutes": 0.5},
            ),
        ),
    ),
    factory=SmokeTestHoldStrategy,
)
strategy_registry.register_scanner(
    metadata=ScreeningStrategyMetadata(
        name=ActivitySurveillanceScanner.name,
        description="Promotes instruments into Tier 1 when market status, tradability, and activity conditions align.",
        promotion_threshold=0.75,
    ),
    factory=ActivitySurveillanceScanner,
)
