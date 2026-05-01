from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from sqlmodel import Session

from app.core.signals import EntrySignal, ExitSignal, SignalCandidate, SignalStatus
from app.models.trade import TradeIntent, TradeIntentState
from app.services.capital_allocator_service import (
    AllocationDecision,
    CapitalAllocatorService,
)
from app.services.market_status_service import get_market_status_service
from app.services.operational_state_service import OperationalStateService
from app.services.portfolio_risk_service import PortfolioRiskService
from app.services.trade_service import ActiveTradeIntentConflictError, TradeService


@dataclass(slots=True)
class TradeDecisionResult:
    """
    Output of the authoritative pre-trade decision boundary.

    Raw strategy candidates become durable `TradeIntent` records here first.
    Only results marked `admitted=True` may proceed to broker submission.
    """

    candidate: SignalCandidate
    intent: TradeIntent | None
    admitted: bool
    reason_code: str | None
    reason: str | None


class TradeDecisionService:
    """Owns proposal, allocation, risk approval, and final entry admission."""

    ALLOCATOR_REASON_MAP = {
        "weaker_duplicate": "duplicate_same_direction",
        "portfolio_position_limit": "portfolio_position_limit",
        "strategy_position_limit": "strategy_capacity_reached",
        "cycle_position_limit": "cycle_capacity_reached",
        "portfolio_risk_exhausted": "portfolio_risk_rejected",
        "cycle_risk_exhausted": "cycle_risk_rejected",
        "strategy_risk_exhausted": "strategy_budget_exhausted",
        "family_risk_exhausted": "family_budget_exhausted",
        "instrument_risk_exhausted": "instrument_budget_exhausted",
        "currency_USD_exhausted": "currency_budget_exhausted",
        "currency_EUR_exhausted": "currency_budget_exhausted",
        "currency_GBP_exhausted": "currency_budget_exhausted",
        "currency_JPY_exhausted": "currency_budget_exhausted",
        "currency_AUD_exhausted": "currency_budget_exhausted",
        "currency_CHF_exhausted": "currency_budget_exhausted",
        "currency_CAD_exhausted": "currency_budget_exhausted",
        "currency_NZD_exhausted": "currency_budget_exhausted",
        "gross_exposure_limit": "gross_exposure_rejected",
        "below_min_size": "below_min_size",
        "size_rounded_to_zero": "below_min_size",
        "direction_conflict": "opposing_signal_blocked",
        "account_equity_unavailable": "allocation_blocked",
        "account_equity_invalid": "allocation_blocked",
        "broker_metadata_unavailable": "allocation_blocked",
        "sizing_context_unavailable": "allocation_blocked",
        "sizing_quote_unavailable": "allocation_blocked",
        "approximate_sizing_unsupported": "allocation_blocked",
        "stale_signal": "stale_signal",
        "allocated": "approved",
    }

    def __init__(self, session: Session):
        self.session = session
        self.trade_service = TradeService(session)
        self.risk_service = PortfolioRiskService(session)
        self.capital_allocator = CapitalAllocatorService(session)
        self.market_status_service = get_market_status_service()
        self.operational_state_service = OperationalStateService(session)

    def decide_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[TradeDecisionResult]:
        entries = [
            candidate
            for candidate in candidates
            if isinstance(candidate.signal, EntrySignal)
        ]
        exits = [
            candidate
            for candidate in candidates
            if isinstance(candidate.signal, ExitSignal)
        ]
        results: list[TradeDecisionResult] = []

        if entries:
            results.extend(
                self._decide_entry_candidates(entries, received_at=received_at)
            )
        for candidate in exits:
            results.append(self._link_exit_candidate(candidate))
        return results

    def _decide_entry_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[TradeDecisionResult]:
        results: list[TradeDecisionResult] = []
        open_positions = self.trade_service.list_positions()
        trades = self.trade_service.list_trades()
        allocation_decisions = self.capital_allocator.allocate(
            candidates, received_at=received_at
        )
        for allocation in allocation_decisions:
            candidate = allocation.candidate
            signal = candidate.signal
            assert isinstance(signal, EntrySignal)
            mapped_reason = self.ALLOCATOR_REASON_MAP.get(
                allocation.reason_code, allocation.reason_code
            )
            signal.size = (
                allocation.normalized_size
                if allocation.selected
                else allocation.requested_size
            )
            signal.risk_percent = (
                allocation.allocated_risk_percent
                if allocation.selected
                else allocation.requested_risk_percent
            )
            if allocation.selected:
                existing_active = (
                    self.trade_service.find_active_trade_intent_for_instrument(
                        candidate.instrument
                    )
                )
                if existing_active is not None:
                    intent = self._create_trade_intent(
                        candidate=candidate,
                        signal=signal,
                        initial_state=TradeIntentState.REJECTED,
                        decision_reason_code="instrument_already_allocated",
                        decision_reason=(
                            f"Instrument {candidate.instrument} already has active intent "
                            f"{existing_active.id} in state {existing_active.state}."
                        ),
                        allocation=allocation,
                        details={
                            "conflicting_trade_intent_id": existing_active.id,
                            "allocation_outcome": {
                                "stage": "post_allocation_conflict",
                                "allocator_selected": True,
                                "hard_risk_passed": None,
                                "hard_risk_blocked": False,
                                "execution_submitted": False,
                                "execution_blocked": True,
                                "execution_revalidation_changed_outcome": False,
                                "fill_status": None,
                                "final_status": TradeIntentState.REJECTED.value,
                            },
                        },
                    )
                    results.append(
                        TradeDecisionResult(
                            candidate=candidate,
                            intent=intent,
                            admitted=False,
                            reason_code="instrument_already_allocated",
                            reason=intent.decision_reason,
                        )
                    )
                    continue
                try:
                    intent = self._create_trade_intent(
                        candidate=candidate,
                        signal=signal,
                        initial_state=TradeIntentState.PROPOSED,
                        decision_reason_code="proposed",
                        decision_reason="Raw strategy signal proposed for centralized trade admission.",
                        allocation=allocation,
                    )
                except ActiveTradeIntentConflictError as exc:
                    conflicting_id = exc.conflicting_intent_id
                    intent = self._create_trade_intent(
                        candidate=candidate,
                        signal=signal,
                        initial_state=TradeIntentState.REJECTED,
                        decision_reason_code="instrument_already_allocated",
                        decision_reason=(
                            f"Instrument {candidate.instrument} was allocated concurrently by "
                            f"trade intent {conflicting_id}."
                            if conflicting_id is not None
                            else f"Instrument {candidate.instrument} was allocated concurrently."
                        ),
                        details=(
                            {
                                "conflicting_trade_intent_id": conflicting_id,
                                "allocation_outcome": {
                                    "stage": "post_allocation_conflict",
                                    "allocator_selected": True,
                                    "hard_risk_passed": None,
                                    "hard_risk_blocked": False,
                                    "execution_submitted": False,
                                    "execution_blocked": True,
                                    "execution_revalidation_changed_outcome": False,
                                    "fill_status": None,
                                    "final_status": TradeIntentState.REJECTED.value,
                                },
                            }
                            if conflicting_id is not None
                            else {
                                "allocation_outcome": {
                                    "stage": "post_allocation_conflict",
                                    "allocator_selected": True,
                                    "hard_risk_passed": None,
                                    "hard_risk_blocked": False,
                                    "execution_submitted": False,
                                    "execution_blocked": True,
                                    "execution_revalidation_changed_outcome": False,
                                    "fill_status": None,
                                    "final_status": TradeIntentState.REJECTED.value,
                                }
                            }
                        ),
                        allocation=allocation,
                    )
                    results.append(
                        TradeDecisionResult(
                            candidate=candidate,
                            intent=intent,
                            admitted=False,
                            reason_code="instrument_already_allocated",
                            reason=intent.decision_reason,
                        )
                    )
                    continue
            else:
                intent = self._create_trade_intent(
                    candidate=candidate,
                    signal=signal,
                    initial_state=TradeIntentState.REJECTED,
                    decision_reason_code=mapped_reason,
                    decision_reason=allocation.reason,
                    allocation=allocation,
                )

            if not allocation.selected:
                results.append(
                    TradeDecisionResult(
                        candidate=candidate,
                        intent=intent,
                        admitted=False,
                        reason_code=mapped_reason,
                        reason=allocation.reason,
                    )
                )
                continue

            approved_signal = self._apply_operational_policy_gate(
                candidate=candidate, signal=signal
            )
            if approved_signal.status is not SignalStatus.REJECTED:
                approved_signal = self._apply_market_status_gate(
                    candidate=candidate, signal=approved_signal
                )
            if approved_signal.status is not SignalStatus.REJECTED:
                approved_signal = self.risk_service.assess_entry(
                    approved_signal,
                    open_positions=open_positions,
                    trades=trades,
                )

            if approved_signal.status is SignalStatus.APPROVED:
                conflicting_active = self.trade_service.find_active_trade_intent_for_instrument_excluding(
                    candidate.instrument,
                    exclude_intent_id=intent.id,
                )
                if conflicting_active is not None:
                    rejected = self.trade_service.transition_trade_intent(
                        intent,
                        state=TradeIntentState.REJECTED,
                        decision_reason_code="instrument_already_allocated",
                        decision_reason=(
                            f"Instrument {candidate.instrument} was allocated while this intent was under review "
                            f"by intent {conflicting_active.id}."
                        ),
                        details={
                            "conflicting_trade_intent_id": conflicting_active.id,
                            "allocation_outcome": {
                                "stage": "post_allocation_conflict",
                                "allocator_selected": True,
                                "hard_risk_passed": True,
                                "hard_risk_blocked": False,
                                "execution_submitted": False,
                                "execution_blocked": True,
                                "execution_revalidation_changed_outcome": False,
                                "fill_status": None,
                                "final_status": TradeIntentState.REJECTED.value,
                            },
                        },
                    )
                    results.append(
                        TradeDecisionResult(
                            candidate=candidate,
                            intent=rejected,
                            admitted=False,
                            reason_code="instrument_already_allocated",
                            reason=rejected.decision_reason,
                        )
                    )
                    continue
                try:
                    approved = self.trade_service.transition_trade_intent(
                        intent,
                        state=TradeIntentState.APPROVED,
                        allocated_size=approved_signal.size,
                        allocated_risk_percent=approved_signal.risk_percent,
                        decision_reason_code="approved",
                        decision_reason=approved_signal.reason
                        or "Approved by centralized trade decision service.",
                        details={
                            "allocator_score": allocation.priority_score,
                            "allocation_priority_score": allocation.priority_score,
                            "risk_rejection_layer": approved_signal.rejection_layer,
                            "risk_audit_summary": approved_signal.audit_summary,
                            "risk_audit_trail": approved_signal.audit_trail,
                            "allocation_outcome": {
                                "stage": "approved_for_execution",
                                "allocator_selected": True,
                                "hard_risk_passed": True,
                                "hard_risk_blocked": False,
                                "execution_submitted": False,
                                "execution_blocked": False,
                                "execution_revalidation_changed_outcome": False,
                                "fill_status": None,
                                "final_status": TradeIntentState.APPROVED.value,
                            },
                        },
                    )
                except ActiveTradeIntentConflictError as exc:
                    rejected = self.trade_service.transition_trade_intent(
                        intent,
                        state=TradeIntentState.REJECTED,
                        decision_reason_code="instrument_already_allocated",
                        decision_reason=(
                            f"Instrument {candidate.instrument} was allocated concurrently by "
                            f"trade intent {exc.conflicting_intent_id}."
                            if exc.conflicting_intent_id is not None
                            else f"Instrument {candidate.instrument} was allocated concurrently."
                        ),
                        details=(
                            {
                                "conflicting_trade_intent_id": exc.conflicting_intent_id,
                                "allocation_outcome": {
                                    "stage": "post_allocation_conflict",
                                    "allocator_selected": True,
                                    "hard_risk_passed": True,
                                    "hard_risk_blocked": False,
                                    "execution_submitted": False,
                                    "execution_blocked": True,
                                    "execution_revalidation_changed_outcome": False,
                                    "fill_status": None,
                                    "final_status": TradeIntentState.REJECTED.value,
                                },
                            }
                            if exc.conflicting_intent_id is not None
                            else {
                                "allocation_outcome": {
                                    "stage": "post_allocation_conflict",
                                    "allocator_selected": True,
                                    "hard_risk_passed": True,
                                    "hard_risk_blocked": False,
                                    "execution_submitted": False,
                                    "execution_blocked": True,
                                    "execution_revalidation_changed_outcome": False,
                                    "fill_status": None,
                                    "final_status": TradeIntentState.REJECTED.value,
                                }
                            }
                        ),
                    )
                    results.append(
                        TradeDecisionResult(
                            candidate=candidate,
                            intent=rejected,
                            admitted=False,
                            reason_code="instrument_already_allocated",
                            reason=rejected.decision_reason,
                        )
                    )
                    continue
                results.append(
                    TradeDecisionResult(
                        candidate=candidate,
                        intent=approved,
                        admitted=True,
                        reason_code="approved",
                        reason=approved.decision_reason,
                    )
                )
                continue

            rejection_code = self._reason_code_from_signal(approved_signal)
            rejected = self.trade_service.transition_trade_intent(
                intent,
                state=TradeIntentState.REJECTED,
                decision_reason_code=rejection_code,
                decision_reason=approved_signal.reason,
                details={
                    "allocator_score": allocation.priority_score,
                    "allocation_priority_score": allocation.priority_score,
                    "risk_rejection_layer": approved_signal.rejection_layer,
                    "risk_audit_summary": approved_signal.audit_summary,
                    "risk_audit_trail": approved_signal.audit_trail,
                    "allocation_outcome": {
                        "stage": "hard_risk_rejected",
                        "allocator_selected": True,
                        "hard_risk_passed": False,
                        "hard_risk_blocked": True,
                        "execution_submitted": False,
                        "execution_blocked": False,
                        "execution_revalidation_changed_outcome": False,
                        "fill_status": None,
                        "final_status": TradeIntentState.REJECTED.value,
                    },
                },
            )
            results.append(
                TradeDecisionResult(
                    candidate=candidate,
                    intent=rejected,
                    admitted=False,
                    reason_code=rejection_code,
                    reason=approved_signal.reason,
                )
            )

        return results

    def _link_exit_candidate(self, candidate: SignalCandidate) -> TradeDecisionResult:
        signal = candidate.signal
        assert isinstance(signal, ExitSignal)
        if signal.position is None:
            return TradeDecisionResult(
                candidate=candidate,
                intent=None,
                admitted=False,
                reason_code="missing_position_context",
                reason="Exit signal has no linked open position context.",
            )
        intent = self.trade_service.find_close_admissible_trade_intent(
            strategy_name=signal.strategy_name,
            instrument=signal.instrument,
            broker_reference=signal.position.broker_reference,
            position_id=signal.position.id,
        )
        if intent is None:
            return TradeDecisionResult(
                candidate=candidate,
                intent=None,
                admitted=False,
                reason_code="missing_open_trade_intent",
                reason="Exit signal was rejected because no close-admissible open trade intent was found.",
            )
        return TradeDecisionResult(
            candidate=candidate,
            intent=intent,
            admitted=True,
            reason_code="close_requested",
            reason="Exit candidate linked to an open trade intent.",
        )

    def _create_trade_intent(
        self,
        *,
        candidate: SignalCandidate,
        signal: EntrySignal,
        initial_state: TradeIntentState,
        decision_reason_code: str,
        decision_reason: str,
        allocation: AllocationDecision,
        details: dict[str, object] | None = None,
    ) -> TradeIntent:
        risk_currency = (
            ((allocation.sizing_details or {}).get("sizing_quote") or {}).get("details")
            or {}
        ).get("account_currency")
        allocation_outcome_stage = (
            "allocator_rejected"
            if not allocation.selected
            else "proposed_for_risk_overlay"
        )
        effective_risk_percent = (
            allocation.allocated_risk_percent
            if allocation.selected
            else allocation.requested_risk_percent
        )
        allocation_drift_metrics = self._build_allocation_drift_metrics(allocation)
        return self.trade_service.create_trade_intent(
            TradeIntent(
                strategy_name=candidate.strategy_name,
                family_name=getattr(candidate.metadata, "family_name", None),
                allocation_cycle_id=allocation.cycle_id,
                instrument=candidate.instrument,
                direction=signal.direction.value,
                state=initial_state.value,
                signal_time=signal.signal_at,
                proposed_size=allocation.requested_size
                if allocation.requested_size is not None
                else signal.size,
                allocated_size=allocation.normalized_size
                if allocation.normalized_size is not None
                else signal.size,
                proposed_risk_percent=(
                    allocation.requested_risk_percent
                    if allocation.requested_risk_percent is not None
                    else signal.risk_percent
                ),
                allocated_risk_percent=(
                    allocation.allocated_risk_percent
                    if allocation.allocated_risk_percent is not None
                    else signal.risk_percent
                ),
                estimated_risk_amount=allocation.risk_amount,
                risk_truth_confidence="ALLOCATION_INTENT_ONLY",
                risk_currency=str(risk_currency) if risk_currency is not None else None,
                confidence=candidate.confidence,
                observed_price=signal.observed_price,
                market_status=signal.market_status,
                tradable=signal.tradable,
                decision_reason_code=decision_reason_code,
                decision_reason=decision_reason,
                details={
                    "source_tier": candidate.source_tier,
                    "strategy_hints": {
                        "signal_size_hint": signal.size,
                        "signal_risk_percent_hint": signal.risk_percent,
                        "signal_stop_loss_price": signal.stop_loss_price,
                        "signal_take_profit_price": signal.take_profit_price,
                        "signal_expected_reward_risk": signal.expected_reward_risk,
                        "signal_volatility_estimate": signal.volatility_estimate,
                        "signal_thesis": signal.thesis,
                        "signal_strategy_metadata": dict(signal.strategy_metadata),
                    },
                    "allocation": {
                        "cycle_id": allocation.cycle_id,
                        "priority_score": allocation.priority_score,
                        "requested_size": allocation.requested_size,
                        "normalized_size": allocation.normalized_size,
                        "requested_risk_percent": allocation.requested_risk_percent,
                        "allocated_risk_percent": allocation.allocated_risk_percent,
                        "risk_amount": allocation.risk_amount,
                        "account_equity": allocation.account_equity,
                        "sizing_precision": allocation.sizing_precision,
                        "sizing_mode": allocation.sizing_mode,
                        "degraded": allocation.degraded,
                        "binding_budget": allocation.binding_budget,
                        "sizing_method": allocation.sizing_method,
                        "score_components": allocation.score_components,
                        "sizing_details": allocation.sizing_details,
                        "broker_details": allocation.broker_details,
                        "notes": allocation.notes,
                        "drift_metrics": allocation_drift_metrics,
                    },
                    "allocation_outcome": {
                        "stage": allocation_outcome_stage,
                        "allocator_selected": allocation.selected,
                        "hard_risk_passed": None,
                        "hard_risk_blocked": False,
                        "execution_submitted": False,
                        "execution_blocked": False,
                        "execution_revalidation_changed_outcome": False,
                        "fill_status": None,
                        "final_status": initial_state.value,
                    },
                    "risk_tracking": {
                        "risk_currency": risk_currency,
                        "estimated_allocation_risk_amount": allocation.risk_amount,
                        "estimated_allocation_risk_percent": effective_risk_percent,
                        "submitted_executable_risk_amount": None,
                        "submitted_executable_risk_percent": None,
                        "fill_derived_risk_amount": None,
                        "fill_derived_risk_percent": None,
                        "submitted_size": None,
                        "filled_size": None,
                        "reservation_owner": "INTENT",
                        "risk_state": "estimated_only",
                        "risk_truth_confidence": "ALLOCATION_INTENT_ONLY",
                    },
                    "risk_reconciliation": {
                        "estimated": {
                            "risk_amount": allocation.risk_amount,
                            "risk_percent": effective_risk_percent,
                            "size": allocation.normalized_size
                            if allocation.selected
                            else allocation.requested_size,
                            "entry_price": signal.observed_price,
                            "risk_currency": risk_currency,
                            "derivation_mode": "allocation_estimate",
                            "precision": allocation.sizing_precision,
                            "sizing_mode": allocation.sizing_mode,
                            "risk_truth_confidence": "ALLOCATION_INTENT_ONLY",
                        },
                        "submitted": None,
                        "filled": None,
                        "live_position": None,
                        "drift_metrics": allocation_drift_metrics,
                        "flags": {
                            "material_execution_drift": False,
                            "fill_risk_estimated": False,
                            "incomplete_fill_data": False,
                            "degraded_sizing": allocation.degraded,
                        },
                    },
                    **(details or {}),
                },
            )
        )

    @staticmethod
    def _metric(
        expected: float | None, actual: float | None
    ) -> dict[str, float | bool] | None:
        if expected is None or actual is None:
            return None
        absolute_drift = float(actual) - float(expected)
        percent_drift = None
        if abs(float(expected)) > 1e-9:
            percent_drift = (absolute_drift / float(expected)) * 100.0
        return {
            "expected": round(float(expected), 8),
            "actual": round(float(actual), 8),
            "absolute_drift": round(absolute_drift, 8),
            "absolute_drift_abs": round(abs(absolute_drift), 8),
            "percent_drift": round(percent_drift, 8)
            if percent_drift is not None
            else None,
            "percent_drift_abs": round(abs(percent_drift), 8)
            if percent_drift is not None
            else None,
        }

    def _build_allocation_drift_metrics(
        self, allocation: AllocationDecision
    ) -> dict[str, object]:
        return {
            "requested_to_normalized_size": self._metric(
                allocation.requested_size, allocation.normalized_size
            ),
            "requested_to_allocated_risk_percent": self._metric(
                allocation.requested_risk_percent,
                allocation.allocated_risk_percent,
            ),
        }

    def _apply_market_status_gate(
        self, *, candidate: SignalCandidate, signal: EntrySignal
    ) -> EntrySignal:
        status = self.market_status_service.get_status(
            signal.instrument, broker=candidate.engine.broker, now=signal.signal_at
        )
        audit_summary = dict(signal.audit_summary)
        audit_summary["market_status"] = status.model_dump(mode="json")
        if status.is_ok:
            return replace(signal, audit_summary=audit_summary)
        audit_trail = list(signal.audit_trail)
        audit_trail.append(
            {
                "layer": "market_status",
                "status": "REJECTED",
                "passed": False,
                "reason": status.reason,
                "checks": [
                    {
                        "code": "market_status_ok",
                        "passed": False,
                        "reason": status.reason,
                        "actual": status.model_dump(mode="json"),
                    }
                ],
            }
        )
        audit_summary.update({"approved": False, "rejection_layer": "market_status"})
        rejection_reason = status.reason or "Market status check failed."
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=rejection_reason,
            rejection_layer="market_status",
            audit_trail=audit_trail,
            audit_summary=audit_summary,
        )

    def _apply_operational_policy_gate(
        self, *, candidate: SignalCandidate, signal: EntrySignal
    ) -> EntrySignal:
        operational_state = self.operational_state_service.get_summary()
        audit_summary = dict(signal.audit_summary)
        audit_summary["operational_policy"] = operational_state.model_dump(mode="json")
        runtime_mode = str(
            getattr(candidate.engine, "runtime_mode", "NORMAL") or "NORMAL"
        )
        if operational_state.entry_eligible and runtime_mode != "EXITS_ONLY":
            return replace(signal, audit_summary=audit_summary)
        audit_trail = list(signal.audit_trail)
        gate_reason = (
            "runtime_exits_only"
            if runtime_mode == "EXITS_ONLY"
            else operational_state.entry_block_reason
        )
        rejection_reason = (
            f"Operational policy blocked new autonomous entries: {gate_reason}."
        )
        audit_trail.append(
            {
                "layer": "operational_policy",
                "status": "REJECTED",
                "passed": False,
                "reason": rejection_reason,
                "checks": [
                    {
                        "code": "entry_eligible",
                        "passed": False,
                        "reason": gate_reason,
                        "actual": {
                            **operational_state.model_dump(mode="json"),
                            "runtime_mode": runtime_mode,
                        },
                    }
                ],
            }
        )
        audit_summary.update(
            {"approved": False, "rejection_layer": "operational_policy"}
        )
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=rejection_reason,
            rejection_layer="operational_policy",
            audit_trail=audit_trail,
            audit_summary=audit_summary,
        )

    @staticmethod
    def _reason_code_from_signal(signal: EntrySignal) -> str:
        if signal.rejection_layer == "operational_policy":
            return "operational_policy_blocked"
        if signal.rejection_layer == "market_status":
            return (
                "market_closed"
                if "closed" in (signal.reason or "").lower()
                else "instrument_not_tradable"
            )
        if signal.rejection_layer in {"portfolio", "kill_switch"}:
            return "portfolio_risk_rejected"
        if signal.rejection_layer == "market_quality":
            return "market_quality_rejected"
        if signal.rejection_layer == "pre_trade":
            return "pre_trade_rejected"
        if signal.rejection_layer == "platform_health":
            return "platform_health_rejected"
        return "rejected"
