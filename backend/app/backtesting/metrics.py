from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.backtesting.execution import SimulatedTradeResult


@dataclass(frozen=True, slots=True)
class EquitySample:
    timestamp: datetime
    cash: float
    unrealized_pnl: float
    equity: float
    open_position_count: int


def calculate_metrics(
    *,
    starting_capital: float,
    ending_capital: float,
    trades: Iterable[SimulatedTradeResult],
    equity: Iterable[EquitySample],
    open_positions_at_end: int,
) -> dict[str, object]:
    trade_rows = list(trades)
    equity_rows = list(equity)
    winners = [trade for trade in trade_rows if trade.net_pnl > 0]
    losers = [trade for trade in trade_rows if trade.net_pnl < 0]
    breakeven = [trade for trade in trade_rows if trade.net_pnl == 0]
    gross_profit = sum(trade.net_pnl for trade in winners)
    gross_loss = sum(trade.net_pnl for trade in losers)
    net_pnl = sum(trade.net_pnl for trade in trade_rows)
    drawdowns = _drawdowns(equity_rows)
    exposure_seconds = sum(
        max((trade.close_time - trade.position.open_time).total_seconds(), 0.0)
        for trade in trade_rows
    )
    total_period_seconds = (
        max((equity_rows[-1].timestamp - equity_rows[0].timestamp).total_seconds(), 0)
        if len(equity_rows) >= 2
        else 0
    )
    return {
        "starting_capital": starting_capital,
        "ending_capital": ending_capital,
        "absolute_return": ending_capital - starting_capital,
        "percentage_return": (
            ((ending_capital - starting_capital) / starting_capital) * 100
            if starting_capital
            else None
        ),
        "total_trades": len(trade_rows),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "breakeven_trades": len(breakeven),
        "win_rate": (len(winners) / len(trade_rows) * 100) if trade_rows else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "maximum_drawdown": max((item[0] for item in drawdowns), default=0.0),
        "maximum_drawdown_percentage": max(
            (item[1] for item in drawdowns), default=0.0
        ),
        "profit_factor": (
            gross_profit / abs(gross_loss)
            if gross_loss < 0
            else (None if gross_profit == 0 else None)
        ),
        "average_trade_pnl": net_pnl / len(trade_rows) if trade_rows else None,
        "average_winner": (gross_profit / len(winners) if winners else None),
        "average_loser": gross_loss / len(losers) if losers else None,
        "largest_winner": (max((trade.net_pnl for trade in winners), default=None)),
        "largest_loser": (min((trade.net_pnl for trade in losers), default=None)),
        "exposure_time_percent": (
            min(exposure_seconds / total_period_seconds * 100, 100.0)
            if total_period_seconds > 0
            else None
        ),
        "fees_paid": sum(trade.fees for trade in trade_rows),
        "spread_cost": sum(trade.spread_cost for trade in trade_rows),
        "slippage_cost": sum(trade.slippage_cost for trade in trade_rows),
        "open_positions_at_end": open_positions_at_end,
    }


def calculate_grouped_metrics(
    *,
    starting_capital: float,
    trades: Iterable[SimulatedTradeResult],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[SimulatedTradeResult]] = defaultdict(list)
    for trade in trades:
        grouped[trade.position.instrument].append(trade)
    return {
        instrument: calculate_metrics(
            starting_capital=starting_capital,
            ending_capital=starting_capital
            + sum(trade.net_pnl for trade in instrument_trades),
            trades=instrument_trades,
            equity=[],
            open_positions_at_end=0,
        )
        for instrument, instrument_trades in sorted(grouped.items())
    }


def equity_drawdown(
    samples: Iterable[EquitySample],
) -> list[tuple[EquitySample, float, float]]:
    result: list[tuple[EquitySample, float, float]] = []
    peak: float | None = None
    for sample in samples:
        peak = sample.equity if peak is None else max(peak, sample.equity)
        drawdown = max(peak - sample.equity, 0.0)
        drawdown_percent = drawdown / peak * 100 if peak else 0.0
        result.append((sample, drawdown, drawdown_percent))
    return result


def _drawdowns(samples: list[EquitySample]) -> list[tuple[float, float]]:
    return [
        (drawdown, drawdown_percent)
        for _, drawdown, drawdown_percent in equity_drawdown(samples)
    ]
