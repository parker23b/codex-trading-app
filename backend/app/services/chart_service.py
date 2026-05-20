from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from app.core.risk_truth import RiskTruthConfidence
from app.core.broker_factory import get_broker
from app.core.instrument_catalog import list_market_instruments
from app.models.trade import Position, TradeIntent, TradeIntentState, utc_now
from app.services.allocation_read_service import AllocationReadService
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
        exposure = AllocationReadService(
            self.trade_service.session
        ).get_exposure_summary()
        reserved_states = {
            TradeIntentState.APPROVED.value,
            TradeIntentState.SUBMITTED.value,
            TradeIntentState.ACKNOWLEDGED.value,
            TradeIntentState.PARTIALLY_FILLED.value,
            TradeIntentState.FILLED.value,
        }
        intents = [
            intent
            for intent in self.trade_service.list_trade_intents(
                limit=1000, states=reserved_states
            )
            if intent.position_id is None
            or AllocationReadService._partial_fill_residual_ratio(intent) > 0.0
        ]
        positions = self.trade_service.list_all_open_positions()
        return self._build_risk_allocation_chart(
            exposure_summary=exposure,
            positions=positions,
            intents=intents,
            generated_at=utc_now(),
        )

    def get_live_instrument_chart(
        self, instrument: str, *, timeframe: str = "1m"
    ) -> dict[str, object]:
        candle_projection = self._load_candles(
            instrument=instrument, timeframe=timeframe
        )
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
        definition = next(
            (item for item in list_market_instruments() if item.epic == instrument),
            None,
        )
        if definition is None:
            return {
                "candles": [],
                "source": "UNAVAILABLE",
                "data_state": "UNSUPPORTED",
                "reason_detail": watchlist_service.reason_detail(
                    "unsupported_chart_instrument"
                ),
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
                        "candles": [
                            self._normalize_candle(candle) for candle in candles
                        ],
                        "source": "REST_CANDLES",
                        "data_state": "READY",
                        "reason_detail": None,
                    }
            except Exception:
                return {
                    "candles": [],
                    "source": "UNAVAILABLE",
                    "data_state": "EMPTY",
                    "reason_detail": watchlist_service.reason_detail(
                        "broker_candles_unavailable"
                    ),
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
            "source": "REST_CANDLES"
            if candle.get("source")
            not in {
                "STREAM",
                "REST_CANDLES",
                "SNAPSHOT",
                "FALLBACK",
                "STALE",
                "UNAVAILABLE",
            }
            else candle.get("source"),
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
            for intent in self.trade_service.list_trade_intents(
                limit=200, instrument=instrument
            )
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
            for intent in self.trade_service.list_trade_intents(
                limit=200, instrument=instrument
            )
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
        if intent.state in {
            TradeIntentState.FAILED.value,
            TradeIntentState.CANCELLED.value,
        }:
            return "expired"
        return "selected"

    @classmethod
    def _build_risk_allocation_chart(
        cls,
        *,
        exposure_summary: dict[str, object],
        positions: list[Position],
        intents: list[TradeIntent],
        generated_at: datetime,
    ) -> dict[str, object]:
        exposure_bars = {
            str(bucket["name"]): bucket
            for bucket in exposure_summary.get("by_instrument", [])
            if isinstance(bucket, dict)
        }
        instrument_contexts: dict[str, dict[str, object]] = defaultdict(
            cls._empty_risk_context
        )
        overall_context = cls._empty_risk_context()
        for position in positions:
            cls._add_position_truth(instrument_contexts[position.instrument], position)
            cls._add_position_truth(overall_context, position)
        for intent in intents:
            cls._add_intent_truth(instrument_contexts[intent.instrument], intent)
            cls._add_intent_truth(overall_context, intent)

        instruments = sorted(set(exposure_bars) | set(instrument_contexts))
        bars = [
            cls._build_risk_allocation_bar(
                instrument=instrument,
                bucket=exposure_bars.get(instrument),
                context=instrument_contexts[instrument],
            )
            for instrument in instruments
        ]
        chartable_bucket_count = sum(
            1 for bar in bars if bar["data_status"] != "UNAVAILABLE"
        )
        unavailable_bucket_count = sum(
            1 for bar in bars if bar["data_status"] == "UNAVAILABLE"
        )
        overall_status = cls._resolve_data_status(
            has_unknown_risk=bool(overall_context["has_unknown_risk"]),
            has_degraded_risk=bool(overall_context["has_degraded_risk"]),
            has_provisional_risk=bool(overall_context["has_provisional_risk"]),
            has_simulated_risk=bool(overall_context["has_simulated_risk"]),
            chartable=chartable_bucket_count > 0,
            active_count=int(overall_context["active_count"]),
        )
        totals = exposure_summary.get("totals", {})
        has_unavailable_only_truth = (
            overall_status == "UNAVAILABLE" and int(overall_context["active_count"]) > 0
        )
        summary = {
            "reserved_risk_percent": None
            if has_unavailable_only_truth
            else totals.get("reserved_risk_percent"),
            "live_risk_percent": None
            if has_unavailable_only_truth
            else totals.get("live_risk_percent"),
            "provisional_live_risk_percent": None
            if has_unavailable_only_truth
            else totals.get("provisional_live_risk_percent"),
            "total_active_risk_percent": None
            if has_unavailable_only_truth
            else cls._sum_optional(
                totals.get("reserved_risk_percent"),
                totals.get("live_risk_percent"),
            ),
            "remaining_portfolio_risk_percent": None
            if has_unavailable_only_truth
            else totals.get("remaining_portfolio_risk_percent"),
            "reserved_intent_count": int(totals.get("reserved_intent_count") or 0),
            "open_position_count": int(totals.get("open_position_count") or 0),
            "chartable_bucket_count": chartable_bucket_count,
            "unavailable_bucket_count": unavailable_bucket_count,
            "has_provisional_risk": bool(overall_context["has_provisional_risk"]),
            "has_simulated_risk": bool(overall_context["has_simulated_risk"]),
            "has_unknown_risk": bool(overall_context["has_unknown_risk"]),
            "has_degraded_risk": bool(overall_context["has_degraded_risk"]),
            "risk_truth_confidence_mix": cls._serialize_confidence_mix(
                overall_context["truth_counts"]
            ),
            "reasons": sorted(overall_context["reasons"]),
        }
        return {
            "generated_at": generated_at,
            "data_status": overall_status,
            "source": "ALLOCATION_EXPOSURE_SUMMARY_PLUS_POSITION_INTENT_TRUTH",
            "chart_mode": "ACTIVE_RISK_BY_INSTRUMENT",
            "summary": summary,
            "bars": sorted(
                bars,
                key=lambda item: float(item["total_risk_percent"] or -1.0),
                reverse=True,
            ),
            "reasons": sorted(overall_context["reasons"]),
            "notes": {
                "numeric_basis": "allocation_exposure_summary_by_instrument",
                "provenance_basis": "open_positions_and_reserved_trade_intents",
                "unavailable_behavior": "unknown_or_degraded_risk_without_chartable_values_returns_null_metrics_not_zero_defaults",
                "partial_behavior": "provisional_simulated_and_intent_only_risk_remain_partial_not_exact",
            },
        }

    @classmethod
    def _build_risk_allocation_bar(
        cls,
        *,
        instrument: str,
        bucket: dict[str, object] | None,
        context: dict[str, object],
    ) -> dict[str, object]:
        active_count = int(context["active_count"])
        reserved_risk_percent = cls._as_optional_float(
            bucket.get("reserved_risk_percent") if bucket else None
        )
        live_risk_percent = cls._as_optional_float(
            bucket.get("live_risk_percent") if bucket else None
        )
        provisional_live_risk_percent = cls._as_optional_float(
            bucket.get("provisional_live_risk_percent") if bucket else None
        )
        if (
            provisional_live_risk_percent is None
            and int(context["provisional_position_count"]) > 0
            and int(context["provisional_position_count"])
            == int(context["open_position_count"])
        ):
            provisional_live_risk_percent = live_risk_percent
        total_risk_percent = cls._as_optional_float(
            bucket.get("total_risk_percent") if bucket else None
        )
        chartable = any(
            (value or 0.0) > 0.0
            for value in (
                reserved_risk_percent,
                live_risk_percent,
                provisional_live_risk_percent,
                total_risk_percent,
            )
        )
        status = cls._resolve_data_status(
            has_unknown_risk=bool(context["has_unknown_risk"]),
            has_degraded_risk=bool(context["has_degraded_risk"]),
            has_provisional_risk=bool(context["has_provisional_risk"]),
            has_simulated_risk=bool(context["has_simulated_risk"]),
            chartable=chartable,
            active_count=active_count,
        )
        if status == "UNAVAILABLE" and active_count > 0:
            reserved_risk_percent = None
            live_risk_percent = None
            provisional_live_risk_percent = None
            total_risk_percent = None
            utilization_percent = None
        else:
            utilization_percent = cls._as_optional_float(
                bucket.get("utilization_percent") if bucket else None
            )
        return {
            "instrument": instrument,
            "reserved_risk_percent": reserved_risk_percent,
            "live_risk_percent": live_risk_percent,
            "provisional_live_risk_percent": provisional_live_risk_percent,
            "total_risk_percent": total_risk_percent,
            "utilization_percent": utilization_percent,
            "budget_limit_percent": float(
                (bucket or {}).get("budget_limit_percent") or 0.0
            ),
            "reserved_intent_count": int(context["reserved_intent_count"]),
            "open_position_count": int(context["open_position_count"]),
            "data_status": status,
            "has_provisional_risk": bool(context["has_provisional_risk"]),
            "has_simulated_risk": bool(context["has_simulated_risk"]),
            "has_unknown_risk": bool(context["has_unknown_risk"]),
            "has_degraded_risk": bool(context["has_degraded_risk"]),
            "risk_basis": sorted(
                set((bucket or {}).get("risk_basis") or []) | set(context["risk_basis"])
            ),
            "risk_truth_confidence_mix": cls._serialize_confidence_mix(
                context["truth_counts"]
            ),
            "reasons": sorted(context["reasons"]),
        }

    @staticmethod
    def _empty_risk_context() -> dict[str, object]:
        return {
            "truth_counts": Counter(),
            "reasons": set(),
            "risk_basis": set(),
            "reserved_intent_count": 0,
            "open_position_count": 0,
            "active_count": 0,
            "has_provisional_risk": False,
            "has_simulated_risk": False,
            "has_unknown_risk": False,
            "has_degraded_risk": False,
            "provisional_position_count": 0,
        }

    @classmethod
    def _add_position_truth(
        cls, context: dict[str, object], position: Position
    ) -> None:
        confidence = str(
            position.risk_truth_confidence or RiskTruthConfidence.UNKNOWN.value
        )
        context["truth_counts"][confidence] += 1
        context["open_position_count"] += 1
        context["active_count"] += 1
        if position.entry_risk_amount is not None:
            context["risk_basis"].add("position_entry_risk_amount")
        if position.risk_percent is not None:
            context["risk_basis"].add("position_risk_percent")
        if confidence == RiskTruthConfidence.PARTIAL_FILL_PROVISIONAL.value:
            context["has_provisional_risk"] = True
            context["provisional_position_count"] += 1
            context["reasons"].add("partial_fill_provisional_live_risk")
        if (
            confidence == RiskTruthConfidence.SIMULATED_LOCAL_FILL.value
            or str(position.broker_sync_status or "")
            == RiskTruthConfidence.SIMULATED_LOCAL_FILL.value
        ):
            context["has_simulated_risk"] = True
            context["reasons"].add("simulated_local_live_risk")
        if confidence == RiskTruthConfidence.INCOMPLETE_DEGRADED.value:
            context["has_degraded_risk"] = True
            context["reasons"].add("degraded_live_position_risk_truth")
        if confidence == RiskTruthConfidence.UNKNOWN.value or (
            position.risk_percent is None and position.entry_risk_amount is None
        ):
            context["has_unknown_risk"] = True
            context["reasons"].add("unknown_live_position_risk_truth")

    @classmethod
    def _add_intent_truth(cls, context: dict[str, object], intent: TradeIntent) -> None:
        confidence = str(
            intent.risk_truth_confidence or RiskTruthConfidence.UNKNOWN.value
        )
        context["truth_counts"][confidence] += 1
        context["reserved_intent_count"] += 1
        context["active_count"] += 1
        context["risk_basis"].add("reserved_trade_intent")
        if confidence == RiskTruthConfidence.PARTIAL_FILL_PROVISIONAL.value:
            context["has_provisional_risk"] = True
            context["reasons"].add("partial_fill_residual_reserved_risk")
        if confidence == RiskTruthConfidence.ALLOCATION_INTENT_ONLY.value:
            context["has_provisional_risk"] = True
            context["reasons"].add("reserved_intent_only_risk")
        if confidence == RiskTruthConfidence.SUBMITTED_EXECUTABLE_ESTIMATE.value:
            context["has_provisional_risk"] = True
            context["reasons"].add("submitted_executable_estimate_risk")
        if confidence == RiskTruthConfidence.INCOMPLETE_DEGRADED.value:
            context["has_degraded_risk"] = True
            context["reasons"].add("degraded_reserved_intent_risk_truth")
        if confidence == RiskTruthConfidence.UNKNOWN.value:
            context["has_unknown_risk"] = True
            context["reasons"].add("unknown_reserved_intent_risk_truth")

    @staticmethod
    def _serialize_confidence_mix(
        truth_counts: Counter[str],
    ) -> list[dict[str, object]]:
        return [
            {"confidence": confidence, "count": count}
            for confidence, count in sorted(
                truth_counts.items(), key=lambda item: item[0]
            )
        ]

    @staticmethod
    def _as_optional_float(value: object) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _sum_optional(left: object, right: object) -> float | None:
        if left is None and right is None:
            return None
        return float(left or 0.0) + float(right or 0.0)

    @staticmethod
    def _resolve_data_status(
        *,
        has_unknown_risk: bool,
        has_degraded_risk: bool,
        has_provisional_risk: bool,
        has_simulated_risk: bool,
        chartable: bool,
        active_count: int,
    ) -> str:
        if (
            active_count > 0
            and not chartable
            and (has_unknown_risk or has_degraded_risk)
        ):
            return "UNAVAILABLE"
        if has_unknown_risk or has_degraded_risk:
            return "DEGRADED"
        if has_provisional_risk or has_simulated_risk:
            return "PARTIAL"
        return "READY"
