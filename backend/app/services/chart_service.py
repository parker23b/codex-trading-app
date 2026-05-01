from __future__ import annotations

from app.core.broker_factory import get_broker
from app.core.instrument_catalog import list_market_instruments
from app.models.trade import TradeIntent, TradeIntentState
from app.services.dashboard_service import DashboardService
from app.services.trade_service import TradeService
from app.services.watchlist_service import WatchlistService


class ChartService:
    """Read-only chart projections built from the same aggregated trade/position state."""

    def __init__(self, trade_service: TradeService):
        self.trade_service = trade_service
        self.dashboard_service = DashboardService(trade_service)

    def get_equity_chart(self) -> list[dict[str, float | str]]:
        return self.dashboard_service.build_equity_curve()

    def get_drawdown_chart(self) -> list[dict[str, float | str]]:
        return self.dashboard_service.build_drawdown_series()

    def get_risk_allocation_chart(self) -> dict[str, object]:
        return self.dashboard_service.build_risk_allocation()

    def get_live_instrument_chart(self, instrument: str, *, timeframe: str = "1m") -> dict[str, object]:
        candle_projection = self._load_candles(instrument=instrument, timeframe=timeframe)
        watchlist_service = WatchlistService(self.trade_service.session)
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "candles": candle_projection["candles"],
            "source": candle_projection["source"],
            "data_state": candle_projection["data_state"],
            "reason_detail": candle_projection["reason_detail"],
            "markers": self._candidate_markers(instrument),
            "position_overlays": self._position_overlays(instrument),
            "intent_markers": self._intent_markers(instrument),
            "execution_markers": self._execution_markers(instrument),
            "feed_state": watchlist_service.feed_state_for_instrument(instrument),
        }

    def _load_candles(self, *, instrument: str, timeframe: str) -> dict[str, object]:
        watchlist_service = WatchlistService(self.trade_service.session)
        definition = next((item for item in list_market_instruments() if item.epic == instrument), None)
        if definition is None:
            return {
                "candles": [],
                "source": "UNAVAILABLE",
                "data_state": "UNSUPPORTED",
                "reason_detail": watchlist_service.reason_detail("unsupported_chart_instrument"),
            }

        broker = get_broker()
        if hasattr(broker, "get_historical_candles"):
            try:
                candles = broker.get_historical_candles(
                    instrument,
                    timeframe=timeframe,
                    num_points=180,
                )
                if candles:
                    return {
                        "candles": [self._normalize_candle(candle) for candle in candles],
                        "source": "REST_CANDLES",
                        "data_state": "READY",
                        "reason_detail": None,
                    }
            except Exception:
                return {
                    "candles": [],
                    "source": "UNAVAILABLE",
                    "data_state": "EMPTY",
                    "reason_detail": watchlist_service.reason_detail("broker_candles_unavailable"),
                }

        return {
            "candles": [],
            "source": "UNAVAILABLE",
            "data_state": "EMPTY",
            "reason_detail": watchlist_service.reason_detail("empty_candles"),
        }

    @staticmethod
    def _normalize_candle(candle: dict[str, object]) -> dict[str, object]:
        return {
            **candle,
            "source": "REST_CANDLES" if candle.get("source") not in {"STREAM", "REST_CANDLES", "SNAPSHOT", "FALLBACK", "STALE", "UNAVAILABLE"} else candle.get("source"),
        }

    def _candidate_markers(self, instrument: str) -> list[dict[str, object]]:
        return [
            {
                "id": f"candidate-{intent.id}",
                "time": int(intent.signal_time.timestamp()),
                "price": intent.observed_price,
                "strategy": intent.strategy_name,
                "direction": intent.direction,
                "status": self._candidate_status(intent),
                "reason": intent.decision_reason or intent.decision_reason_code,
                "trade_intent_id": intent.id,
            }
            for intent in self.trade_service.list_trade_intents(limit=200, instrument=instrument)
        ]

    def _intent_markers(self, instrument: str) -> list[dict[str, object]]:
        return [
            {
                "id": f"intent-{intent.id}",
                "time": int(intent.updated_at.timestamp()),
                "price": intent.average_fill_price or intent.observed_price,
                "strategy": intent.strategy_name,
                "direction": intent.direction,
                "state": intent.state,
                "reason": intent.decision_reason or intent.decision_reason_code,
                "trade_intent_id": intent.id,
            }
            for intent in self.trade_service.list_trade_intents(limit=200, instrument=instrument)
        ]

    def _execution_markers(self, instrument: str) -> list[dict[str, object]]:
        return [
            {
                "id": f"execution-{execution.id}",
                "time": int(execution.last_transition_at.timestamp()),
                "price": execution.average_fill_price or execution.requested_price,
                "strategy": execution.strategy_name,
                "phase": execution.phase,
                "status": execution.status,
                "reason": execution.error_message or execution.reason,
                "trade_intent_id": execution.trade_intent_id,
                "execution_id": execution.id,
            }
            for execution in self.trade_service.list_executions(limit=250)
            if execution.instrument == instrument
        ]

    def _position_overlays(self, instrument: str) -> list[dict[str, object]]:
        return [
            {
                "id": f"position-{position.id}",
                "strategy": position.strategy_name,
                "direction": position.direction,
                "open_time": int(position.open_time.timestamp()),
                "open_price": position.open_price,
                "current_price": position.current_price,
                "size": position.size,
                "risk_percent": position.risk_percent,
                "unrealized_pnl": position.unrealized_pnl,
                "broker_reference": position.broker_reference,
            }
            for position in self.trade_service.list_positions()
            if position.instrument == instrument
        ]

    @staticmethod
    def _candidate_status(intent: TradeIntent) -> str:
        if intent.state == TradeIntentState.REJECTED.value:
            reason = str(intent.decision_reason_code or "")
            if "conflict" in reason or "duplicate" in reason or "active" in reason:
                return "blocked_by_conflict"
            return "blocked_by_risk"
        if intent.state in {
            TradeIntentState.SUBMITTED.value,
            TradeIntentState.ACKNOWLEDGED.value,
            TradeIntentState.FILLED.value,
            TradeIntentState.POSITION_OPENED.value,
        }:
            return "promoted_to_trade_intent"
        if intent.state in {TradeIntentState.FAILED.value, TradeIntentState.CANCELLED.value}:
            return "expired"
        return "selected"
