from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate
from app.strategies.registry import strategy_registry
from app.strategies.volatility_adjusted_pullback_continuation import (
    VolatilityAdjustedPullbackContinuationStrategy,
)


INSTRUMENT = "CS.D.GBPUSD.CFD.IP"
START = datetime(2026, 4, 7, 0, 0, tzinfo=UTC)


def _strategy() -> VolatilityAdjustedPullbackContinuationStrategy:
    return VolatilityAdjustedPullbackContinuationStrategy(
        regime_fast_window=2,
        regime_slow_window=4,
        regime_slope_window=1,
        trigger_ema_window=3,
        setup_ema_window=3,
        atr_window=2,
        volatility_window=4,
        atr_min_percentile=0,
        atr_max_percentile=100,
        pullback_swing_window=2,
    )


def _feed_minute(
    strategy: VolatilityAdjustedPullbackContinuationStrategy,
    minute: int,
    price: float,
    *,
    instrument: str = INSTRUMENT,
    spread: float = 0.00006,
    high_offset: float = 0.00004,
    low_offset: float = 0.00004,
) -> None:
    half_spread = spread / 2
    strategy.on_price_update(
        PriceUpdate(
            instrument=instrument,
            price=price,
            bid=price - half_spread,
            ask=price + half_spread,
            high=price + high_offset,
            low=price - low_offset,
            market_status="TRADEABLE",
            tradable=True,
            received_at=START + timedelta(minutes=minute),
        )
    )


def _warm_long_regime(
    strategy: VolatilityAdjustedPullbackContinuationStrategy,
    *,
    minutes: int = 76,
) -> None:
    for minute in range(minutes):
        _feed_minute(strategy, minute, 1.1000 + (minute * 0.0001))


def _warm_short_regime(
    strategy: VolatilityAdjustedPullbackContinuationStrategy,
    *,
    minutes: int = 76,
) -> None:
    for minute in range(minutes):
        _feed_minute(strategy, minute, 1.1400 - (minute * 0.0001))


def test_registry_lists_generic_forex_pullback_strategy_without_eurusd_default():
    metadata = strategy_registry.get_metadata(
        "volatility_adjusted_pullback_continuation"
    )

    assert metadata.default_instrument == ""
    assert metadata.supported_asset_classes == ("FOREX",)
    assert metadata.risk_per_trade == 0.1
    assert metadata.parameter_profiles[0].parameter_values["max_spread_pips"] == 1.0


def test_long_entry_uses_any_forex_instrument_and_emits_scalper_hints():
    strategy = _strategy()
    _warm_long_regime(strategy)

    _feed_minute(
        strategy,
        76,
        1.1078,
        low_offset=0.00045,
        high_offset=0.00004,
    )
    _feed_minute(strategy, 77, 1.10786)

    assert strategy.should_enter_trade() is False

    _feed_minute(strategy, 77, 1.10795)

    assert strategy.should_enter_trade() is True
    assert strategy.entry_direction() is OrderDirection.BUY

    hints = strategy.entry_signal_hints()
    assert hints["thesis"] == "all_day_forex_pullback_continuation_long"
    assert hints["expected_reward_risk"] == 1.25
    assert hints["max_hold_minutes"] == 20.0
    assert hints["stop_loss_price"] < 1.10795
    assert hints["take_profit_price"] > 1.10795


def test_short_entry_uses_any_forex_instrument_and_emits_scalper_hints():
    strategy = _strategy()
    _warm_short_regime(strategy)

    _feed_minute(
        strategy,
        76,
        1.1322,
        high_offset=0.00045,
        low_offset=0.00004,
    )
    _feed_minute(strategy, 77, 1.13214)

    assert strategy.should_enter_trade() is False

    _feed_minute(strategy, 77, 1.13205)

    assert strategy.should_enter_trade() is True
    assert strategy.entry_direction() is OrderDirection.SELL

    hints = strategy.entry_signal_hints()
    assert hints["thesis"] == "all_day_forex_pullback_continuation_short"
    assert hints["stop_loss_price"] > 1.13205
    assert hints["take_profit_price"] < 1.13205


def test_wide_spread_blocks_entry_against_spread_and_stop_fraction_limits():
    strategy = _strategy()
    _warm_long_regime(strategy)
    _feed_minute(
        strategy,
        76,
        1.1078,
        low_offset=0.00045,
        high_offset=0.00004,
    )
    _feed_minute(strategy, 77, 1.10786)

    assert strategy.should_enter_trade() is False

    _feed_minute(strategy, 77, 1.10795, spread=0.00016)

    assert strategy.should_enter_trade() is False


def test_time_stop_closes_position_after_configured_hold_minutes():
    strategy = _strategy()
    _warm_long_regime(strategy)
    strategy.on_position_opened(direction=OrderDirection.BUY, entry_price=1.10795)

    _feed_minute(strategy, 96, 1.1080)

    assert strategy.should_exit_trade() is True


def test_snapshot_restore_preserves_candles_and_active_trade_state():
    strategy = _strategy()
    _warm_long_regime(strategy)
    strategy.on_position_opened(direction=OrderDirection.BUY, entry_price=1.10795)

    snapshot = strategy.export_state_snapshot()
    restored = _strategy()
    restored.restore_state_snapshot(snapshot)

    assert restored.entry_direction() is OrderDirection.BUY
    assert restored._entry_price == 1.10795
    assert list(restored.minute_candles) == list(strategy.minute_candles)
