from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.backtesting.execution import SimulatedPosition, SimulatedTradeResult
from app.backtesting.metrics import EquitySample, calculate_metrics
from app.core.broker import OrderDirection


START = datetime(2026, 1, 1, tzinfo=UTC)


def _trade(pnl: float, index: int) -> SimulatedTradeResult:
    position = SimulatedPosition(
        id=index,
        instrument="TEST",
        direction=OrderDirection.BUY,
        size=1,
        open_time=START + timedelta(minutes=index),
        open_price=100,
        entry_reference_price=100,
        entry_fee=0,
        entry_spread_cost=0,
        entry_slippage_cost=0,
    )
    return SimulatedTradeResult(
        position=position,
        close_time=position.open_time + timedelta(minutes=1),
        close_price=100 + pnl,
        gross_pnl=pnl,
        fees=0,
        spread_cost=0,
        slippage_cost=0,
        net_pnl=pnl,
        exit_reason="TEST",
        conservative_ambiguity=False,
        pricing_mode="TEST",
    )


def test_metrics_cover_returns_profit_factor_win_rate_and_drawdown():
    trades = [_trade(10, 0), _trade(-5, 2), _trade(0, 4)]
    equity = [
        EquitySample(START, 100, 0, 100, 0),
        EquitySample(START + timedelta(minutes=1), 110, 0, 110, 0),
        EquitySample(START + timedelta(minutes=2), 100, 0, 100, 0),
    ]

    metrics = calculate_metrics(
        starting_capital=100,
        ending_capital=105,
        trades=trades,
        equity=equity,
        open_positions_at_end=0,
    )

    assert metrics["absolute_return"] == 5
    assert metrics["percentage_return"] == 5
    assert metrics["win_rate"] == pytest.approx(100 / 3)
    assert metrics["gross_profit"] == 10
    assert metrics["gross_loss"] == -5
    assert metrics["profit_factor"] == 2
    assert metrics["maximum_drawdown"] == 10
    assert metrics["maximum_drawdown_percentage"] == pytest.approx(100 / 11)


def test_undefined_metrics_are_null():
    metrics = calculate_metrics(
        starting_capital=100,
        ending_capital=100,
        trades=[],
        equity=[],
        open_positions_at_end=0,
    )

    assert metrics["win_rate"] is None
    assert metrics["profit_factor"] is None
    assert metrics["average_trade_pnl"] is None
    assert metrics["average_winner"] is None
    assert metrics["average_loser"] is None
