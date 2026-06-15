from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.backtesting.execution import (
    SimulatedOpenPositionResult,
    SimulatedTradeResult,
)


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
    ending_cash: float,
    trades: Iterable[SimulatedTradeResult],
    equity: Iterable[EquitySample],
    open_positions: Iterable[SimulatedOpenPositionResult],
    period_start: datetime,
    period_end: datetime,
    open_position_treatment: str,
) -> dict[str, object]:
    trade_rows = list(trades)
    equity_rows = list(equity)
    open_rows = list(open_positions)
    winners = [trade for trade in trade_rows if trade.net_pnl > 0]
    losers = [trade for trade in trade_rows if trade.net_pnl < 0]
    breakeven = [trade for trade in trade_rows if trade.net_pnl == 0]
    gross_profit = sum(trade.net_pnl for trade in winners)
    gross_loss = sum(trade.net_pnl for trade in losers)
    realised_pnl = sum(trade.gross_pnl for trade in trade_rows)
    unrealised_pnl = sum(position.unrealized_pnl for position in open_rows)
    fees_paid = sum(trade.fees for trade in trade_rows) + sum(
        position.position.entry_fee for position in open_rows
    )
    net_closed_trade_pnl = sum(trade.net_pnl for trade in trade_rows)
    total_pnl = realised_pnl + unrealised_pnl - fees_paid
    ending_equity = ending_cash + unrealised_pnl
    drawdowns = _drawdowns(equity_rows)
    exposure_seconds = _union_duration_seconds(
        [
            (trade.position.open_time, trade.close_time)
            for trade in trade_rows
            if trade.close_time >= trade.position.open_time
        ]
        + [
            (position.position.open_time, position.mark_time)
            for position in open_rows
            if position.mark_time >= position.position.open_time
        ]
    )
    total_period_seconds = max((period_end - period_start).total_seconds(), 0)
    return {
        "starting_capital": starting_capital,
        "realised_pnl": realised_pnl,
        "unrealised_pnl": unrealised_pnl,
        "fees_paid": fees_paid,
        "spread_cost": sum(trade.spread_cost for trade in trade_rows)
        + sum(position.position.entry_spread_cost for position in open_rows),
        "slippage_cost": sum(trade.slippage_cost for trade in trade_rows)
        + sum(position.position.entry_slippage_cost for position in open_rows),
        "net_closed_trade_pnl": net_closed_trade_pnl,
        "total_pnl": total_pnl,
        "ending_equity": ending_equity,
        "ending_cash": ending_cash,
        "open_position_value": sum(
            position.open_position_value for position in open_rows
        ),
        "return_pct": (
            (total_pnl / starting_capital) * 100 if starting_capital else None
        ),
        "closed_trade_return_pct": (
            (net_closed_trade_pnl / starting_capital) * 100
            if starting_capital
            else None
        ),
        "headline_return_includes_unrealised": bool(open_rows),
        "closed_trade_count": len(trade_rows),
        "winning_closed_trades": len(winners),
        "losing_closed_trades": len(losers),
        "breakeven_closed_trades": len(breakeven),
        "closed_trade_win_rate": (
            len(winners) / len(trade_rows) * 100 if trade_rows else None
        ),
        "closed_trade_gross_profit": gross_profit,
        "closed_trade_gross_loss": gross_loss,
        "maximum_drawdown": (max(item[0] for item in drawdowns) if drawdowns else None),
        "maximum_drawdown_percentage": (
            max(item[1] for item in drawdowns) if drawdowns else None
        ),
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else None,
        "average_closed_trade_pnl": (
            net_closed_trade_pnl / len(trade_rows) if trade_rows else None
        ),
        "average_winner": (gross_profit / len(winners) if winners else None),
        "average_loser": gross_loss / len(losers) if losers else None,
        "largest_winner": (max((trade.net_pnl for trade in winners), default=None)),
        "largest_loser": (min((trade.net_pnl for trade in losers), default=None)),
        "wall_clock_exposure_pct": (
            exposure_seconds / total_period_seconds * 100
            if total_period_seconds > 0
            else None
        ),
        "open_positions_at_end": len(open_rows),
        "open_position_treatment": open_position_treatment,
    }


def calculate_grouped_metrics(
    *,
    starting_capital: float,
    trades: Iterable[SimulatedTradeResult],
    open_positions: Iterable[SimulatedOpenPositionResult],
    period_start: datetime,
    period_end: datetime,
    open_position_treatment: str,
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[SimulatedTradeResult]] = defaultdict(list)
    for trade in trades:
        grouped[trade.position.instrument].append(trade)
    grouped_open: dict[str, list[SimulatedOpenPositionResult]] = defaultdict(list)
    for position in open_positions:
        grouped_open[position.position.instrument].append(position)
    instruments = sorted(set(grouped) | set(grouped_open))
    return {
        instrument: calculate_metrics(
            starting_capital=starting_capital,
            ending_cash=starting_capital
            + sum(trade.net_pnl for trade in grouped[instrument])
            - sum(position.position.entry_fee for position in grouped_open[instrument]),
            trades=grouped[instrument],
            equity=[],
            open_positions=grouped_open[instrument],
            period_start=period_start,
            period_end=period_end,
            open_position_treatment=open_position_treatment,
        )
        for instrument in instruments
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


def _union_duration_seconds(
    intervals: list[tuple[datetime, datetime]],
) -> float:
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    start, end = ordered[0]
    total = 0.0
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
            continue
        total += (end - start).total_seconds()
        start, end = next_start, next_end
    return total + (end - start).total_seconds()
