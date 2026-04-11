from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.instrument_catalog import list_instruments
from app.core.ig_broker import IGBrokerError
from app.core.broker_factory import get_broker
from app.core.runtime import runtime_manager
from app.models.trade import Position, Trade
from app.services.trade_service import TradeService


class DashboardService:
    """Aggregates dashboard KPIs, keeping account metrics broker-sourced only."""

    def __init__(self, trade_service: TradeService):
        self.trade_service = trade_service
        self.settings = get_settings()

    def get_dashboard(self) -> dict[str, object]:
        trades = self.trade_service.list_trades()
        positions = self.trade_service.list_positions()
        recent_trades = trades[: self.settings.dashboard_recent_trade_window]
        system_daily_pnl = self._daily_pnl(trades, positions)
        broker_info: dict[str, object] | None = None

        try:
            account_summary = get_broker().get_account_summary()
            broker_info = {
                "accountId": account_summary.account_id,
                "accountType": account_summary.account_type.value,
                "balance": round(account_summary.balance, 2),
                "available": round(account_summary.available, 2),
                "equity": round(account_summary.equity, 2),
                "profitLoss": round(account_summary.profit_loss, 2),
            }
        except IGBrokerError:
            pass

        return {
            "dailyPnl": round(system_daily_pnl, 2),
            "dailyPnlPercent": None,
            "openRisk": round(sum(position.risk_percent or 0.0 for position in positions), 2),
            "winRate": round(self._win_rate(recent_trades), 2),
            "riskReward": round(self._risk_reward(recent_trades), 2),
            "runningStrategies": self._running_strategies(),
            "brokerInfo": broker_info,
        }

    def build_equity_curve(self) -> list[dict[str, float | str]]:
        equity = self.settings.starting_account_value
        peak = equity
        series: list[dict[str, float | str]] = []
        for trade in reversed(self.trade_service.list_trades()):
            equity = round(equity + trade.pnl, 2)
            peak = max(peak, equity)
            drawdown = round(((peak - equity) / peak) * 100, 2) if peak else 0.0
            series.append(
                {
                    "timestamp": trade.close_time.isoformat(),
                    "label": trade.close_time.strftime("%d %b"),
                    "value": equity,
                    "drawdown": drawdown,
                }
            )
        return series

    def build_drawdown_series(self) -> list[dict[str, float | str]]:
        return [
            {"timestamp": point["timestamp"], "label": point["label"], "value": point["drawdown"]}
            for point in self.build_equity_curve()
        ]

    def build_risk_allocation(self) -> dict[str, object]:
        positions = self.trade_service.list_positions()
        long_exposure = sum(
            (position.current_price or position.open_price) * position.size
            for position in positions
            if position.direction == "BUY"
        )
        short_exposure = sum(
            (position.current_price or position.open_price) * position.size
            for position in positions
            if position.direction == "SELL"
        )
        total_exposure = max(long_exposure + short_exposure, 1.0)

        return {
            "longExposure": round(long_exposure, 2),
            "shortExposure": round(short_exposure, 2),
            "allocations": [
                {
                    "instrument": position.instrument,
                    "allocation": round(
                        (((position.current_price or position.open_price) * position.size) / total_exposure) * 100,
                        2,
                    ),
                    "direction": position.direction,
                }
                for position in positions
            ],
        }

    def _daily_pnl(self, trades: Sequence[Trade], positions: Sequence[Position]) -> float:
        today = datetime.now(UTC).date()
        closed_today = sum(trade.pnl for trade in trades if trade.close_time.astimezone(UTC).date() == today)
        open_today = sum(
            position.unrealized_pnl or 0.0 for position in positions if position.open_time.astimezone(UTC).date() == today
        )
        return closed_today + open_today

    @staticmethod
    def _win_rate(trades: Sequence[Trade]) -> float:
        if not trades:
            return 0.0
        wins = len([trade for trade in trades if trade.pnl > 0])
        return (wins / len(trades)) * 100

    @staticmethod
    def _risk_reward(trades: Sequence[Trade]) -> float:
        if not trades:
            return 0.0
        wins = [trade.pnl for trade in trades if trade.pnl > 0]
        losses = [abs(trade.pnl) for trade in trades if trade.pnl < 0]
        average_win = sum(wins) / len(wins) if wins else 0.0
        average_loss = sum(losses) / len(losses) if losses else 0.0
        if average_win == 0.0:
            return 0.0
        if average_loss == 0.0:
            return average_win
        return average_win / average_loss

    @staticmethod
    def _running_strategies() -> list[dict[str, object]]:
        from app.services.ig_streaming_service import get_ig_streaming_service

        instruments = {item["epic"]: item for item in list_instruments()}
        rows: list[dict[str, object]] = []
        for (_, instrument), engine in runtime_manager.engines.items():
            if not engine.active:
                continue
            last_price = get_ig_streaming_service().get_last_price(instrument)
            if last_price is None:
                last_price = runtime_manager.get_last_price(instrument)
            if last_price is None and engine.current_position is not None:
                last_price = engine.current_position.current_price
            if last_price is None:
                try:
                    last_price = engine.broker.get_latest_price(instrument)
                except IGBrokerError:
                    last_price = None
            rows.append(
                {
                    "name": engine.strategy.name,
                    "instrument": instrument,
                    "runtimeKey": f"{engine.strategy.name}:{instrument}",
                    "brokerReference": engine.current_position.broker_reference if engine.current_position else None,
                    "instrumentLabel": instruments.get(instrument, {}).get("label", instrument),
                    "lastPrice": last_price,
                    "hasOpenPosition": engine.current_position is not None,
                }
            )
        return rows
