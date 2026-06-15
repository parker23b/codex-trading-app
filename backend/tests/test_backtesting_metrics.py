from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.backtesting.execution import (
    SimulatedOpenPositionResult,
    SimulatedPosition,
    SimulatedTradeResult,
)
from app.backtesting.metrics import EquitySample, calculate_metrics
from app.core.broker import OrderDirection


START = datetime(2026, 1, 1, tzinfo=UTC)


def _position(
    *,
    instrument: str = "TEST",
    direction: OrderDirection = OrderDirection.BUY,
    opened_at: int = 0,
    open_price: float = 100,
    size: float = 1,
    entry_fee: float = 0,
    entry_spread_cost: float = 0,
    entry_slippage_cost: float = 0,
) -> SimulatedPosition:
    return SimulatedPosition(
        id=opened_at + 1,
        instrument=instrument,
        direction=direction,
        size=size,
        open_time=START + timedelta(minutes=opened_at),
        open_price=open_price,
        entry_reference_price=100,
        entry_fee=entry_fee,
        entry_spread_cost=entry_spread_cost,
        entry_slippage_cost=entry_slippage_cost,
    )


def _trade(
    pnl: float,
    opened_at: int,
    *,
    instrument: str = "TEST",
    direction: OrderDirection = OrderDirection.BUY,
    duration_minutes: int = 1,
    fees: float = 0,
    spread_cost: float = 0,
    slippage_cost: float = 0,
) -> SimulatedTradeResult:
    position = _position(
        instrument=instrument,
        direction=direction,
        opened_at=opened_at,
    )
    return SimulatedTradeResult(
        position=position,
        close_time=position.open_time + timedelta(minutes=duration_minutes),
        close_price=100 + pnl,
        gross_pnl=pnl,
        fees=fees,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        net_pnl=pnl - fees,
        exit_reason="TEST",
        conservative_ambiguity=False,
        pricing_mode="TEST",
    )


def _open_position(
    *,
    pnl: float,
    opened_at: int,
    marked_at: int,
    instrument: str = "TEST",
    direction: OrderDirection = OrderDirection.BUY,
    entry_fee: float = 0,
    spread_cost: float = 0,
    slippage_cost: float = 0,
) -> SimulatedOpenPositionResult:
    position = _position(
        instrument=instrument,
        direction=direction,
        opened_at=opened_at,
        entry_fee=entry_fee,
        entry_spread_cost=spread_cost,
        entry_slippage_cost=slippage_cost,
    )
    mark_price = 100 + pnl if direction is OrderDirection.BUY else 100 - pnl
    return SimulatedOpenPositionResult(
        position=position,
        mark_time=START + timedelta(minutes=marked_at),
        mark_price=mark_price,
        unrealized_pnl=pnl,
        open_position_value=abs(mark_price * position.size),
        pricing_mode="TEST",
    )


def _metrics(
    *,
    trades: list[SimulatedTradeResult] | None = None,
    open_positions: list[SimulatedOpenPositionResult] | None = None,
    ending_cash: float = 100,
    equity: list[EquitySample] | None = None,
    period_minutes: int = 4,
) -> dict[str, object]:
    return calculate_metrics(
        starting_capital=100,
        ending_cash=ending_cash,
        trades=trades or [],
        equity=equity or [],
        open_positions=open_positions or [],
        period_start=START,
        period_end=START + timedelta(minutes=period_minutes),
        open_position_treatment="MARK_TO_MARKET",
    )


@pytest.mark.parametrize(("gross_pnl", "fees"), [(10, 2), (-10, 2)])
def test_closed_trade_accounting_identity(gross_pnl: float, fees: float):
    trade = _trade(gross_pnl, 0, fees=fees)
    metrics = _metrics(trades=[trade], ending_cash=100 + gross_pnl - fees)

    assert metrics["realised_pnl"] == gross_pnl
    assert metrics["unrealised_pnl"] == 0
    assert metrics["fees_paid"] == fees
    assert metrics["net_closed_trade_pnl"] == gross_pnl - fees
    assert metrics["total_pnl"] == gross_pnl - fees
    assert metrics["ending_cash"] == 100 + gross_pnl - fees
    assert metrics["ending_equity"] == 100 + gross_pnl - fees
    assert metrics["return_pct"] == gross_pnl - fees
    assert metrics["closed_trade_return_pct"] == gross_pnl - fees


def test_open_at_end_and_mixed_accounting_identity():
    closed = _trade(10, 0, fees=2, spread_cost=1, slippage_cost=0.5)
    open_position = _open_position(
        pnl=-3,
        opened_at=2,
        marked_at=4,
        entry_fee=1,
        spread_cost=0.5,
        slippage_cost=0.25,
    )
    metrics = _metrics(
        trades=[closed],
        open_positions=[open_position],
        ending_cash=107,
    )

    assert metrics["realised_pnl"] == 10
    assert metrics["unrealised_pnl"] == -3
    assert metrics["fees_paid"] == 3
    assert metrics["net_closed_trade_pnl"] == 8
    assert metrics["total_pnl"] == 4
    assert metrics["ending_cash"] == 107
    assert metrics["ending_equity"] == 104
    assert metrics["ending_equity"] == (
        metrics["starting_capital"]
        + metrics["realised_pnl"]
        + metrics["unrealised_pnl"]
        - metrics["fees_paid"]
    )
    assert metrics["spread_cost"] == 1.5
    assert metrics["slippage_cost"] == 0.75
    assert metrics["open_positions_at_end"] == 1
    assert metrics["headline_return_includes_unrealised"] is True


def test_long_and_short_open_positions_are_accounted_from_their_marked_pnl():
    rows = [
        _open_position(
            pnl=5,
            opened_at=0,
            marked_at=4,
            direction=OrderDirection.BUY,
        ),
        _open_position(
            pnl=7,
            opened_at=1,
            marked_at=4,
            direction=OrderDirection.SELL,
            instrument="SECOND",
        ),
    ]
    metrics = _metrics(open_positions=rows, ending_cash=100)

    assert metrics["unrealised_pnl"] == 12
    assert metrics["total_pnl"] == 12
    assert metrics["ending_equity"] == 112
    assert metrics["open_position_value"] == 198


def test_drawdown_and_profit_factor_use_closed_trade_equity_semantics():
    trades = [_trade(10, 0), _trade(-5, 2), _trade(0, 3)]
    equity = [
        EquitySample(START, 100, 0, 100, 0),
        EquitySample(START + timedelta(minutes=1), 110, 0, 110, 0),
        EquitySample(START + timedelta(minutes=2), 100, 0, 100, 0),
    ]
    metrics = _metrics(trades=trades, ending_cash=105, equity=equity)

    assert metrics["closed_trade_win_rate"] == pytest.approx(100 / 3)
    assert metrics["closed_trade_gross_profit"] == 10
    assert metrics["closed_trade_gross_loss"] == -5
    assert metrics["profit_factor"] == 2
    assert metrics["maximum_drawdown"] == 10
    assert metrics["maximum_drawdown_percentage"] == pytest.approx(100 / 11)


def test_profit_factor_is_null_when_there_are_no_losing_closed_trades():
    metrics = _metrics(trades=[_trade(10, 0)], ending_cash=110)

    assert metrics["profit_factor"] is None


def test_undefined_closed_trade_metrics_are_null():
    metrics = _metrics()

    assert metrics["closed_trade_win_rate"] is None
    assert metrics["profit_factor"] is None
    assert metrics["average_closed_trade_pnl"] is None
    assert metrics["average_winner"] is None
    assert metrics["average_loser"] is None
    assert metrics["maximum_drawdown"] is None
    assert metrics["maximum_drawdown_percentage"] is None


@pytest.mark.parametrize(
    ("trades", "open_positions", "expected"),
    [
        ([_trade(1, 0, duration_minutes=1)], [], 25),
        ([], [_open_position(pnl=1, opened_at=2, marked_at=4)], 50),
        (
            [
                _trade(1, 0, duration_minutes=3),
                _trade(1, 1, duration_minutes=2, instrument="SECOND"),
            ],
            [],
            75,
        ),
        (
            [_trade(1, 0, duration_minutes=2)],
            [
                _open_position(
                    pnl=1,
                    opened_at=1,
                    marked_at=4,
                    instrument="SECOND",
                )
            ],
            100,
        ),
    ],
)
def test_wall_clock_exposure_uses_union_of_closed_and_open_intervals(
    trades, open_positions, expected
):
    metrics = _metrics(
        trades=trades,
        open_positions=open_positions,
        ending_cash=100 + sum(trade.net_pnl for trade in trades),
    )

    assert metrics["wall_clock_exposure_pct"] == expected
