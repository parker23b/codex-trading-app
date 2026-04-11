from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from sqlmodel import Session

from app.core.signals import EntrySignal, ExitSignal, SignalCandidate, SignalStatus
from app.models.trade import TradeIntent, TradeIntentState
from app.services.market_status_service import get_market_status_service
from app.services.portfolio_risk_service import PortfolioRiskService
from app.services.trade_allocator_service import TradeAllocatorService
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
        "direction_conflict": "opposing_signal_blocked",
        "instrument_exposure_limit": "instrument_already_allocated",
        "cycle_capacity": "insufficient_capacity",
        "strategy_capacity": "strategy_capacity_reached",
        "open_risk_capacity": "portfolio_risk_rejected",
        "stale_signal": "stale_signal",
        "selected": "approved",
    }

    def __init__(self, session: Session):
        self.session = session
        self.trade_service = TradeService(session)
        self.risk_service = PortfolioRiskService(session)
        self.trade_allocator = TradeAllocatorService(session)
        self.market_status_service = get_market_status_service()

    def decide_signal_candidates(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[TradeDecisionResult]:
        entries = [candidate for candidate in candidates if isinstance(candidate.signal, EntrySignal)]
        exits = [candidate for candidate in candidates if isinstance(candidate.signal, ExitSignal)]
        results: list[TradeDecisionResult] = []

        if entries:
            results.extend(self._decide_entry_candidates(entries, received_at=received_at))
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
        prepared_candidates: list[SignalCandidate] = []
        for candidate in candidates:
            signal = candidate.signal
            assert isinstance(signal, EntrySignal)
            size_hint, risk_hint = self._resolve_sizing(candidate)
            signal.size = size_hint
            signal.risk_percent = risk_hint
            prepared_candidates.append(candidate)

        open_positions = self.trade_service.list_positions()
        trades = self.trade_service.list_trades()
        allocation_decisions = self.trade_allocator.allocate(prepared_candidates, received_at=received_at)
        for allocation in allocation_decisions:
            candidate = allocation.candidate
            signal = candidate.signal
            assert isinstance(signal, EntrySignal)
            mapped_reason = self.ALLOCATOR_REASON_MAP.get(allocation.reason_code, allocation.reason_code)
            if allocation.selected:
                existing_active = self.trade_service.find_active_trade_intent_for_instrument(candidate.instrument)
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
                        details={"conflicting_trade_intent_id": existing_active.id},
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
                            {"conflicting_trade_intent_id": conflicting_id}
                            if conflicting_id is not None
                            else None
                        ),
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
                    details={"allocator_score": allocation.score},
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

            approved_signal = self._apply_market_status_gate(candidate=candidate, signal=signal)
            if approved_signal.status is not SignalStatus.REJECTED:
                approved_signal = self.risk_service.assess_entry(
                    approved_signal,
                    open_positions=open_positions,
                    trades=trades,
                )
            if approved_signal.status is SignalStatus.APPROVED:
                approved_signal = self._apply_broker_entry_constraints(candidate=candidate, signal=approved_signal)

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
                        details={"conflicting_trade_intent_id": conflicting_active.id},
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
                        decision_reason=approved_signal.reason or "Approved by centralized trade decision service.",
                        details={
                            "allocator_score": allocation.score,
                            "risk_rejection_layer": approved_signal.rejection_layer,
                            "risk_audit_summary": approved_signal.audit_summary,
                            "risk_audit_trail": approved_signal.audit_trail,
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
                            {"conflicting_trade_intent_id": exc.conflicting_intent_id}
                            if exc.conflicting_intent_id is not None
                            else None
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
                    "allocator_score": allocation.score,
                    "risk_rejection_layer": approved_signal.rejection_layer,
                    "risk_audit_summary": approved_signal.audit_summary,
                    "risk_audit_trail": approved_signal.audit_trail,
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
        details: dict[str, object] | None = None,
    ) -> TradeIntent:
        return self.trade_service.create_trade_intent(
            TradeIntent(
                strategy_name=candidate.strategy_name,
                instrument=candidate.instrument,
                direction=signal.direction.value,
                state=initial_state.value,
                signal_time=signal.signal_at,
                proposed_size=signal.size,
                allocated_size=signal.size,
                proposed_risk_percent=signal.risk_percent,
                allocated_risk_percent=signal.risk_percent,
                confidence=candidate.confidence,
                observed_price=signal.observed_price,
                market_status=signal.market_status,
                tradable=signal.tradable,
                decision_reason_code=decision_reason_code,
                decision_reason=decision_reason,
                details={
                    "source_tier": candidate.source_tier,
                    "strategy_hints": {
                        "metadata_position_size": getattr(candidate.metadata, "position_size", None),
                        "metadata_risk_per_trade": getattr(candidate.metadata, "risk_per_trade", None),
                        "signal_size_hint": signal.size,
                    },
                    **(details or {}),
                },
            )
        )

    @staticmethod
    def _resolve_sizing(candidate: SignalCandidate) -> tuple[float, float]:
        metadata = candidate.metadata
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        size_hint = float(getattr(metadata, "position_size", signal.size) or signal.size or 0.0)
        risk_hint = float(getattr(metadata, "risk_per_trade", signal.risk_percent) or signal.risk_percent or 0.0)
        return size_hint, risk_hint

    def _apply_market_status_gate(self, *, candidate: SignalCandidate, signal: EntrySignal) -> EntrySignal:
        status = self.market_status_service.get_status(signal.instrument, broker=candidate.engine.broker, now=signal.signal_at)
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

    @staticmethod
    def _apply_broker_entry_constraints(*, candidate: SignalCandidate, signal: EntrySignal) -> EntrySignal:
        try:
            market_details = candidate.engine.broker.get_market_details(signal.instrument)
        except Exception:
            return signal

        min_deal_size = market_details.min_deal_size
        if min_deal_size is None or signal.size >= min_deal_size:
            return signal

        reason = (
            f"Requested size {signal.size} is below broker minimum deal size "
            f"{min_deal_size} for {signal.instrument}."
        )
        audit_trail = list(signal.audit_trail)
        audit_trail.append(
            {
                "layer": "broker_constraints",
                "status": "REJECTED",
                "passed": False,
                "reason": reason,
                "checks": [
                    {
                        "code": "min_deal_size",
                        "passed": False,
                        "reason": reason,
                        "actual": signal.size,
                        "limit": min_deal_size,
                    }
                ],
            }
        )
        audit_summary = dict(signal.audit_summary)
        audit_summary.update(
            {
                "approved": False,
                "rejection_layer": "broker_constraints",
                "min_deal_size": min_deal_size,
            }
        )
        return replace(
            signal,
            status=SignalStatus.REJECTED,
            reason=reason,
            rejection_layer="broker_constraints",
            audit_trail=audit_trail,
            audit_summary=audit_summary,
        )

    @staticmethod
    def _reason_code_from_signal(signal: EntrySignal) -> str:
        if signal.rejection_layer == "broker_constraints":
            return "below_min_size"
        if signal.rejection_layer == "market_status":
            return "market_closed" if "closed" in (signal.reason or "").lower() else "instrument_not_tradable"
        if signal.rejection_layer in {"portfolio", "kill_switch"}:
            return "portfolio_risk_rejected"
        if signal.rejection_layer == "market_quality":
            return "market_quality_rejected"
        if signal.rejection_layer == "pre_trade":
            return "pre_trade_rejected"
        if signal.rejection_layer == "platform_health":
            return "platform_health_rejected"
        return "rejected"
