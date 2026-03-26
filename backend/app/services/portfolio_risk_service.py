from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.signals import EntrySignal, SignalStatus
from app.models.trade import Position, Trade


class PortfolioRiskService:
    """Centralized entry gating for strategy-generated candidates."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def assess_entry(
        self,
        signal: EntrySignal,
        *,
        open_positions: list[Position],
        trades: list[Trade],
    ) -> EntrySignal:
        if signal.tradable is False:
            return self._reject(signal, "Market is not tradable.")

        if self.settings.runtime_one_position_per_instrument and any(
            position.instrument == signal.instrument and position.is_open
            for position in open_positions
        ):
            return self._reject(signal, "Instrument already has an open position.")

        if any(
            position.strategy_name == signal.strategy_name and position.instrument == signal.instrument and position.is_open
            for position in open_positions
        ):
            return self._reject(signal, "Strategy already has an open position for this instrument.")

        open_for_strategy = sum(1 for position in open_positions if position.strategy_name == signal.strategy_name and position.is_open)
        if open_for_strategy >= self.settings.runtime_max_positions_per_strategy:
            return self._reject(signal, "Strategy concurrency limit reached.")

        if len(open_positions) >= self.settings.runtime_max_open_positions:
            return self._reject(signal, "Portfolio max open positions reached.")

        projected_risk = sum(position.risk_percent or 0.0 for position in open_positions) + signal.risk_percent
        if projected_risk > self.settings.runtime_max_open_risk_percent:
            return self._reject(signal, "Portfolio open risk cap reached.")

        daily_pnl = self._daily_closed_pnl(trades)
        if daily_pnl <= -abs(self.settings.runtime_daily_loss_limit):
            return self._reject(signal, "Daily loss cap reached.")

        return replace(signal, status=SignalStatus.APPROVED, reason="Approved by portfolio risk.")

    @staticmethod
    def _reject(signal: EntrySignal, reason: str) -> EntrySignal:
        return replace(signal, status=SignalStatus.REJECTED, reason=reason)

    @staticmethod
    def _daily_closed_pnl(trades: list[Trade]) -> float:
        today = datetime.now(UTC).date()
        return sum(
            trade.pnl
            for trade in trades
            if trade.close_time.astimezone(UTC).date() == today
        )
