from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.execution import ExecutionAssumptions, SimulatedExecutionAdapter
from app.core.broker import OrderDirection


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bid_ask_candle() -> HistoricalCandle:
    return HistoricalCandle(
        timestamp=NOW,
        instrument="EUR_USD",
        timeframe="1m",
        bid=PriceBar(99.0, 106.0, 94.0, 101.0),
        ask=PriceBar(101.0, 108.0, 96.0, 103.0),
        mid=PriceBar(100.0, 107.0, 95.0, 102.0),
    )


def test_bid_ask_spread_slippage_and_fees_are_applied_deterministically():
    adapter = SimulatedExecutionAdapter(
        ExecutionAssumptions(
            spread_model="DATASET",
            slippage_model="FIXED_PRICE",
            slippage_value=0.5,
            fee_model="FIXED_PER_ORDER",
            fee_value=2.0,
        )
    )
    position = adapter.open_position(
        instrument="EUR_USD",
        direction=OrderDirection.BUY,
        size=2,
        candle=_bid_ask_candle(),
        stop_loss_price=None,
        take_profit_price=None,
    )
    trade = adapter.close_position(
        position=position,
        candle=_bid_ask_candle(),
        exit_reason="TEST",
    )

    assert position.open_price == 101.5
    assert trade.close_price == 98.5
    assert trade.gross_pnl == -6.0
    assert trade.fees == 4.0
    assert trade.slippage_cost == 2.0
    assert trade.pricing_mode == "HISTORICAL_BID_ASK"


def test_synthetic_spread_is_required_for_midpoint_only_data():
    candle = HistoricalCandle(
        timestamp=NOW,
        instrument="EUR_USD",
        timeframe="1m",
        mid=PriceBar(100, 101, 99, 100),
    )
    adapter = SimulatedExecutionAdapter(ExecutionAssumptions(spread_model="DATASET"))

    with pytest.raises(ValueError, match="synthetic spread"):
        adapter.open_position(
            instrument="EUR_USD",
            direction=OrderDirection.BUY,
            size=1,
            candle=candle,
            stop_loss_price=None,
            take_profit_price=None,
        )


def test_same_candle_stop_and_target_uses_conservative_stop():
    adapter = SimulatedExecutionAdapter(ExecutionAssumptions(spread_model="DATASET"))
    position = adapter.open_position(
        instrument="EUR_USD",
        direction=OrderDirection.BUY,
        size=1,
        candle=_bid_ask_candle(),
        stop_loss_price=95.0,
        take_profit_price=105.0,
    )

    trade = adapter.threshold_exit(position=position, candle=_bid_ask_candle())

    assert trade is not None
    assert trade.close_price == 95.0
    assert trade.spread_cost == 2.0
    assert trade.conservative_ambiguity is True
    assert trade.exit_reason == "STOP_LOSS_CONSERVATIVE_INTRACANDLE"


def test_gap_through_stop_uses_less_favorable_candle_open():
    adapter = SimulatedExecutionAdapter(ExecutionAssumptions(spread_model="DATASET"))
    position = adapter.open_position(
        instrument="EUR_USD",
        direction=OrderDirection.BUY,
        size=1,
        candle=_bid_ask_candle(),
        stop_loss_price=95.0,
        take_profit_price=None,
    )
    gap = HistoricalCandle(
        timestamp=NOW,
        instrument="EUR_USD",
        timeframe="1m",
        bid=PriceBar(90, 93, 89, 92),
        ask=PriceBar(92, 95, 91, 94),
        mid=PriceBar(91, 94, 90, 93),
    )

    trade = adapter.threshold_exit(position=position, candle=gap)

    assert trade is not None
    assert trade.close_price == 90


def test_threshold_spread_cost_does_not_include_market_move():
    candle = HistoricalCandle(
        timestamp=NOW,
        instrument="TEST",
        timeframe="1m",
        mid=PriceBar(100, 110, 90, 105),
    )
    adapter = SimulatedExecutionAdapter(
        ExecutionAssumptions(spread_model="FIXED_PRICE", spread_value=2)
    )
    position = adapter.open_position(
        instrument="TEST",
        direction=OrderDirection.BUY,
        size=1,
        candle=candle,
        stop_loss_price=95,
        take_profit_price=None,
    )

    trade = adapter.threshold_exit(position=position, candle=candle)

    assert trade is not None
    assert trade.spread_cost == 2
