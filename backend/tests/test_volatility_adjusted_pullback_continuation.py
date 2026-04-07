from __future__ import annotations

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate
from app.strategies.registry import strategy_registry
from app.strategies.volatility_adjusted_pullback_continuation import (
    VolatilityAdjustedPullbackContinuationStrategy,
)


def _feed_tick(
    strategy: VolatilityAdjustedPullbackContinuationStrategy,
    price: float,
    *,
    spread: float = 0.00006,
    high_offset: float = 0.00035,
    low_offset: float = 0.00035,
) -> None:
    half_spread = spread / 2
    strategy.on_price_update(
        PriceUpdate(
            instrument="CS.D.EURUSD.MINI.IP",
            price=price,
            bid=price - half_spread,
            ask=price + half_spread,
            high=price + high_offset,
            low=price - low_offset,
            market_status="TRADEABLE",
            tradable=True,
        )
    )


def test_registry_lists_volatility_adjusted_pullback_continuation_strategy():
    metadata = strategy_registry.get_metadata("volatility_adjusted_pullback_continuation")

    assert metadata.default_instrument == "CS.D.EURUSD.MINI.IP"
    assert metadata.position_size == 0.4


def test_long_entry_and_trailing_exit():
    strategy = VolatilityAdjustedPullbackContinuationStrategy()

    prices = [1.1000 + (step * 0.0003) for step in range(60)]
    prices.extend([1.1168, 1.1163, 1.1158, 1.1153, 1.1148, 1.1151, 1.1155, 1.1160, 1.1164])
    for index, price in enumerate(prices):
        if index < 50:
            _feed_tick(strategy, price, high_offset=0.00025, low_offset=0.00025)
            continue
        if 60 <= index <= 64:
            _feed_tick(strategy, price, high_offset=0.00018, low_offset=0.00045)
            continue
        _feed_tick(strategy, price, high_offset=0.00012, low_offset=0.00018)

    assert strategy.should_enter_trade() is True
    assert strategy.entry_direction() is OrderDirection.BUY

    strategy.on_position_opened(direction=OrderDirection.BUY, entry_price=1.11643)

    for price in [1.1169, 1.1174, 1.1179, 1.1186]:
        _feed_tick(strategy, price, high_offset=0.00045, low_offset=0.00015)

    _feed_tick(strategy, 1.1176, high_offset=0.00012, low_offset=0.00035)

    assert strategy.should_exit_trade() is True


def test_short_entry_and_trailing_exit():
    strategy = VolatilityAdjustedPullbackContinuationStrategy()

    prices = [1.1400 - (step * 0.0003) for step in range(60)]
    prices.extend([1.1232, 1.1237, 1.1242, 1.1247, 1.1252, 1.1249, 1.1245, 1.1240, 1.1236])
    for index, price in enumerate(prices):
        if index < 50:
            _feed_tick(strategy, price, high_offset=0.00025, low_offset=0.00025)
            continue
        if 60 <= index <= 64:
            _feed_tick(strategy, price, high_offset=0.00045, low_offset=0.00018)
            continue
        _feed_tick(strategy, price, high_offset=0.00018, low_offset=0.00012)

    assert strategy.should_enter_trade() is True
    assert strategy.entry_direction() is OrderDirection.SELL

    strategy.on_position_opened(direction=OrderDirection.SELL, entry_price=1.12357)

    for price in [1.1230, 1.1224, 1.1219, 1.1213]:
        _feed_tick(strategy, price, high_offset=0.00015, low_offset=0.00045)

    _feed_tick(strategy, 1.1222, high_offset=0.00035, low_offset=0.00012)

    assert strategy.should_exit_trade() is True


def test_snapshot_restore_preserves_active_trade_state():
    strategy = VolatilityAdjustedPullbackContinuationStrategy()
    for price in [1.1000 + (step * 0.0002) for step in range(80)]:
        _feed_tick(strategy, price)

    strategy.on_position_opened(direction=OrderDirection.BUY, entry_price=1.1150)
    _feed_tick(strategy, 1.1162, high_offset=0.0005, low_offset=0.00015)
    snapshot = strategy.export_state_snapshot()

    restored = VolatilityAdjustedPullbackContinuationStrategy()
    restored.restore_state_snapshot(snapshot)

    assert restored.entry_direction() is OrderDirection.BUY
    assert restored._entry_price == 1.1150
    assert restored._highest_price_since_entry is not None
    assert list(restored.prices) == list(strategy.prices)


def test_wide_spread_blocks_entry():
    strategy = VolatilityAdjustedPullbackContinuationStrategy(max_spread_threshold=0.00005)

    prices = [1.1000 + (step * 0.0003) for step in range(60)]
    prices.extend([1.1168, 1.1163, 1.1158, 1.1153, 1.1148, 1.1151, 1.1155, 1.1160, 1.1164])
    for price in prices:
        _feed_tick(strategy, price, spread=0.00008)

    assert strategy.should_enter_trade() is False
