from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlmodel import Session

from app.core.config import get_settings
from app.core.identifier_policy import project_identifier
from app.models.trade import (
    AllocationCycle,
    Execution,
    Position,
    Trade,
    TradeIntent,
    utc_now,
)
from app.services.trade_service import TradeService


class AllocationReadService:
    def __init__(self, session: Session):
        self.session = session
        self.trade_service = TradeService(session)

    def list_recent_cycles(self, *, limit: int = 50) -> list[dict[str, object]]:
        return [
            self._serialize_cycle(cycle)
            for cycle in self.trade_service.list_allocation_cycles(limit=limit)
        ]

    def get_cycle(self, cycle_id: str) -> dict[str, object] | None:
        cycle = self.trade_service.get_allocation_cycle(cycle_id)
        if cycle is None:
            return None
        intents = self.trade_service.list_trade_intents(
            limit=500, allocation_cycle_id=cycle_id
        )
        return {
            **self._serialize_cycle(cycle),
            "intents": [self._serialize_intent(intent) for intent in intents],
        }

    def list_intents(
        self,
        *,
        limit: int = 100,
        cycle_id: str | None = None,
        strategy_name: str | None = None,
        instrument: str | None = None,
        states: list[str] | None = None,
    ) -> list[dict[str, object]]:
        intents = self.trade_service.list_trade_intents(
            limit=limit,
            allocation_cycle_id=cycle_id,
            strategy_name=strategy_name,
            instrument=instrument,
            states=states,
        )
        return [self._serialize_intent(intent) for intent in intents]

    def get_intent(self, trade_intent_id: int) -> dict[str, object] | None:
        intent = self.trade_service.get_trade_intent(trade_intent_id)
        if intent is None:
            return None
        return self._serialize_intent(intent)

    def get_drift_summary(
        self, *, limit: int = 100, window_minutes: int | None = None
    ) -> dict[str, object]:
        settings = get_settings()
        since = None
        if window_minutes is not None:
            since = utc_now() - timedelta(minutes=window_minutes)
        intents = self.trade_service.list_trade_intents(
            limit=max(limit, 250), date_from=since
        )
        drifted: list[dict[str, object]] = []
        by_strategy: defaultdict[str, list[float]] = defaultdict(list)
        by_family: defaultdict[str, list[float]] = defaultdict(list)
        by_instrument: defaultdict[str, list[float]] = defaultdict(list)
        for intent in intents:
            view = self._serialize_intent(intent)
            drift_metrics = (view.get("risk_reconciliation") or {}).get(
                "drift_metrics"
            ) or {}
            max_drift = self._max_percent_drift(drift_metrics)
            if max_drift is None:
                continue
            if max_drift >= settings.allocation_drift_warning_percent:
                drifted.append(
                    {
                        "trade_intent_id": view["id"],
                        "strategy_name": view["strategy_name"],
                        "family_name": view["family_name"],
                        "instrument": view["instrument"],
                        "state": view["state"],
                        "max_percent_drift": round(max_drift, 6),
                        "drift_metrics": drift_metrics,
                        "updated_at": view["updated_at"],
                    }
                )
                by_strategy[str(view["strategy_name"])].append(max_drift)
                by_family[str(view.get("family_name") or "UNASSIGNED")].append(
                    max_drift
                )
                by_instrument[str(view["instrument"])].append(max_drift)
        drifted.sort(key=lambda item: float(item["max_percent_drift"]), reverse=True)
        return {
            "window_minutes": window_minutes
            or settings.allocation_alert_window_minutes,
            "drift_warning_percent": settings.allocation_drift_warning_percent,
            "drift_critical_percent": settings.allocation_drift_critical_percent,
            "material_drift_count": len(drifted),
            "worst_intents": drifted[:limit],
            "by_strategy": self._serialize_drift_buckets(by_strategy),
            "by_family": self._serialize_drift_buckets(by_family),
            "by_instrument": self._serialize_drift_buckets(by_instrument),
        }

    def list_alerts(
        self, *, limit: int = 50, window_minutes: int | None = None
    ) -> list[dict[str, object]]:
        settings = get_settings()
        effective_window = window_minutes or settings.allocation_alert_window_minutes
        since = utc_now() - timedelta(minutes=effective_window)
        cycles = [
            cycle
            for cycle in self.trade_service.list_allocation_cycles(limit=500)
            if self._comparable_datetime(cycle.completed_at)
            >= self._comparable_datetime(since)
        ]
        intents = self.trade_service.list_trade_intents(limit=1000, date_from=since)
        alerts: list[dict[str, object]] = []

        degraded_cycles = [
            cycle for cycle in cycles if bool((cycle.details or {}).get("degraded"))
        ]
        if degraded_cycles:
            alerts.append(
                self._alert(
                    alert_type="degraded_allocation_cycles",
                    severity="warning" if len(degraded_cycles) == 1 else "error",
                    title="Degraded allocation cycles detected",
                    message="Recent allocation cycles ran with degraded sizing conditions.",
                    count=len(degraded_cycles),
                    cycle_ids=[cycle.cycle_id for cycle in degraded_cycles],
                    timestamps=[cycle.completed_at for cycle in degraded_cycles],
                )
            )

        approximate_live_blocks = [
            intent
            for intent in intents
            if (((intent.details or {}).get("allocation") or {}).get("notes") or [])
            and (
                ((intent.details or {}).get("allocation") or {}).get("sizing_precision")
                == "APPROXIMATE"
            )
            and intent.decision_reason_code == "allocation_blocked"
        ]
        if approximate_live_blocks:
            alerts.append(
                self._alert(
                    alert_type="approximate_sizing_blocked_live",
                    severity="error",
                    title="Approximate live sizing blocked",
                    message="Live allocation blocked candidates because only approximate sizing was available.",
                    count=len(approximate_live_blocks),
                    intent_ids=[
                        intent.id
                        for intent in approximate_live_blocks
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in approximate_live_blocks
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[
                        intent.updated_at for intent in approximate_live_blocks
                    ],
                )
            )

        revalidation_failures = [
            intent
            for intent in intents
            if intent.decision_reason_code == "execution_revalidation_failed"
        ]
        if (
            len(revalidation_failures)
            >= settings.allocation_alert_revalidation_failure_threshold
        ):
            alerts.append(
                self._alert(
                    alert_type="repeated_execution_revalidation_failures",
                    severity="error",
                    title="Repeated execution revalidation failures",
                    message="Execution-time broker revalidation changed or blocked approved sizes repeatedly.",
                    count=len(revalidation_failures),
                    intent_ids=[
                        intent.id
                        for intent in revalidation_failures
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in revalidation_failures
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[intent.updated_at for intent in revalidation_failures],
                    execution_ids=[
                        execution.id
                        for intent in revalidation_failures
                        for execution in self.trade_service.list_executions_for_trade_intent(
                            intent.id or 0
                        )[:1]
                        if execution.id is not None
                    ],
                )
            )

        broker_submission_failures = [
            intent
            for intent in intents
            if intent.decision_reason_code == "broker_submission_failed"
        ]
        if (
            len(broker_submission_failures)
            >= settings.allocation_alert_broker_submission_failure_threshold
        ):
            alerts.append(
                self._alert(
                    alert_type="repeated_broker_submission_failures",
                    severity="error",
                    title="Repeated broker submission failures",
                    message="Recent approved trades failed during broker order submission.",
                    count=len(broker_submission_failures),
                    intent_ids=[
                        intent.id
                        for intent in broker_submission_failures
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in broker_submission_failures
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[
                        intent.updated_at for intent in broker_submission_failures
                    ],
                    execution_ids=[
                        execution.id
                        for intent in broker_submission_failures
                        for execution in self.trade_service.list_executions_for_trade_intent(
                            intent.id or 0
                        )[:1]
                        if execution.id is not None
                    ],
                )
            )

        below_min_rejections = [
            intent
            for intent in intents
            if intent.decision_reason_code == "below_min_size"
        ]
        if (
            len(below_min_rejections)
            >= settings.allocation_alert_under_minimum_rejection_threshold
        ):
            alerts.append(
                self._alert(
                    alert_type="under_minimum_trade_rejections",
                    severity="warning",
                    title="Repeated under-minimum trade rejections",
                    message="Multiple candidates were rejected because broker-valid size fell below minimum trade size.",
                    count=len(below_min_rejections),
                    intent_ids=[
                        intent.id
                        for intent in below_min_rejections
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in below_min_rejections
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[intent.updated_at for intent in below_min_rejections],
                )
            )

        hard_risk_blocks = [
            intent
            for intent in intents
            if bool(
                (
                    ((intent.details or {}).get("allocation_outcome") or {}).get(
                        "hard_risk_blocked"
                    )
                )
            )
        ]
        if len(hard_risk_blocks) >= settings.allocation_alert_hard_risk_block_threshold:
            alerts.append(
                self._alert(
                    alert_type="repeated_hard_risk_blocks",
                    severity="warning",
                    title="Repeated hard-risk overlay blocks",
                    message="Multiple allocator-approved candidates were later blocked by hard risk overlays.",
                    count=len(hard_risk_blocks),
                    intent_ids=[
                        intent.id
                        for intent in hard_risk_blocks
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in hard_risk_blocks
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[intent.updated_at for intent in hard_risk_blocks],
                )
            )

        metadata_failures = [
            intent
            for intent in intents
            if (((intent.details or {}).get("allocation") or {}).get("notes") or [])
            and intent.decision_reason_code == "allocation_blocked"
            and (
                ((intent.details or {}).get("allocation") or {}).get("binding_budget")
                is None
            )
            and (
                ((intent.details or {}).get("allocation") or {}).get("sizing_precision")
                in {None, "UNSUPPORTED"}
            )
        ]
        if metadata_failures:
            alerts.append(
                self._alert(
                    alert_type="missing_broker_sizing_metadata",
                    severity="error",
                    title="Missing broker sizing metadata",
                    message="Allocation failed closed because broker sizing metadata or coherent risk sizing was unavailable.",
                    count=len(metadata_failures),
                    intent_ids=[
                        intent.id
                        for intent in metadata_failures
                        if intent.id is not None
                    ],
                    cycle_ids=list(
                        {
                            intent.allocation_cycle_id
                            for intent in metadata_failures
                            if intent.allocation_cycle_id
                        }
                    ),
                    timestamps=[intent.updated_at for intent in metadata_failures],
                )
            )

        drift_summary = self.get_drift_summary(
            limit=limit, window_minutes=effective_window
        )
        if drift_summary["material_drift_count"]:
            alerts.append(
                self._alert(
                    alert_type="material_execution_drift",
                    severity=(
                        "error"
                        if any(
                            float(item["max_percent_drift"])
                            >= settings.allocation_drift_critical_percent
                            for item in drift_summary["worst_intents"]
                        )
                        else "warning"
                    ),
                    title="Material allocation-to-execution drift detected",
                    message="Execution drift exceeded configured tolerance on recent trades.",
                    count=int(drift_summary["material_drift_count"]),
                    intent_ids=[
                        int(item["trade_intent_id"])
                        for item in drift_summary["worst_intents"][:limit]
                    ],
                    timestamps=[
                        item["updated_at"]
                        for item in drift_summary["worst_intents"][:limit]
                    ],
                    execution_ids=[
                        execution.id
                        for item in drift_summary["worst_intents"][:limit]
                        for execution in self.trade_service.list_executions_for_trade_intent(
                            int(item["trade_intent_id"])
                        )[:1]
                        if execution.id is not None
                    ],
                    details={"drift_summary": drift_summary},
                )
            )

        incomplete_fill_truth = [
            view
            for view in [self._serialize_intent(intent) for intent in intents]
            if bool(
                ((view.get("risk_reconciliation") or {}).get("flags") or {}).get(
                    "incomplete_fill_data"
                )
            )
            or bool(
                ((view.get("risk_reconciliation") or {}).get("flags") or {}).get(
                    "partial_fill_provisional"
                )
            )
        ]
        if incomplete_fill_truth:
            alerts.append(
                self._alert(
                    alert_type="incomplete_fill_truth",
                    severity="warning",
                    title="Incomplete or provisional fill truth detected",
                    message="Recent live or opening positions still rely on incomplete or provisional fill-derived risk truth.",
                    count=len(incomplete_fill_truth),
                    intent_ids=[
                        int(view["id"])
                        for view in incomplete_fill_truth
                        if view.get("id") is not None
                    ],
                    cycle_ids=[
                        str(view["allocation_cycle_id"])
                        for view in incomplete_fill_truth
                        if view.get("allocation_cycle_id")
                    ],
                    execution_ids=[
                        int(view["latest_execution"]["id"])
                        for view in incomplete_fill_truth
                        if isinstance(view.get("latest_execution"), dict)
                        and view["latest_execution"].get("id") is not None
                    ],
                    timestamps=[
                        view["updated_at"]
                        for view in incomplete_fill_truth
                        if view.get("updated_at") is not None
                    ],
                )
            )

        exposure_summary = self.get_exposure_summary()
        for hotspot in exposure_summary["hotspots"]:
            alerts.append(
                self._alert(
                    alert_type="concentration_hotspot",
                    severity="warning"
                    if float(hotspot["utilization_percent"]) < 100.0
                    else "error",
                    title="Concentration hotspot detected",
                    message=f"{hotspot['bucket_type']} exposure is near or above configured budget.",
                    count=1,
                    timestamps=[],
                    details=hotspot,
                )
            )

        alerts.sort(
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}.get(str(item["severity"]), 3),
                -int(item["count"]),
            )
        )
        return alerts[:limit]

    def get_exposure_summary(self) -> dict[str, object]:
        settings = get_settings()
        positions = self.trade_service.list_all_open_positions()
        reserved_states = {
            "APPROVED",
            "SUBMITTED",
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
            "FILLED",
        }
        intents = [
            intent
            for intent in self.trade_service.list_trade_intents(
                limit=1000, states=reserved_states
            )
            if intent.position_id is None
            or self._partial_fill_residual_ratio(intent) > 0.0
        ]
        summary = {
            "totals": {
                "reserved_risk_percent": 0.0,
                "live_risk_percent": 0.0,
                "provisional_live_risk_percent": 0.0,
                "reserved_risk_amount": 0.0,
                "live_risk_amount": 0.0,
                "provisional_live_risk_amount": 0.0,
                "reserved_intent_count": len(intents),
                "open_position_count": len(positions),
            },
            "by_strategy": defaultdict(
                lambda: self._empty_bucket(
                    "strategy", settings.allocation_max_risk_per_strategy_percent
                )
            ),
            "by_family": defaultdict(
                lambda: self._empty_bucket(
                    "family", settings.allocation_max_risk_per_family_percent
                )
            ),
            "by_instrument": defaultdict(
                lambda: self._empty_bucket(
                    "instrument", settings.allocation_max_risk_per_instrument_percent
                )
            ),
            "by_currency": defaultdict(
                lambda: self._empty_bucket(
                    "currency", settings.allocation_max_risk_per_currency_percent
                )
            ),
            "currency_directional": defaultdict(self._empty_currency_direction_bucket),
        }

        for intent in intents:
            risk_percent, risk_amount, basis = self._intent_risk(intent)
            self._add_exposure(
                summary=summary,
                key_type="reserved",
                strategy_name=intent.strategy_name,
                family_name=intent.family_name or "UNASSIGNED",
                instrument=intent.instrument,
                currencies=self._currency_buckets(
                    intent.instrument, intent.details or {}
                ),
                direction=intent.direction,
                risk_percent=risk_percent,
                risk_amount=risk_amount,
                basis=basis,
            )
        for position in positions:
            truth_confidence = str(position.risk_truth_confidence or "")
            is_provisional = truth_confidence == "PARTIAL_FILL_PROVISIONAL"
            self._add_exposure(
                summary=summary,
                key_type="live",
                strategy_name=position.strategy_name,
                family_name=position.family_name or "UNASSIGNED",
                instrument=position.instrument,
                currencies=self._currency_buckets(position.instrument, {}),
                direction=position.direction,
                risk_percent=float(position.risk_percent or 0.0),
                risk_amount=float(position.entry_risk_amount or 0.0),
                basis="live_position_entry_risk"
                if position.entry_risk_amount is not None
                else "live_position_estimated",
                provisional=is_provisional,
            )

        hotspots: list[dict[str, object]] = []
        for bucket_type in ("by_strategy", "by_family", "by_instrument", "by_currency"):
            for name, bucket in summary[bucket_type].items():
                total_risk = (
                    bucket["reserved_risk_percent"] + bucket["live_risk_percent"]
                )
                budget = bucket["budget_limit_percent"]
                utilization = (
                    (total_risk / budget * 100.0) if budget and budget > 0 else None
                )
                bucket["total_risk_percent"] = round(total_risk, 6)
                bucket["utilization_percent"] = (
                    round(utilization, 6) if utilization is not None else None
                )
                bucket["remaining_risk_percent"] = round(
                    max(float(budget or 0.0) - total_risk, 0.0), 6
                )
                bucket["risk_basis"] = sorted(bucket["risk_basis"])
                if (
                    utilization is not None
                    and utilization
                    >= settings.allocation_alert_concentration_warning_utilization_percent
                ):
                    hotspots.append(
                        {
                            "bucket_type": bucket["bucket_type"],
                            "name": name,
                            "total_risk_percent": bucket["total_risk_percent"],
                            "budget_limit_percent": budget,
                            "utilization_percent": bucket["utilization_percent"],
                            "risk_basis": bucket["risk_basis"],
                            "bucket_mode": "gross_proxy"
                            if bucket_type == "by_currency"
                            else "risk_budget",
                        }
                    )
        for currency, bucket in summary["currency_directional"].items():
            gross_total = (
                bucket["reserved_long_risk_percent"]
                + bucket["reserved_short_risk_percent"]
                + bucket["live_long_risk_percent"]
                + bucket["live_short_risk_percent"]
            )
            net_total = (
                bucket["reserved_long_risk_percent"] + bucket["live_long_risk_percent"]
            ) - (
                bucket["reserved_short_risk_percent"]
                + bucket["live_short_risk_percent"]
            )
            bucket["gross_risk_percent"] = round(gross_total, 6)
            bucket["net_risk_percent"] = round(net_total, 6)
            bucket["gross_utilization_percent"] = round(
                (gross_total / settings.allocation_max_risk_per_currency_percent)
                * 100.0,
                6,
            )
            bucket["net_bias"] = (
                "LONG" if net_total > 0 else "SHORT" if net_total < 0 else "FLAT"
            )
            bucket["risk_basis"] = sorted(bucket["risk_basis"])
            if (
                bucket["gross_utilization_percent"]
                >= settings.allocation_alert_concentration_warning_utilization_percent
            ):
                hotspots.append(
                    {
                        "bucket_type": "currency_directional",
                        "name": currency,
                        "total_risk_percent": bucket["gross_risk_percent"],
                        "budget_limit_percent": settings.allocation_max_risk_per_currency_percent,
                        "utilization_percent": bucket["gross_utilization_percent"],
                        "risk_basis": bucket["risk_basis"],
                        "bucket_mode": "directional_net_approximation",
                        "net_bias": bucket["net_bias"],
                        "net_risk_percent": bucket["net_risk_percent"],
                    }
                )
        summary["totals"]["remaining_portfolio_risk_percent"] = round(
            max(
                settings.runtime_max_open_risk_percent
                - summary["totals"]["reserved_risk_percent"]
                - summary["totals"]["live_risk_percent"],
                0.0,
            ),
            6,
        )
        return {
            "totals": {
                key: round(value, 6) if isinstance(value, float) else value
                for key, value in summary["totals"].items()
            },
            "by_strategy": self._serialize_buckets(summary["by_strategy"]),
            "by_family": self._serialize_buckets(summary["by_family"]),
            "by_instrument": self._serialize_buckets(summary["by_instrument"]),
            "by_currency": self._serialize_buckets(summary["by_currency"]),
            "currency_directional": self._serialize_currency_direction_buckets(
                summary["currency_directional"]
            ),
            "hotspots": sorted(
                hotspots,
                key=lambda item: float(item["utilization_percent"]),
                reverse=True,
            ),
            "notes": {
                "currency_bucket_mode": "gross_proxy_plus_directional_split",
                "directional_netting": "derived_from_pair_direction_and_currency_side",
                "currency_directional_exactness": "exact_pair_direction_with_split_risk_attribution",
                "reserved_risk_basis": "intent_submitted_or_fill_derived_or_estimated_or_partial_fill_residual",
                "live_risk_basis": "position_entry_risk_amount_or_position_risk_percent",
            },
        }

    def _serialize_cycle(self, cycle: AllocationCycle) -> dict[str, object]:
        return {
            "cycle_id": cycle.cycle_id,
            "received_at": cycle.received_at,
            "completed_at": cycle.completed_at,
            "candidate_count": cycle.candidate_count,
            "approved_count": cycle.approved_count,
            "rejected_count": cycle.rejected_count,
            "total_requested_risk_percent": cycle.total_requested_risk_percent,
            "total_allocated_risk_percent": cycle.total_allocated_risk_percent,
            "remaining_portfolio_risk_percent": cycle.remaining_portfolio_risk_percent,
            "resized_candidate_count": cycle.resized_candidate_count,
            "degraded_candidate_count": cycle.degraded_candidate_count,
            "blocked_unsupported_sizing_count": cycle.blocked_unsupported_sizing_count,
            "blocked_approximate_live_count": cycle.blocked_approximate_live_count,
            "blocked_under_minimum_size_count": cycle.blocked_under_minimum_size_count,
            "blocked_budget_count": cycle.blocked_budget_count,
            "blocked_conflict_count": cycle.blocked_conflict_count,
            "binding_budget_counts": cycle.binding_budget_counts,
            "rejection_reason_counts": cycle.rejection_reason_counts,
            "details": cycle.details,
        }

    def _serialize_intent(self, intent: TradeIntent) -> dict[str, object]:
        allocation = (intent.details or {}).get("allocation") or {}
        allocation_outcome = (intent.details or {}).get("allocation_outcome") or {}
        risk_tracking = {**((intent.details or {}).get("risk_tracking") or {})}
        latest_execution = (
            self.trade_service.get_latest_execution_for_trade_intent(intent.id or 0)
            if intent.id is not None
            else None
        )
        executions = (
            self.trade_service.list_executions_for_trade_intent(intent.id or 0)
            if intent.id is not None
            else []
        )
        position = (
            self.trade_service.get_position_by_id(intent.position_id)
            if intent.position_id is not None
            else None
        )
        trade = (
            self.trade_service.get_trade(intent.trade_id)
            if intent.trade_id is not None
            else None
        )
        risk_tracking.update(
            {
                "estimated_allocation_risk_amount": intent.estimated_risk_amount,
                "submitted_executable_risk_amount": intent.submitted_risk_amount,
                "fill_derived_risk_amount": intent.fill_derived_risk_amount,
                "risk_currency": intent.risk_currency,
            }
        )
        risk_reconciliation = {
            **((intent.details or {}).get("risk_reconciliation") or {})
        }
        return {
            "id": intent.id,
            "allocation_cycle_id": intent.allocation_cycle_id,
            "strategy_name": intent.strategy_name,
            "family_name": intent.family_name,
            "instrument": intent.instrument,
            "direction": intent.direction,
            "state": intent.state,
            "signal_time": intent.signal_time,
            "decision_reason_code": intent.decision_reason_code,
            "decision_reason": intent.decision_reason,
            "close_reason_code": intent.close_reason_code,
            "close_reason": intent.close_reason,
            "proposed_size": intent.proposed_size,
            "allocated_size": intent.allocated_size,
            "proposed_risk_percent": intent.proposed_risk_percent,
            "allocated_risk_percent": intent.allocated_risk_percent,
            "confidence": intent.confidence,
            "estimated_risk_amount": intent.estimated_risk_amount,
            "submitted_risk_amount": intent.submitted_risk_amount,
            "fill_derived_risk_amount": intent.fill_derived_risk_amount,
            "risk_truth_confidence": intent.risk_truth_confidence,
            "risk_currency": intent.risk_currency,
            "allocation": allocation,
            "allocation_outcome": allocation_outcome,
            "risk_tracking": risk_tracking,
            "risk_reconciliation": risk_reconciliation,
            "latest_execution": self._serialize_execution(latest_execution),
            "executions": [
                self._serialize_execution(execution) for execution in executions
            ],
            "position": self._serialize_position(position),
            "trade": self._serialize_trade(trade),
            "details": intent.details or {},
            "created_at": intent.created_at,
            "updated_at": intent.updated_at,
        }

    @staticmethod
    def _serialize_execution(execution: Execution | None) -> dict[str, object] | None:
        if execution is None:
            return None
        return {
            "id": execution.id,
            "phase": execution.phase,
            "status": execution.status,
            "client_request_id": project_identifier(
                execution.client_request_id,
                kind="request_id",
            ),
            "broker_reference": project_identifier(
                execution.broker_reference,
                kind="broker_reference",
            ),
            "submitted_at": execution.submitted_at,
            "acknowledged_at": execution.acknowledged_at,
            "completed_at": execution.completed_at,
            "requested_size": execution.requested_size,
            "filled_size": execution.filled_size,
            "requested_price": execution.requested_price,
            "average_fill_price": execution.average_fill_price,
            "intended_risk_amount": execution.intended_risk_amount,
            "submitted_risk_amount": execution.submitted_risk_amount,
            "fill_derived_risk_amount": execution.fill_derived_risk_amount,
            "risk_truth_confidence": execution.risk_truth_confidence,
            "reason": execution.reason,
            "error_code": execution.error_code,
            "error_message": execution.error_message,
            "requires_manual_review": execution.requires_manual_review,
            "details": execution.details or {},
        }

    @staticmethod
    def _serialize_position(position: Position | None) -> dict[str, object] | None:
        if position is None:
            return None
        return {
            "id": position.id,
            "broker_reference": project_identifier(
                position.broker_reference,
                kind="broker_reference",
            ),
            "instrument": position.instrument,
            "direction": position.direction,
            "size": position.size,
            "open_price": position.open_price,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "risk_percent": position.risk_percent,
            "entry_risk_amount": position.entry_risk_amount,
            "risk_truth_confidence": position.risk_truth_confidence,
            "open_time": position.open_time,
            "close_time": position.close_time,
            "is_open": position.is_open,
        }

    @staticmethod
    def _serialize_trade(trade: Trade | None) -> dict[str, object] | None:
        if trade is None:
            return None
        return {
            "id": trade.id,
            "broker_reference": project_identifier(
                trade.broker_reference,
                kind="broker_reference",
            ),
            "close_broker_reference": project_identifier(
                trade.close_broker_reference,
                kind="broker_reference",
            ),
            "instrument": trade.instrument,
            "direction": trade.direction,
            "size": trade.size,
            "open_price": trade.open_price,
            "close_price": trade.close_price,
            "pnl": trade.pnl,
            "entry_risk_amount": trade.entry_risk_amount,
            "risk_truth_confidence": trade.risk_truth_confidence,
            "r_multiple": trade.r_multiple,
            "open_time": trade.open_time,
            "close_time": trade.close_time,
            "reason": trade.reason,
            "outcome": trade.outcome,
        }

    @staticmethod
    def _max_percent_drift(metrics: dict[str, object]) -> float | None:
        values: list[float] = []
        for value in metrics.values():
            if isinstance(value, dict) and value.get("percent_drift_abs") is not None:
                values.append(float(value["percent_drift_abs"]))
        return max(values) if values else None

    @staticmethod
    def _serialize_drift_buckets(
        buckets: dict[str, list[float]],
    ) -> list[dict[str, object]]:
        rows = []
        for name, values in buckets.items():
            if not values:
                continue
            rows.append(
                {
                    "name": name,
                    "count": len(values),
                    "average_percent_drift": round(sum(values) / len(values), 6),
                    "max_percent_drift": round(max(values), 6),
                }
            )
        return sorted(
            rows, key=lambda item: float(item["max_percent_drift"]), reverse=True
        )

    @staticmethod
    def _alert(
        *,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        count: int,
        timestamps: list[object],
        intent_ids: list[int] | None = None,
        cycle_ids: list[str] | None = None,
        execution_ids: list[int] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
        return {
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "count": count,
            "first_seen_at": min(timestamps) if timestamps else None,
            "last_seen_at": max(timestamps) if timestamps else None,
            "intent_ids": intent_ids or [],
            "cycle_ids": cycle_ids or [],
            "execution_ids": execution_ids or [],
            "details": details or {},
        }

    @staticmethod
    def _empty_bucket(
        bucket_type: str, budget_limit_percent: float
    ) -> dict[str, object]:
        return {
            "bucket_type": bucket_type,
            "reserved_risk_percent": 0.0,
            "live_risk_percent": 0.0,
            "reserved_risk_amount": 0.0,
            "live_risk_amount": 0.0,
            "reserved_count": 0,
            "live_count": 0,
            "budget_limit_percent": budget_limit_percent,
            "risk_basis": set(),
        }

    @staticmethod
    def _empty_currency_direction_bucket() -> dict[str, object]:
        return {
            "reserved_long_risk_percent": 0.0,
            "reserved_short_risk_percent": 0.0,
            "live_long_risk_percent": 0.0,
            "live_short_risk_percent": 0.0,
            "reserved_long_risk_amount": 0.0,
            "reserved_short_risk_amount": 0.0,
            "live_long_risk_amount": 0.0,
            "live_short_risk_amount": 0.0,
            "risk_basis": set(),
        }

    @staticmethod
    def _serialize_buckets(
        buckets: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for name, bucket in buckets.items():
            rows.append({"name": name, **bucket})
        rows.sort(key=lambda item: float(item["total_risk_percent"]), reverse=True)
        return rows

    @staticmethod
    def _serialize_currency_direction_buckets(
        buckets: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for name, bucket in buckets.items():
            rows.append({"currency": name, **bucket})
        rows.sort(key=lambda item: float(item["gross_risk_percent"]), reverse=True)
        return rows

    @staticmethod
    def _comparable_datetime(value):
        return (
            value.replace(tzinfo=None)
            if getattr(value, "tzinfo", None) is not None
            else value
        )

    @staticmethod
    def _currency_buckets(
        instrument: str, details: dict[str, object]
    ) -> tuple[str, ...]:
        allocation = (
            (details.get("allocation") or {}) if isinstance(details, dict) else {}
        )
        broker_details = (
            (allocation.get("broker_details") or {})
            if isinstance(allocation, dict)
            else {}
        )
        base = broker_details.get("base_currency")
        quote = broker_details.get("quote_currency")
        if isinstance(base, str) and isinstance(quote, str):
            return (base.upper(), quote.upper())
        symbol = instrument.replace("/", "").upper()
        if len(symbol) == 6 and symbol.isalpha():
            return (symbol[:3], symbol[3:])
        return ()

    @staticmethod
    def _intent_risk(intent: TradeIntent) -> tuple[float, float, str]:
        residual_ratio = AllocationReadService._partial_fill_residual_ratio(intent)
        if residual_ratio > 0.0:
            submitted_risk_amount = (
                intent.submitted_risk_amount
                if intent.submitted_risk_amount is not None
                else intent.estimated_risk_amount
            )
            return (
                float(
                    intent.allocated_risk_percent or intent.proposed_risk_percent or 0.0
                )
                * residual_ratio,
                float(submitted_risk_amount or 0.0) * residual_ratio,
                "partial_fill_residual",
            )
        if intent.fill_derived_risk_amount is not None:
            return (
                float(
                    intent.allocated_risk_percent or intent.proposed_risk_percent or 0.0
                ),
                float(intent.fill_derived_risk_amount),
                "fill_derived",
            )
        if intent.submitted_risk_amount is not None:
            return (
                float(
                    intent.allocated_risk_percent or intent.proposed_risk_percent or 0.0
                ),
                float(intent.submitted_risk_amount),
                "submitted_executable",
            )
        return (
            float(intent.allocated_risk_percent or intent.proposed_risk_percent or 0.0),
            float(intent.estimated_risk_amount or 0.0),
            "estimated_allocation",
        )

    @staticmethod
    def _partial_fill_residual_ratio(intent: TradeIntent) -> float:
        if intent.state != "PARTIALLY_FILLED":
            return 0.0
        partial_fill = (intent.details or {}).get("partial_fill") or {}
        if not isinstance(partial_fill, dict):
            return 0.0
        submitted_size = float(partial_fill.get("submitted_size") or 0.0)
        residual_size = float(partial_fill.get("residual_size") or 0.0)
        if submitted_size <= 0 or residual_size <= 0:
            return 0.0
        return min(max(residual_size / submitted_size, 0.0), 1.0)

    @classmethod
    def _add_exposure(
        cls,
        *,
        summary: dict[str, object],
        key_type: str,
        strategy_name: str,
        family_name: str,
        instrument: str,
        currencies: tuple[str, ...],
        direction: str,
        risk_percent: float,
        risk_amount: float,
        basis: str,
        provisional: bool = False,
    ) -> None:
        total_key = f"{key_type}_risk_percent"
        amount_key = f"{key_type}_risk_amount"
        count_key = f"{key_type}_count"
        summary["totals"][total_key] += risk_percent
        summary["totals"][amount_key] += risk_amount
        if provisional and key_type == "live":
            summary["totals"]["provisional_live_risk_percent"] += risk_percent
            summary["totals"]["provisional_live_risk_amount"] += risk_amount
        for bucket_name, label in (
            ("by_strategy", strategy_name),
            ("by_family", family_name),
            ("by_instrument", instrument),
        ):
            bucket = summary[bucket_name][label]
            bucket[total_key] += risk_percent
            bucket[amount_key] += risk_amount
            bucket[count_key] += 1
            bucket["risk_basis"].add(basis)
        for currency in currencies:
            bucket = summary["by_currency"][currency]
            bucket[total_key] += risk_percent / max(len(currencies), 1)
            bucket[amount_key] += risk_amount / max(len(currencies), 1)
            bucket[count_key] += 1
            bucket["risk_basis"].add(basis)
        for currency, side in cls._currency_direction_components(
            currencies=currencies, direction=direction
        ):
            bucket = summary["currency_directional"][currency]
            bucket[f"{key_type}_{side}_risk_percent"] += risk_percent / max(
                len(currencies), 1
            )
            bucket[f"{key_type}_{side}_risk_amount"] += risk_amount / max(
                len(currencies), 1
            )
            bucket["risk_basis"].add(basis)

    @staticmethod
    def _currency_direction_components(
        *, currencies: tuple[str, ...], direction: str
    ) -> list[tuple[str, str]]:
        if len(currencies) != 2:
            return []
        base, quote = currencies
        normalized_direction = str(direction).upper()
        if normalized_direction == "BUY":
            return [(base, "long"), (quote, "short")]
        if normalized_direction == "SELL":
            return [(base, "short"), (quote, "long")]
        return []
