from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import floor
from uuid import uuid4

from sqlmodel import Session

from app.core.broker import (
    BrokerMarketDetails,
    BrokerRiskSizingQuote,
    BrokerSizingPrecision,
)
from app.core.config import get_settings
from app.core.instrument_catalog import list_market_instruments
from app.core.signals import EntrySignal, SignalCandidate
from app.models.trade import (
    AllocationCycle,
    Position,
    TradeIntent,
    TradeIntentState,
    utc_now,
)
from app.services.domain_event_service import domain_event_service
from app.services.trade_service import TradeService


RISK_RESERVED_INTENT_STATES = {
    TradeIntentState.APPROVED.value,
    TradeIntentState.SUBMITTED.value,
    TradeIntentState.ACKNOWLEDGED.value,
    TradeIntentState.PARTIALLY_FILLED.value,
    TradeIntentState.FILLED.value,
}


@dataclass(slots=True)
class AllocationDecision:
    candidate: SignalCandidate
    cycle_id: str
    selected: bool
    reason_code: str
    reason: str
    priority_score: float = 0.0
    requested_size: float = 0.0
    normalized_size: float = 0.0
    requested_risk_percent: float = 0.0
    allocated_risk_percent: float = 0.0
    risk_amount: float = 0.0
    account_equity: float = 0.0
    sizing_method: str = "unavailable"
    sizing_precision: str = "UNSUPPORTED"
    sizing_mode: str = "UNSUPPORTED"
    binding_budget: str | None = None
    score_components: dict[str, float] = field(default_factory=dict)
    sizing_details: dict[str, object] = field(default_factory=dict)
    broker_details: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    degraded: bool = False


@dataclass(slots=True)
class CandidatePlan:
    candidate: SignalCandidate
    family_name: str
    requested_risk_percent: float
    requested_size: float
    risk_amount: float
    account_equity: float
    entry_price: float
    priority_score: float
    score_components: dict[str, float]
    sizing_method: str
    sizing_details: dict[str, object]
    broker_details: BrokerMarketDetails
    sizing_quote: BrokerRiskSizingQuote
    currencies: tuple[str, ...]


class CapitalAllocatorService:
    """Constructs portfolio allocations before hard risk admission checks."""

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.trade_service = TradeService(session)
        self._instrument_index = {
            instrument.epic: instrument for instrument in list_market_instruments()
        }

    def allocate(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[AllocationDecision]:
        if not candidates:
            return []

        current_time = (
            received_at.astimezone(UTC)
            if received_at is not None
            else datetime.now(UTC)
        )
        cycle_id = f"alloc-{uuid4().hex[:12]}"
        open_positions = self.trade_service.list_positions()
        reserved_intents = self.trade_service.list_trade_intents(
            states=RISK_RESERVED_INTENT_STATES
        )
        decisions: list[AllocationDecision] = []
        candidate_plans: list[CandidatePlan] = []
        open_state = self._build_open_state(open_positions, reserved_intents)
        cycle_state = {
            "selected_positions": 0,
            "selected_risk": 0.0,
            "selected_gross_notional": 0.0,
            "selected_strategy_positions": defaultdict(int),
            "strategy_risk": defaultdict(float),
            "family_risk": defaultdict(float),
            "instrument_risk": defaultdict(float),
            "currency_risk": defaultdict(float),
        }

        for candidate in candidates:
            signal = candidate.signal
            if not isinstance(signal, EntrySignal):
                decisions.append(
                    AllocationDecision(
                        candidate=candidate,
                        cycle_id=cycle_id,
                        selected=True,
                        reason_code="non_entry_passthrough",
                        reason="Non-entry candidates bypass the capital allocator.",
                    )
                )
                continue
            stale_decision = self._reject_if_stale(candidate, current_time=current_time)
            if stale_decision is not None:
                decisions.append(stale_decision)
                continue
            plan, rejection = self._prepare_candidate_plan(
                candidate, current_time=current_time, open_state=open_state
            )
            if rejection is not None:
                decisions.append(rejection)
                continue
            assert plan is not None
            candidate_plans.append(plan)

        candidate_plans = self._suppress_weaker_duplicates(candidate_plans, decisions)
        candidate_plans = self._resolve_direction_conflicts(candidate_plans, decisions)

        for plan in sorted(
            candidate_plans,
            key=lambda item: (
                -item.priority_score,
                item.candidate.strategy_name,
                item.candidate.instrument,
            ),
        ):
            decision = self._allocate_candidate(
                plan, cycle_id=cycle_id, open_state=open_state, cycle_state=cycle_state
            )
            decisions.append(decision)
            if decision.selected:
                self._reserve_cycle_state(
                    plan=plan, decision=decision, cycle_state=cycle_state
                )

        for decision in decisions:
            if decision.cycle_id == "unassigned":
                decision.cycle_id = cycle_id

        self._persist_cycle_summary(
            cycle_id=cycle_id,
            received_at=current_time,
            decisions=decisions,
            open_state=open_state,
            cycle_state=cycle_state,
        )
        return decisions

    def _prepare_candidate_plan(
        self,
        candidate: SignalCandidate,
        *,
        current_time: datetime,
        open_state: dict[str, object],
    ) -> tuple[CandidatePlan | None, AllocationDecision | None]:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        broker = candidate.engine.broker
        requested_risk_percent = self._requested_risk_percent(candidate)

        try:
            account_summary = broker.get_account_summary()
        except Exception as exc:
            return None, self._reject_candidate(
                candidate,
                "account_equity_unavailable",
                "Broker account equity is unavailable; allocation failed closed for this cycle.",
                requested_risk_percent=requested_risk_percent,
                sizing_details={"error": str(exc)},
            )
        account_equity = float(account_summary.equity or 0.0)
        if account_equity <= 0:
            return None, self._reject_candidate(
                candidate,
                "account_equity_invalid",
                "Broker account equity is zero or negative; allocation failed closed for this cycle.",
                requested_risk_percent=requested_risk_percent,
                account_equity=account_equity,
            )

        try:
            broker_details = broker.get_market_details(signal.instrument)
            sizing_quote = broker.quote_risk_sized_order(
                signal.instrument,
                entry_price=self._entry_price(signal),
                risk_amount=account_equity * (requested_risk_percent / 100.0),
                stop_loss_price=signal.stop_loss_price,
                fallback_stop_distance=max(
                    self._entry_price(signal)
                    * self.settings.allocation_fallback_stop_distance_percent,
                    1e-9,
                ),
            )
        except Exception as exc:
            return None, self._reject_candidate(
                candidate,
                "broker_metadata_unavailable",
                "Broker market metadata is unavailable; allocation failed closed for this candidate.",
                requested_risk_percent=requested_risk_percent,
                account_equity=account_equity,
                sizing_details={"error": str(exc)},
            )

        if (
            not sizing_quote.sizing_available
            or sizing_quote.precision is BrokerSizingPrecision.UNSUPPORTED
        ):
            return None, self._reject_candidate(
                candidate,
                "sizing_quote_unavailable",
                sizing_quote.reason
                or "Broker sizing metadata is insufficient for coherent risk sizing.",
                requested_risk_percent=requested_risk_percent,
                account_equity=account_equity,
                broker_details=broker_details,
                sizing_details={
                    "sizing_quote": self._serialize_sizing_quote(sizing_quote)
                },
            )
        if (
            sizing_quote.precision is BrokerSizingPrecision.APPROXIMATE
            and broker.account_type.value == "LIVE"
        ):
            return None, self._reject_candidate(
                candidate,
                "approximate_sizing_unsupported",
                "Approximate sizing is not permitted for live allocation.",
                requested_risk_percent=requested_risk_percent,
                account_equity=account_equity,
                broker_details=broker_details,
                sizing_details={
                    "sizing_quote": self._serialize_sizing_quote(sizing_quote)
                },
            )

        entry_price = float(sizing_quote.entry_price)
        family_name = self._family_name(candidate)
        requested_size = max(float(sizing_quote.requested_size), 0.0)
        risk_amount = float(sizing_quote.risk_amount)
        sizing_method = str(sizing_quote.sizing_method or "unavailable")
        sizing_details = self._build_sizing_details(
            candidate, sizing_quote=sizing_quote
        )
        score_components = self._score_components(
            candidate,
            current_time=current_time,
            family_name=family_name,
            open_state=open_state,
            broker_details=broker_details,
        )
        priority_score = round(sum(score_components.values()), 6)
        currencies = self._currency_buckets(signal.instrument, broker_details)
        return (
            CandidatePlan(
                candidate=candidate,
                family_name=family_name,
                requested_risk_percent=requested_risk_percent,
                requested_size=requested_size,
                risk_amount=risk_amount,
                account_equity=account_equity,
                entry_price=entry_price,
                priority_score=priority_score,
                score_components=score_components,
                sizing_method=sizing_method,
                sizing_details=sizing_details,
                broker_details=broker_details,
                sizing_quote=sizing_quote,
                currencies=currencies,
            ),
            None,
        )

    def _allocate_candidate(
        self,
        plan: CandidatePlan,
        *,
        cycle_id: str,
        open_state: dict[str, object],
        cycle_state: dict[str, object],
    ) -> AllocationDecision:
        if (
            self._portfolio_position_count(open_state, cycle_state)
            >= self.settings.runtime_max_open_positions
        ):
            return self._reject(
                plan,
                "portfolio_position_limit",
                "Portfolio max open positions reached.",
                binding_budget="portfolio_open_positions",
            )
        if (
            self._strategy_position_count(
                plan.candidate.strategy_name, open_state, cycle_state
            )
            >= self.settings.runtime_max_positions_per_strategy
        ):
            return self._reject(
                plan,
                "strategy_position_limit",
                "Strategy max concurrent positions reached.",
                binding_budget="strategy_positions",
            )
        if (
            cycle_state["selected_positions"]
            >= self.settings.allocation_max_new_positions_per_cycle
        ):
            return self._reject(
                plan,
                "cycle_position_limit",
                "Allocation cycle max new-position count reached.",
                binding_budget="cycle_positions",
            )

        allocatable_risk, hard_risk_limit, binding_budget, budget_snapshot = (
            self._allocatable_risk_percent(
                plan,
                open_state=open_state,
                cycle_state=cycle_state,
            )
        )
        if allocatable_risk <= 0:
            return self._reject(
                plan,
                reason_code=f"{binding_budget}_exhausted"
                if binding_budget
                else "allocation_budget_exhausted",
                reason="No risk budget remains for this candidate.",
                binding_budget=binding_budget,
                broker_details=plan.broker_details,
                sizing_details={
                    **plan.sizing_details,
                    "budget_snapshot": budget_snapshot,
                },
            )

        risk_scale = (
            allocatable_risk / plan.requested_risk_percent
            if plan.requested_risk_percent > 0
            else 0.0
        )
        raw_size = plan.requested_size * risk_scale
        raw_notional = abs(raw_size * plan.entry_price)
        if raw_size <= 0 or raw_notional <= 0:
            return self._reject(
                plan,
                "size_zero",
                "Allocation reduced size to zero.",
                binding_budget=binding_budget,
            )

        gross_remaining_notional = self._gross_remaining_notional(
            plan.account_equity, open_state=open_state, cycle_state=cycle_state
        )
        max_trade_notional = self.settings.runtime_max_position_notional
        capped_notional = min(
            raw_notional, max_trade_notional, gross_remaining_notional
        )
        capped_size = (
            raw_size * (capped_notional / raw_notional)
            if raw_notional > 0
            else raw_size
        )
        capped_risk_percent = (
            allocatable_risk * (capped_size / raw_size)
            if raw_size > 0
            else allocatable_risk
        )
        capped_risk_amount = (
            plan.risk_amount * (capped_risk_percent / plan.requested_risk_percent)
            if plan.requested_risk_percent > 0
            else 0.0
        )
        if capped_size <= 0 or capped_notional <= 0:
            return self._reject(
                plan,
                "gross_exposure_limit",
                "Gross exposure budget would be exceeded.",
                binding_budget="gross_exposure",
            )

        normalized = self._normalize_size(
            plan=plan,
            requested_size=capped_size,
            requested_risk_percent=capped_risk_percent,
            requested_risk_amount=capped_risk_amount,
            hard_risk_limit_percent=hard_risk_limit,
        )
        if not normalized["accepted"]:
            return self._reject(
                plan,
                reason_code=str(normalized["reason_code"]),
                reason=str(normalized["reason"]),
                binding_budget=binding_budget,
                broker_details=plan.broker_details,
                sizing_details={
                    **plan.sizing_details,
                    **normalized,
                    "budget_snapshot": budget_snapshot,
                },
            )

        actual_size = float(normalized["normalized_size"])
        actual_risk_percent = float(normalized["allocated_risk_percent"])
        actual_risk_amount = float(normalized["allocated_risk_amount"])

        return AllocationDecision(
            candidate=plan.candidate,
            cycle_id=cycle_id,
            selected=True,
            reason_code="allocated",
            reason="Capital allocated by portfolio construction layer.",
            priority_score=plan.priority_score,
            requested_size=plan.requested_size,
            normalized_size=actual_size,
            requested_risk_percent=plan.requested_risk_percent,
            allocated_risk_percent=actual_risk_percent,
            risk_amount=actual_risk_amount,
            account_equity=plan.account_equity,
            sizing_method=plan.sizing_method,
            sizing_precision=plan.sizing_quote.precision.value,
            sizing_mode=plan.sizing_quote.mode.value,
            binding_budget=binding_budget,
            score_components=plan.score_components,
            sizing_details={
                **plan.sizing_details,
                "budget_snapshot": budget_snapshot,
                "binding_budget_is_hard": binding_budget is not None,
                "raw_size_after_budgets": round(capped_size, 8),
                "raw_notional_after_budgets": round(
                    abs(actual_size * plan.entry_price), 8
                ),
                **normalized,
            },
            broker_details=self._serialize_broker_details(plan.broker_details),
            notes=list(normalized.get("notes", [])),
            degraded=plan.sizing_quote.precision is BrokerSizingPrecision.APPROXIMATE,
        )

    def _build_sizing_details(
        self,
        candidate: SignalCandidate,
        *,
        sizing_quote: BrokerRiskSizingQuote,
    ) -> dict[str, object]:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        details = {
            "entry_price": round(float(sizing_quote.entry_price), 8),
            "requested_risk_percent": round(self._requested_risk_percent(candidate), 6),
            "risk_amount": round(float(sizing_quote.risk_amount), 6),
            "stop_distance_price": round(
                float(sizing_quote.stop_distance_price or 0.0), 8
            ),
            "risk_per_unit": round(float(sizing_quote.risk_per_unit or 0.0), 8),
            "sizing_precision": sizing_quote.precision.value,
            "sizing_mode": sizing_quote.mode.value,
            "sizing_quote": self._serialize_sizing_quote(sizing_quote),
            "stop_loss_price": signal.stop_loss_price,
            "take_profit_price": signal.take_profit_price,
            "expected_reward_risk": signal.expected_reward_risk,
            "volatility_estimate": signal.volatility_estimate,
        }
        if sizing_quote.precision is BrokerSizingPrecision.APPROXIMATE:
            details["degraded_mode"] = True
        return details

    def _normalize_size(
        self,
        *,
        plan: CandidatePlan,
        requested_size: float,
        requested_risk_percent: float,
        requested_risk_amount: float,
        hard_risk_limit_percent: float,
    ) -> dict[str, object]:
        normalization = plan.candidate.engine.broker.normalize_order_size(
            plan.candidate.instrument, requested_size
        )
        notes = list(normalization.notes)
        if normalization.accepted:
            normalized_size = normalization.normalized_size
            return {
                "accepted": True,
                "reason_code": "allocated",
                "reason": normalization.reason,
                "normalization_resized": abs(normalized_size - requested_size) > 1e-8,
                "normalized_size": round(normalized_size, 8),
                "allocated_risk_percent": round(
                    requested_risk_percent
                    * (normalized_size / max(requested_size, 1e-9)),
                    6,
                ),
                "allocated_risk_amount": round(
                    requested_risk_amount
                    * (normalized_size / max(requested_size, 1e-9)),
                    6,
                ),
                "minimum_deal_size": normalization.min_deal_size,
                "size_step": normalization.size_step,
                "normalization_details": normalization.details,
                "notes": notes,
            }

        if (
            normalization.reason_code == "below_min_size"
            and normalization.min_deal_size is not None
        ):
            round_up_size = normalization.min_deal_size
            if normalization.size_step is not None and normalization.size_step > 0:
                round_up_size = max(
                    normalization.min_deal_size,
                    self._round_up(
                        normalization.min_deal_size, normalization.size_step
                    ),
                )
            round_up_risk_percent = requested_risk_percent * (
                round_up_size / max(requested_size, 1e-9)
            )
            tolerance_multiplier = 1.0 + (
                self.settings.allocation_under_minimum_round_up_tolerance_percent
                / 100.0
            )
            if (
                round_up_risk_percent <= requested_risk_percent * tolerance_multiplier
                and round_up_risk_percent <= hard_risk_limit_percent
            ):
                notes.append("rounded_up_to_minimum_deal_size")
                return {
                    "accepted": True,
                    "reason_code": "allocated",
                    "reason": "Size rounded up to broker minimum deal size within tolerance.",
                    "normalization_resized": True,
                    "normalized_size": round(round_up_size, 8),
                    "allocated_risk_percent": round(round_up_risk_percent, 6),
                    "allocated_risk_amount": round(
                        requested_risk_amount
                        * (round_up_size / max(requested_size, 1e-9)),
                        6,
                    ),
                    "minimum_deal_size": normalization.min_deal_size,
                    "size_step": normalization.size_step,
                    "normalization_details": normalization.details,
                    "notes": notes,
                }

        return {
            "accepted": False,
            "reason_code": normalization.reason_code,
            "reason": normalization.reason,
            "normalization_resized": abs(normalization.normalized_size - requested_size)
            > 1e-8,
            "normalized_size": round(normalization.normalized_size, 8),
            "allocated_risk_percent": round(
                requested_risk_percent
                * (normalization.normalized_size / max(requested_size, 1e-9)),
                6,
            ),
            "allocated_risk_amount": round(
                requested_risk_amount
                * (normalization.normalized_size / max(requested_size, 1e-9)),
                6,
            ),
            "minimum_deal_size": normalization.min_deal_size,
            "size_step": normalization.size_step,
            "normalization_details": normalization.details,
            "notes": notes,
        }

    def _requested_risk_percent(self, candidate: SignalCandidate) -> float:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        raw = signal.risk_percent
        if raw in (None, 0):
            raw = self.settings.allocation_default_risk_per_trade_percent
        return max(float(raw), 0.0)

    def _allocatable_risk_percent(
        self,
        plan: CandidatePlan,
        *,
        open_state: dict[str, object],
        cycle_state: dict[str, object],
    ) -> tuple[float, float, str | None, dict[str, float]]:
        remaining = {
            "portfolio_risk": max(
                self.settings.runtime_max_open_risk_percent
                - float(open_state["total_risk"])
                - float(cycle_state["selected_risk"]),
                0.0,
            ),
            "cycle_risk": max(
                self.settings.allocation_max_new_risk_per_cycle_percent
                - float(cycle_state["selected_risk"]),
                0.0,
            ),
            "strategy_risk": max(
                self.settings.allocation_max_risk_per_strategy_percent
                - float(open_state["strategy_risk"][plan.candidate.strategy_name])
                - float(cycle_state["strategy_risk"][plan.candidate.strategy_name]),
                0.0,
            ),
            "family_risk": max(
                self.settings.allocation_max_risk_per_family_percent
                - float(open_state["family_risk"][plan.family_name])
                - float(cycle_state["family_risk"][plan.family_name]),
                0.0,
            ),
            "instrument_risk": max(
                self.settings.allocation_max_risk_per_instrument_percent
                - float(open_state["instrument_risk"][plan.candidate.instrument])
                - float(cycle_state["instrument_risk"][plan.candidate.instrument]),
                0.0,
            ),
        }
        for currency in plan.currencies:
            remaining[f"currency_{currency}"] = max(
                self.settings.allocation_max_risk_per_currency_percent
                - float(open_state["currency_risk"][currency])
                - float(cycle_state["currency_risk"][currency]),
                0.0,
            )
        binding_budget, available = min(remaining.items(), key=lambda item: item[1])
        return (
            min(plan.requested_risk_percent, available),
            available,
            binding_budget,
            {key: round(value, 6) for key, value in remaining.items()},
        )

    def _reserve_cycle_state(
        self,
        *,
        plan: CandidatePlan,
        decision: AllocationDecision,
        cycle_state: dict[str, object],
    ) -> None:
        cycle_state["selected_positions"] += 1
        cycle_state["selected_risk"] += decision.allocated_risk_percent
        cycle_state["selected_gross_notional"] += abs(
            decision.normalized_size * plan.entry_price
        )
        cycle_state["selected_strategy_positions"][plan.candidate.strategy_name] += 1
        cycle_state["strategy_risk"][plan.candidate.strategy_name] += (
            decision.allocated_risk_percent
        )
        cycle_state["family_risk"][plan.family_name] += decision.allocated_risk_percent
        cycle_state["instrument_risk"][plan.candidate.instrument] += (
            decision.allocated_risk_percent
        )
        for currency in plan.currencies:
            cycle_state["currency_risk"][currency] += (
                decision.allocated_risk_percent / max(len(plan.currencies), 1)
            )

    def _score_components(
        self,
        candidate: SignalCandidate,
        *,
        current_time: datetime,
        family_name: str,
        open_state: dict[str, object],
        broker_details: BrokerMarketDetails,
    ) -> dict[str, float]:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        confidence = max(
            0.0,
            min(candidate.confidence if candidate.confidence is not None else 0.5, 1.0),
        )
        signal_age_ms = max(
            (current_time - signal.signal_at.astimezone(UTC)).total_seconds() * 1000.0,
            0.0,
        )
        freshness = 1.0
        if self.settings.max_price_age_ms > 0:
            freshness = max(
                0.0,
                1.0
                - min(signal_age_ms, self.settings.max_price_age_ms)
                / self.settings.max_price_age_ms,
            )
        spread = (
            (signal.ask - signal.bid)
            if signal.bid is not None and signal.ask is not None
            else None
        )
        spread_score = 0.5
        if spread is not None and self.settings.max_spread_pips > 0:
            spread_score = max(
                0.0,
                1.0
                - min(spread, self.settings.max_spread_pips)
                / self.settings.max_spread_pips,
            )
        source_quality = 1.0 if candidate.source_tier == "TIER1" else 0.85
        reward_risk_score = 0.5
        if signal.expected_reward_risk is not None:
            reward_risk_score = max(0.0, min(signal.expected_reward_risk / 3.0, 1.0))
        diversification_penalty = 0.0
        if float(open_state["instrument_risk"][candidate.instrument]) > 0:
            diversification_penalty += 0.35
        if float(open_state["family_risk"][family_name]) > 0:
            diversification_penalty += 0.1
        for currency in self._currency_buckets(signal.instrument, broker_details):
            if float(open_state["currency_risk"][currency]) >= (
                self.settings.allocation_max_risk_per_currency_percent * 0.5
            ):
                diversification_penalty += 0.1
        diversification = max(0.0, 1.0 - diversification_penalty)
        return {
            "confidence": round(confidence * 0.30, 6),
            "freshness": round(freshness * 0.20, 6),
            "spread": round(spread_score * 0.15, 6),
            "source_quality": round(source_quality * 0.10, 6),
            "reward_risk": round(reward_risk_score * 0.10, 6),
            "diversification": round(diversification * 0.15, 6),
        }

    def _build_open_state(
        self, open_positions: list[Position], reserved_intents: list[TradeIntent]
    ) -> dict[str, object]:
        total_risk = 0.0
        total_gross_notional = 0.0
        strategy_risk: defaultdict[str, float] = defaultdict(float)
        family_risk: defaultdict[str, float] = defaultdict(float)
        instrument_risk: defaultdict[str, float] = defaultdict(float)
        currency_risk: defaultdict[str, float] = defaultdict(float)
        strategy_positions: defaultdict[str, int] = defaultdict(int)
        reserved_intent_ids: set[int] = set()

        for position in open_positions:
            risk_percent = float(position.risk_percent or 0.0)
            family_name = str(position.family_name or position.strategy_name)
            total_risk += risk_percent
            strategy_risk[position.strategy_name] += risk_percent
            family_risk[family_name] += risk_percent
            instrument_risk[position.instrument] += risk_percent
            strategy_positions[position.strategy_name] += 1
            mark_price = position.current_price or position.open_price
            total_gross_notional += abs((mark_price or 0.0) * position.size)
            currencies = self._currency_buckets(position.instrument, None)
            for currency in currencies:
                currency_risk[currency] += risk_percent / max(len(currencies), 1)
            if position.trade_intent_id is not None:
                reserved_intent_ids.add(position.trade_intent_id)

        for intent in reserved_intents:
            if intent.id is not None and intent.id in reserved_intent_ids:
                continue
            if intent.position_id is not None:
                continue
            risk_percent = float(
                intent.allocated_risk_percent or intent.proposed_risk_percent or 0.0
            )
            size = float(intent.allocated_size or intent.proposed_size or 0.0)
            price = float(intent.average_fill_price or intent.observed_price or 0.0)
            family_name = str(intent.family_name or intent.strategy_name)
            total_risk += risk_percent
            strategy_risk[intent.strategy_name] += risk_percent
            family_risk[family_name] += risk_percent
            instrument_risk[intent.instrument] += risk_percent
            strategy_positions[intent.strategy_name] += 1
            total_gross_notional += abs(price * size)
            currencies = self._currency_buckets(intent.instrument, None)
            for currency in currencies:
                currency_risk[currency] += risk_percent / max(len(currencies), 1)

        return {
            "total_risk": total_risk,
            "total_gross_notional": total_gross_notional,
            "strategy_risk": strategy_risk,
            "family_risk": family_risk,
            "instrument_risk": instrument_risk,
            "currency_risk": currency_risk,
            "strategy_positions": strategy_positions,
            "open_positions": len(open_positions)
            + len(
                [
                    intent
                    for intent in reserved_intents
                    if intent.position_id is None
                    and (intent.id is None or intent.id not in reserved_intent_ids)
                ]
            ),
        }

    def _portfolio_position_count(
        self, open_state: dict[str, object], cycle_state: dict[str, object]
    ) -> int:
        return int(open_state["open_positions"]) + int(
            cycle_state["selected_positions"]
        )

    def _strategy_position_count(
        self,
        strategy_name: str,
        open_state: dict[str, object],
        cycle_state: dict[str, object],
    ) -> int:
        return int(open_state["strategy_positions"][strategy_name]) + int(
            cycle_state["selected_strategy_positions"][strategy_name]
        )

    def _gross_remaining_notional(
        self,
        equity: float,
        *,
        open_state: dict[str, object],
        cycle_state: dict[str, object],
    ) -> float:
        gross_limit = equity * (
            self.settings.allocation_max_gross_exposure_percent / 100.0
        )
        used = float(open_state["total_gross_notional"]) + float(
            cycle_state["selected_gross_notional"]
        )
        return max(gross_limit - used, 0.0)

    def _suppress_weaker_duplicates(
        self, plans: list[CandidatePlan], decisions: list[AllocationDecision]
    ) -> list[CandidatePlan]:
        best_by_key: dict[tuple[str, str], CandidatePlan] = {}
        for plan in sorted(
            plans,
            key=lambda item: (
                -item.priority_score,
                item.candidate.strategy_name,
                item.candidate.instrument,
            ),
        ):
            signal = plan.candidate.signal
            assert isinstance(signal, EntrySignal)
            key = (plan.candidate.instrument, signal.direction.value)
            existing = best_by_key.get(key)
            if existing is None:
                best_by_key[key] = plan
                continue
            decisions.append(
                self._reject(
                    plan,
                    "weaker_duplicate",
                    "A stronger same-direction signal already exists for this instrument in the current allocation cycle.",
                )
            )
        return list(best_by_key.values())

    def _resolve_direction_conflicts(
        self, plans: list[CandidatePlan], decisions: list[AllocationDecision]
    ) -> list[CandidatePlan]:
        grouped: defaultdict[str, list[CandidatePlan]] = defaultdict(list)
        for plan in plans:
            grouped[plan.candidate.instrument].append(plan)
        selected: list[CandidatePlan] = []
        for instrument, entries in grouped.items():
            if len(entries) == 1:
                selected.extend(entries)
                continue
            ranked = sorted(
                entries,
                key=lambda item: (-item.priority_score, item.candidate.strategy_name),
            )
            selected.append(ranked[0])
            for plan in ranked[1:]:
                decisions.append(
                    self._reject(
                        plan,
                        "direction_conflict",
                        f"A stronger conflicting signal was selected for {instrument}.",
                    )
                )
        return selected

    def _reject_if_stale(
        self, candidate: SignalCandidate, *, current_time: datetime
    ) -> AllocationDecision | None:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        age_seconds = (current_time - signal.signal_at.astimezone(UTC)).total_seconds()
        if age_seconds <= self.settings.trade_allocator_signal_stale_after_seconds:
            return None
        return AllocationDecision(
            candidate=candidate,
            cycle_id="unassigned",
            selected=False,
            reason_code="stale_signal",
            reason=(
                f"Signal age {round(age_seconds, 2)}s exceeds allocator limit "
                f"{self.settings.trade_allocator_signal_stale_after_seconds}s."
            ),
            requested_risk_percent=self._requested_risk_percent(candidate),
        )

    def _reject_candidate(
        self,
        candidate: SignalCandidate,
        reason_code: str,
        reason: str,
        *,
        requested_risk_percent: float,
        account_equity: float = 0.0,
        broker_details: BrokerMarketDetails | None = None,
        sizing_details: dict[str, object] | None = None,
    ) -> AllocationDecision:
        return AllocationDecision(
            candidate=candidate,
            cycle_id="unassigned",
            selected=False,
            reason_code=reason_code,
            reason=reason,
            requested_risk_percent=requested_risk_percent,
            account_equity=account_equity,
            sizing_precision=(
                str((sizing_details or {}).get("sizing_quote", {}).get("precision"))
                if sizing_details is not None
                else "UNSUPPORTED"
            )
            or "UNSUPPORTED",
            sizing_mode=(
                str((sizing_details or {}).get("sizing_quote", {}).get("mode"))
                if sizing_details is not None
                else "UNSUPPORTED"
            )
            or "UNSUPPORTED",
            sizing_details=sizing_details or {},
            broker_details=self._serialize_broker_details(broker_details)
            if broker_details is not None
            else {},
            degraded=((sizing_details or {}).get("degraded_mode") is True),
        )

    def _reject(
        self,
        plan: CandidatePlan,
        reason_code: str,
        reason: str,
        *,
        binding_budget: str | None = None,
        broker_details: BrokerMarketDetails | None = None,
        sizing_details: dict[str, object] | None = None,
    ) -> AllocationDecision:
        return AllocationDecision(
            candidate=plan.candidate,
            cycle_id="unassigned",
            selected=False,
            reason_code=reason_code,
            reason=reason,
            priority_score=plan.priority_score,
            requested_size=plan.requested_size,
            requested_risk_percent=plan.requested_risk_percent,
            account_equity=plan.account_equity,
            sizing_method=plan.sizing_method,
            sizing_precision=plan.sizing_quote.precision.value,
            sizing_mode=plan.sizing_quote.mode.value,
            binding_budget=binding_budget,
            score_components=plan.score_components,
            sizing_details=sizing_details or dict(plan.sizing_details),
            broker_details=self._serialize_broker_details(
                broker_details or plan.broker_details
            ),
            degraded=plan.sizing_quote.precision is BrokerSizingPrecision.APPROXIMATE,
        )

    def _entry_price(self, signal: EntrySignal) -> float:
        if signal.direction.value == "BUY" and signal.ask is not None:
            return signal.ask
        if signal.direction.value == "SELL" and signal.bid is not None:
            return signal.bid
        return signal.observed_price

    def _family_name(self, candidate: SignalCandidate) -> str:
        metadata = candidate.metadata
        family_name = getattr(metadata, "family_name", None)
        return str(family_name or candidate.strategy_name)

    def _persist_cycle_summary(
        self,
        *,
        cycle_id: str,
        received_at: datetime,
        decisions: list[AllocationDecision],
        open_state: dict[str, object],
        cycle_state: dict[str, object],
    ) -> None:
        entry_decisions = [
            decision
            for decision in decisions
            if isinstance(decision.candidate.signal, EntrySignal)
        ]
        if not entry_decisions:
            return
        binding_budget_counts: defaultdict[str, int] = defaultdict(int)
        rejection_reason_counts: defaultdict[str, int] = defaultdict(int)
        resized_candidate_count = 0
        degraded_candidate_count = 0
        blocked_unsupported_sizing_count = 0
        blocked_approximate_live_count = 0
        blocked_under_minimum_size_count = 0
        blocked_budget_count = 0
        blocked_conflict_count = 0
        for decision in entry_decisions:
            if decision.binding_budget:
                binding_budget_counts[decision.binding_budget] += 1
            if not decision.selected:
                rejection_reason_counts[decision.reason_code] += 1
            raw_after_budgets = float(
                (decision.sizing_details or {}).get("raw_size_after_budgets") or 0.0
            )
            if (
                raw_after_budgets > 0
                and abs(raw_after_budgets - float(decision.normalized_size or 0.0))
                > 1e-8
            ):
                resized_candidate_count += 1
            if decision.degraded:
                degraded_candidate_count += 1
            if decision.reason_code in {
                "sizing_quote_unavailable",
                "broker_metadata_unavailable",
            }:
                blocked_unsupported_sizing_count += 1
            if decision.reason_code == "approximate_sizing_unsupported":
                blocked_approximate_live_count += 1
            if decision.reason_code in {"below_min_size", "size_rounded_to_zero"}:
                blocked_under_minimum_size_count += 1
            if decision.reason_code.endswith("_exhausted") or decision.reason_code in {
                "portfolio_position_limit",
                "strategy_position_limit",
                "cycle_position_limit",
                "gross_exposure_limit",
            }:
                blocked_budget_count += 1
            if decision.reason_code in {"weaker_duplicate", "direction_conflict"}:
                blocked_conflict_count += 1
        remaining_portfolio_risk = max(
            self.settings.runtime_max_open_risk_percent
            - float(open_state["total_risk"])
            - float(cycle_state["selected_risk"]),
            0.0,
        )
        allocation_cycle = AllocationCycle(
            cycle_id=cycle_id,
            received_at=received_at,
            completed_at=utc_now(),
            candidate_count=len(entry_decisions),
            approved_count=len(
                [decision for decision in entry_decisions if decision.selected]
            ),
            rejected_count=len(
                [decision for decision in entry_decisions if not decision.selected]
            ),
            total_requested_risk_percent=round(
                sum(decision.requested_risk_percent for decision in entry_decisions), 6
            ),
            total_allocated_risk_percent=round(
                sum(
                    decision.allocated_risk_percent
                    for decision in entry_decisions
                    if decision.selected
                ),
                6,
            ),
            remaining_portfolio_risk_percent=round(remaining_portfolio_risk, 6),
            resized_candidate_count=resized_candidate_count,
            degraded_candidate_count=degraded_candidate_count,
            blocked_unsupported_sizing_count=blocked_unsupported_sizing_count,
            blocked_approximate_live_count=blocked_approximate_live_count,
            blocked_under_minimum_size_count=blocked_under_minimum_size_count,
            blocked_budget_count=blocked_budget_count,
            blocked_conflict_count=blocked_conflict_count,
            binding_budget_counts=dict(binding_budget_counts),
            rejection_reason_counts=dict(rejection_reason_counts),
            details={
                "portfolio_risk_before_cycle": round(
                    float(open_state["total_risk"]), 6
                ),
                "portfolio_risk_reserved_by_cycle": round(
                    float(cycle_state["selected_risk"]), 6
                ),
                "portfolio_gross_notional_before_cycle": round(
                    float(open_state["total_gross_notional"]), 6
                ),
                "portfolio_gross_notional_reserved_by_cycle": round(
                    float(cycle_state["selected_gross_notional"]), 6
                ),
                "degraded": degraded_candidate_count > 0,
            },
        )
        self.trade_service.record_allocation_cycle(allocation_cycle)
        domain_event_service.record_event(
            event_type="allocation.cycle_completed",
            category="allocation",
            severity="warning" if degraded_candidate_count > 0 else "info",
            source="capital_allocator_service.allocate",
            title="Allocation cycle completed",
            message=f"Allocation cycle {cycle_id} evaluated {len(entry_decisions)} candidates.",
            payload_json={
                "cycle_id": cycle_id,
                "candidate_count": allocation_cycle.candidate_count,
                "approved_count": allocation_cycle.approved_count,
                "rejected_count": allocation_cycle.rejected_count,
                "total_requested_risk_percent": allocation_cycle.total_requested_risk_percent,
                "total_allocated_risk_percent": allocation_cycle.total_allocated_risk_percent,
                "remaining_portfolio_risk_percent": allocation_cycle.remaining_portfolio_risk_percent,
                "binding_budget_counts": allocation_cycle.binding_budget_counts,
                "rejection_reason_counts": allocation_cycle.rejection_reason_counts,
                "degraded": allocation_cycle.details.get("degraded", False),
            },
            created_at=allocation_cycle.completed_at,
        )

    def _currency_buckets(
        self, instrument: str, broker_details: BrokerMarketDetails | None
    ) -> tuple[str, ...]:
        base = broker_details.base_currency if broker_details is not None else None
        quote = broker_details.quote_currency if broker_details is not None else None
        if base and quote:
            return (base.upper(), quote.upper())
        definition = self._instrument_index.get(instrument)
        symbol = definition.symbol if definition is not None else ""
        if len(symbol) == 6 and symbol.isalpha():
            return (symbol[:3].upper(), symbol[3:].upper())
        return ()

    @staticmethod
    def _round_up(value: float, step: float) -> float:
        rounded_down = floor(value / step) * step
        if abs(rounded_down - value) < 1e-9:
            return rounded_down
        return rounded_down + step

    @staticmethod
    def _serialize_broker_details(
        details: BrokerMarketDetails | None,
    ) -> dict[str, object]:
        if details is None:
            return {}
        return {
            "min_deal_size": details.min_deal_size,
            "size_step": details.size_step,
            "min_normal_stop_or_limit_distance": details.min_normal_stop_or_limit_distance,
            "base_currency": details.base_currency,
            "quote_currency": details.quote_currency,
            "metadata": details.metadata,
        }

    @staticmethod
    def _serialize_sizing_quote(quote: BrokerRiskSizingQuote) -> dict[str, object]:
        return {
            "precision": quote.precision.value,
            "mode": quote.mode.value,
            "sizing_available": quote.sizing_available,
            "reason_code": quote.reason_code,
            "reason": quote.reason,
            "entry_price": quote.entry_price,
            "risk_amount": quote.risk_amount,
            "requested_size": quote.requested_size,
            "normalized_size": quote.normalized_size,
            "risk_per_unit": quote.risk_per_unit,
            "stop_distance_price": quote.stop_distance_price,
            "sizing_method": quote.sizing_method,
            "min_stop_distance": quote.min_stop_distance,
            "normalization": {
                "accepted": quote.normalization.accepted,
                "reason_code": quote.normalization.reason_code,
                "reason": quote.normalization.reason,
                "normalized_size": quote.normalization.normalized_size,
                "min_deal_size": quote.normalization.min_deal_size,
                "size_step": quote.normalization.size_step,
                "details": quote.normalization.details,
                "notes": quote.normalization.notes,
            }
            if quote.normalization is not None
            else None,
            "details": quote.details,
        }
