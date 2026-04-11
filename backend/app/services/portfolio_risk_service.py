from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.core.signals import EntrySignal, SignalStatus
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Position, Trade, TradeIntent, TradeIntentState
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService


class PortfolioRiskService:
    """Layered entry gating with auditable rule outcomes."""

    SMOKE_TEST_STRATEGIES = {"smoke_test_hold"}

    def __init__(self, session: Session | None = None) -> None:
        self.settings = get_settings()
        self.session = session
        self.runtime_state_service = RuntimeStateService(session) if session is not None else None
        self.trade_service = TradeService(session) if session is not None else None

    def assess_entry(
        self,
        signal: EntrySignal,
        *,
        open_positions: list[Position],
        trades: list[Trade],
    ) -> EntrySignal:
        recent_intents = self._load_recent_entry_trade_intents(signal)
        runtimes = self.runtime_state_service.list_active_runtimes() if self.runtime_state_service is not None else []

        layers = [
            self._evaluate_pre_trade(signal, open_positions, trades, recent_intents),
            self._evaluate_portfolio(signal, open_positions, trades),
            self._evaluate_market_quality(signal),
            self._evaluate_platform_health(signal, runtimes),
            self._evaluate_kill_switch(signal, trades, runtimes),
        ]

        rejection_layer: str | None = None
        rejection_reason: str | None = None
        audited_layers: list[dict[str, object]] = []
        blocked = False
        for layer in layers:
            if blocked:
                audited_layers.append(
                    {
                        "layer": layer["layer"],
                        "status": "SKIPPED",
                        "passed": None,
                        "reason": "Skipped after earlier rejection.",
                        "checks": [],
                    }
                )
                continue
            audited_layers.append(layer)
            if layer["passed"] is False:
                rejection_layer = str(layer["layer"])
                rejection_reason = str(layer["reason"])
                blocked = True

        approved = rejection_reason is None
        summary = self._build_summary(
            signal=signal,
            open_positions=open_positions,
            trades=trades,
            runtimes=runtimes,
            recent_intents=recent_intents,
            approved=approved,
            rejection_layer=rejection_layer,
        )
        if approved:
            return replace(
                signal,
                status=SignalStatus.APPROVED,
                reason="Approved by layered risk controls.",
                rejection_layer=None,
                audit_trail=audited_layers,
                audit_summary=summary,
            )
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=rejection_reason,
            rejection_layer=rejection_layer,
            audit_trail=audited_layers,
            audit_summary=summary,
        )

    def _evaluate_pre_trade(
        self,
        signal: EntrySignal,
        open_positions: list[Position],
        trades: list[Trade],
        recent_intents: list[TradeIntent],
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        checks.append(
            self._check(
                "tradable",
                signal.tradable is not False,
                "Market is tradable for fresh entries.",
                "Market is not tradable.",
                actual=signal.tradable,
            )
        )

        open_same_instrument = [
            position
            for position in open_positions
            if position.instrument == signal.instrument and position.is_open
        ]
        one_position_ok = (
            not self.settings.runtime_one_position_per_instrument or not open_same_instrument
        )
        checks.append(
            self._check(
                "one_position_per_instrument",
                one_position_ok,
                "Instrument-level position limit is clear.",
                "Instrument already has an open position.",
                actual=len(open_same_instrument),
                limit=1,
            )
        )

        same_strategy_instrument = [
            position
            for position in open_positions
            if position.strategy_name == signal.strategy_name
            and position.instrument == signal.instrument
            and position.is_open
        ]
        checks.append(
            self._check(
                "strategy_instrument_uniqueness",
                not same_strategy_instrument,
                "No duplicate strategy position for this instrument.",
                "Strategy already has an open position for this instrument.",
                actual=len(same_strategy_instrument),
                limit=0,
            )
        )

        open_for_strategy = [
            position for position in open_positions if position.strategy_name == signal.strategy_name and position.is_open
        ]
        checks.append(
            self._check(
                "strategy_position_limit",
                len(open_for_strategy) < self.settings.runtime_max_positions_per_strategy,
                "Strategy concurrency is within limits.",
                "Strategy concurrency limit reached.",
                actual=len(open_for_strategy),
                limit=self.settings.runtime_max_positions_per_strategy,
            )
        )

        last_trade = self._latest_closed_trade(trades, signal)
        loss_cutoff = signal.signal_at - timedelta(seconds=self.settings.runtime_cooldown_after_loss_seconds)
        recent_loss = (
            last_trade is not None
            and last_trade.pnl < 0
            and last_trade.close_time.astimezone(UTC) >= loss_cutoff.astimezone(UTC)
        )
        checks.append(
            self._check(
                "cooldown_after_loss",
                not recent_loss,
                "Loss cooldown is clear.",
                "Cooldown after recent losing trade is active.",
                actual=last_trade.close_time.isoformat() if recent_loss and last_trade is not None else None,
                limit=self.settings.runtime_cooldown_after_loss_seconds,
            )
        )

        exit_cutoff = signal.signal_at - timedelta(seconds=self.settings.runtime_cooldown_after_exit_seconds)
        recent_exit = last_trade is not None and last_trade.close_time.astimezone(UTC) >= exit_cutoff.astimezone(UTC)
        checks.append(
            self._check(
                "cooldown_after_exit",
                not recent_exit,
                "Exit cooldown is clear.",
                "Cooldown after recent exit is active.",
                actual=last_trade.close_time.isoformat() if recent_exit and last_trade is not None else None,
                limit=self.settings.runtime_cooldown_after_exit_seconds,
            )
        )

        duplicate_cutoff = signal.signal_at - timedelta(seconds=self.settings.runtime_duplicate_signal_window_seconds)
        duplicate_signals = [
            intent
            for intent in recent_intents
            if intent.created_at.astimezone(UTC) >= duplicate_cutoff.astimezone(UTC)
            and intent.signal_time.astimezone(UTC) < signal.signal_at.astimezone(UTC)
            and intent.strategy_name == signal.strategy_name
            and intent.instrument == signal.instrument
            and intent.direction == signal.direction.value
            and intent.state != TradeIntentState.PROPOSED.value
            and intent.state != TradeIntentState.REJECTED.value
        ]
        duplicate_suppression_enabled = signal.strategy_name not in self.SMOKE_TEST_STRATEGIES
        checks.append(
            self._check(
                "duplicate_signal_suppression",
                (not duplicate_signals) if duplicate_suppression_enabled else True,
                (
                    "No duplicate entry signal in the suppression window."
                    if duplicate_suppression_enabled
                    else "Duplicate signal suppression skipped for smoke-test strategy."
                ),
                "Duplicate entry signal detected in suppression window.",
                actual=len(duplicate_signals) if duplicate_suppression_enabled else "skipped",
                limit=0 if duplicate_suppression_enabled else None,
            )
        )

        burst_cutoff = signal.signal_at - timedelta(seconds=self.settings.runtime_entry_burst_window_seconds)
        concurrent_entries = [
            intent
            for intent in recent_intents
            if intent.created_at.astimezone(UTC) >= burst_cutoff.astimezone(UTC)
            and intent.signal_time.astimezone(UTC) < signal.signal_at.astimezone(UTC)
            and intent.state != TradeIntentState.PROPOSED.value
            and intent.state != TradeIntentState.REJECTED.value
        ]
        burst_limit_enabled = signal.strategy_name not in self.SMOKE_TEST_STRATEGIES
        checks.append(
            self._check(
                "entry_burst_limit",
                (
                    len(concurrent_entries) < self.settings.runtime_entry_burst_limit
                    if burst_limit_enabled
                    else True
                ),
                (
                    "Entry velocity is within the configured burst window."
                    if burst_limit_enabled
                    else "Entry burst limit skipped for smoke-test strategy."
                ),
                "Too many recent entry attempts in the configured burst window.",
                actual=len(concurrent_entries) if burst_limit_enabled else "skipped",
                limit=self.settings.runtime_entry_burst_limit if burst_limit_enabled else None,
            )
        )

        failed_entry_cutoff = signal.signal_at - timedelta(seconds=self.settings.runtime_failed_entry_retry_cooldown_seconds)
        recent_failed_entries = [
            intent
            for intent in recent_intents
            if intent.created_at.astimezone(UTC) >= failed_entry_cutoff.astimezone(UTC)
            and intent.strategy_name == signal.strategy_name
            and intent.instrument == signal.instrument
            and intent.state == TradeIntentState.FAILED.value
            and intent.position_id is None
        ]
        checks.append(
            self._check(
                "failed_entry_retry_cooldown",
                not recent_failed_entries,
                "No recent broker-side entry failures are blocking retries.",
                "Recent broker-side entry failure is in cooldown; retry paused to avoid repeated broker requests.",
                actual=recent_failed_entries[0].created_at.isoformat() if recent_failed_entries else None,
                limit=self.settings.runtime_failed_entry_retry_cooldown_seconds,
            )
        )
        return self._layer_result("pre_trade", checks)

    def _evaluate_portfolio(
        self,
        signal: EntrySignal,
        open_positions: list[Position],
        trades: list[Trade],
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        checks.append(
            self._check(
                "portfolio_open_positions",
                len(open_positions) < self.settings.runtime_max_open_positions,
                "Portfolio open-position count is within limits.",
                "Portfolio max open positions reached.",
                actual=len(open_positions),
                limit=self.settings.runtime_max_open_positions,
            )
        )

        projected_risk = sum(position.risk_percent or 0.0 for position in open_positions) + signal.risk_percent
        checks.append(
            self._check(
                "portfolio_open_risk",
                projected_risk <= self.settings.runtime_max_open_risk_percent,
                "Projected open risk remains within the portfolio cap.",
                "Portfolio open risk cap reached.",
                actual=round(projected_risk, 4),
                limit=self.settings.runtime_max_open_risk_percent,
            )
        )

        projected_notional = round(abs(signal.size * signal.observed_price), 4)
        checks.append(
            self._check(
                "position_notional",
                projected_notional <= self.settings.runtime_max_position_notional,
                "Projected position notional is within limits.",
                "Projected position notional exceeds the configured limit.",
                actual=projected_notional,
                limit=self.settings.runtime_max_position_notional,
            )
        )

        daily_pnl = self._daily_closed_pnl(trades)
        checks.append(
            self._check(
                "daily_loss_limit",
                daily_pnl > -abs(self.settings.runtime_daily_loss_limit),
                "Daily realized PnL is within limits.",
                "Daily loss cap reached.",
                actual=round(daily_pnl, 2),
                limit=-abs(self.settings.runtime_daily_loss_limit),
            )
        )
        return self._layer_result("portfolio", checks)

    def _evaluate_market_quality(self, signal: EntrySignal) -> dict[str, object]:
        checks: list[dict[str, object]] = []

        spread = self._spread(signal)
        spread_limit = round(signal.observed_price * self.settings.runtime_max_spread_percent_of_price, 8)
        spread_ok = spread is None or spread <= spread_limit
        checks.append(
            self._check(
                "spread_gate",
                spread_ok,
                "Observed spread is within the configured threshold.",
                "Observed spread exceeds the configured threshold.",
                actual=round(spread, 8) if spread is not None else None,
                limit=spread_limit,
            )
        )

        last_price_seen_at = runtime_manager.get_last_price_updated_at(signal.instrument)
        price_age_seconds = None
        stale_price = last_price_seen_at is None
        if last_price_seen_at is not None:
            price_age_seconds = max(
                0.0,
                (signal.signal_at.astimezone(UTC) - last_price_seen_at.astimezone(UTC)).total_seconds(),
            )
            stale_price = price_age_seconds > self.settings.runtime_price_stale_after_seconds
        checks.append(
            self._check(
                "stale_price_gate",
                not stale_price,
                "Latest price update is fresh enough for execution.",
                "Latest price update is stale.",
                actual=round(price_age_seconds, 3) if price_age_seconds is not None else None,
                limit=self.settings.runtime_price_stale_after_seconds,
            )
        )

        checks.append(
            self._check(
                "market_status_gate",
                signal.market_status is None or signal.market_status.upper() not in {"CLOSED", "OFFLINE", "SUSPENDED"},
                "Market status permits fresh entries.",
                "Market status does not permit fresh entries.",
                actual=signal.market_status,
            )
        )
        return self._layer_result("market_quality", checks)

    def _evaluate_platform_health(
        self,
        signal: EntrySignal,
        runtimes: list[StrategyRuntimeState],
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        price_error = runtime_manager.get_price_error(signal.instrument)
        checks.append(
            self._check(
                "price_feed_health",
                price_error is None,
                "No active price-feed error for this instrument.",
                "Instrument has an active price-feed error.",
                actual=price_error,
            )
        )

        unhealthy_runtimes = [
            runtime
            for runtime in runtimes
            if runtime.recovery_state in {"RECOVERY_REQUIRED", "ERROR"}
            and runtime_manager.get_engine(runtime.strategy_name, runtime.instrument) is not None
        ]
        checks.append(
            self._check(
                "runtime_recovery_state",
                not unhealthy_runtimes,
                "No runtime is currently flagged as unhealthy.",
                "At least one runtime is flagged as unhealthy.",
                actual=len(unhealthy_runtimes),
                limit=0,
            )
        )
        return self._layer_result("platform_health", checks)

    def _evaluate_kill_switch(
        self,
        signal: EntrySignal,
        trades: list[Trade],
        runtimes: list[StrategyRuntimeState],
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        checks.append(
            self._check(
                "global_entry_kill_switch",
                not self.settings.runtime_global_entry_kill_switch,
                "Global entry kill switch is not active.",
                "Global entry kill switch is active.",
                actual=self.settings.runtime_global_entry_kill_switch,
            )
        )

        unhealthy_count = len(
            [
                runtime
                for runtime in runtimes
                if runtime.recovery_state in {"RECOVERY_REQUIRED", "ERROR"}
                and runtime_manager.get_engine(runtime.strategy_name, runtime.instrument) is not None
            ]
        )
        checks.append(
            self._check(
                "unhealthy_runtime_count",
                unhealthy_count <= self.settings.runtime_max_unhealthy_runtimes,
                "Unhealthy runtime count is within the kill-switch tolerance.",
                "Unhealthy runtime count exceeded the kill-switch tolerance.",
                actual=unhealthy_count,
                limit=self.settings.runtime_max_unhealthy_runtimes,
            )
        )

        daily_pnl = self._daily_closed_pnl(trades)
        checks.append(
            self._check(
                "daily_drawdown_kill_switch",
                daily_pnl > -abs(self.settings.runtime_daily_loss_limit),
                "Daily drawdown kill switch is not active.",
                "Daily drawdown kill switch is active.",
                actual=round(daily_pnl, 2),
                limit=-abs(self.settings.runtime_daily_loss_limit),
            )
        )
        return self._layer_result("kill_switch", checks)

    def _build_summary(
        self,
        *,
        signal: EntrySignal,
        open_positions: list[Position],
        trades: list[Trade],
        runtimes: list[StrategyRuntimeState],
        recent_intents: list[TradeIntent],
        approved: bool,
        rejection_layer: str | None,
    ) -> dict[str, object]:
        daily_pnl = self._daily_closed_pnl(trades)
        open_risk = sum(position.risk_percent or 0.0 for position in open_positions)
        unhealthy_count = len(
            [
                runtime
                for runtime in runtimes
                if runtime.recovery_state in {"RECOVERY_REQUIRED", "ERROR"}
                and runtime_manager.get_engine(runtime.strategy_name, runtime.instrument) is not None
            ]
        )
        return {
            "approved": approved,
            "rejection_layer": rejection_layer,
            "instrument": signal.instrument,
            "strategy_name": signal.strategy_name,
            "direction": signal.direction.value,
            "observed_price": signal.observed_price,
            "projected_notional": round(abs(signal.size * signal.observed_price), 4),
            "spread": round(self._spread(signal), 8) if self._spread(signal) is not None else None,
            "open_positions": len(open_positions),
            "open_risk_percent": round(open_risk, 4),
            "daily_closed_pnl": round(daily_pnl, 2),
            "recent_entry_attempts": len(recent_intents),
            "unhealthy_runtimes": unhealthy_count,
            "market_status": signal.market_status,
            "tradable": signal.tradable,
        }

    def _load_recent_entry_trade_intents(self, signal: EntrySignal) -> list[TradeIntent]:
        if self.session is None:
            return []
        lookback_seconds = max(
            self.settings.runtime_entry_burst_window_seconds,
            self.settings.runtime_failed_entry_retry_cooldown_seconds,
            self.settings.runtime_duplicate_signal_window_seconds,
            self.settings.runtime_cooldown_after_loss_seconds,
            self.settings.runtime_cooldown_after_exit_seconds,
        )
        cutoff = signal.signal_at.astimezone(UTC) - timedelta(seconds=lookback_seconds)
        if self.trade_service is None:
            return []
        return self.trade_service.list_recent_trade_intents(
            signal_time_from=cutoff,
            strategy_name=None,
            instrument=None,
        )

    @staticmethod
    def _latest_closed_trade(trades: list[Trade], signal: EntrySignal) -> Trade | None:
        relevant = [
            trade
            for trade in trades
            if trade.strategy_name == signal.strategy_name and trade.instrument == signal.instrument
        ]
        if not relevant:
            return None
        return max(relevant, key=lambda trade: trade.close_time)

    @staticmethod
    def _check(
        code: str,
        passed: bool,
        success_reason: str,
        failure_reason: str,
        *,
        actual: Any = None,
        limit: Any = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": code,
            "passed": passed,
            "reason": success_reason if passed else failure_reason,
        }
        if actual is not None:
            payload["actual"] = actual
        if limit is not None:
            payload["limit"] = limit
        return payload

    @staticmethod
    def _layer_result(layer: str, checks: list[dict[str, object]]) -> dict[str, object]:
        failed_check = next((check for check in checks if check["passed"] is False), None)
        return {
            "layer": layer,
            "status": "PASSED" if failed_check is None else "REJECTED",
            "passed": failed_check is None,
            "reason": (failed_check or {"reason": f"{layer} checks passed."})["reason"],
            "checks": checks,
        }

    @staticmethod
    def _spread(signal: EntrySignal) -> float | None:
        if signal.bid is None or signal.ask is None:
            return None
        return abs(signal.ask - signal.bid)

    @staticmethod
    def _daily_closed_pnl(trades: list[Trade]) -> float:
        today = datetime.now(UTC).date()
        return sum(
            trade.pnl
            for trade in trades
            if trade.close_time.astimezone(UTC).date() == today
        )
