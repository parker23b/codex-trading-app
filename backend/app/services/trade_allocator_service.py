from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.core.signals import EntrySignal, SignalCandidate, TradeAllocationDecision
from app.models.trade import Position
from app.services.trade_service import TradeService


class TradeAllocatorService:
    """Deprecated legacy allocator retained only for backward compatibility tests."""

    def __init__(
        self,
        session: Session | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()

    def allocate(
        self,
        candidates: list[SignalCandidate],
        *,
        received_at: datetime | None = None,
    ) -> list[TradeAllocationDecision]:
        if self.session is None:
            raise ValueError(
                "A database session is required to allocate trade candidates."
            )

        if not candidates:
            return []

        trade_service = TradeService(self.session)
        open_positions = trade_service.list_positions()
        current_time = self._as_utc(received_at) or datetime.now(UTC)

        decisions: list[TradeAllocationDecision] = []
        passthrough: list[TradeAllocationDecision] = []
        entry_scored: list[tuple[SignalCandidate, float]] = []

        for candidate in candidates:
            if not isinstance(candidate.signal, EntrySignal):
                passthrough.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=True,
                        reason_code="non_entry_passthrough",
                        reason="Non-entry candidates bypass the trade allocator.",
                    )
                )
                continue

            stale_decision = self._reject_if_stale(
                candidate=candidate, now=current_time
            )
            if stale_decision is not None:
                decisions.append(stale_decision)
                continue

            if (
                self._instrument_open_position_count(
                    open_positions, candidate.instrument
                )
                >= self.settings.trade_allocator_max_open_positions_per_instrument
            ):
                decisions.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=False,
                        reason_code="instrument_exposure_limit",
                        reason="Instrument already has the maximum allowed open exposure.",
                        score=0.0,
                    )
                )
                continue

            score = self._score_candidate(candidate=candidate, now=current_time)
            entry_scored.append((candidate, score))

        scored_by_direction = self._suppress_weaker_duplicates(entry_scored, decisions)
        shortlisted = self._resolve_direction_conflicts(scored_by_direction, decisions)
        decisions.extend(
            self._apply_capacity_limits(shortlisted, open_positions=open_positions)
        )
        decisions.extend(passthrough)
        return decisions

    def _reject_if_stale(
        self,
        *,
        candidate: SignalCandidate,
        now: datetime,
    ) -> TradeAllocationDecision | None:
        signal = candidate.signal
        if not isinstance(signal, EntrySignal):
            return None
        age_seconds = (now - self._as_utc(signal.signal_at)).total_seconds()
        if age_seconds <= self.settings.trade_allocator_signal_stale_after_seconds:
            return None
        return TradeAllocationDecision(
            candidate=candidate,
            selected=False,
            reason_code="stale_signal",
            reason=(
                f"Signal age {round(age_seconds, 2)}s exceeds allocator limit "
                f"{self.settings.trade_allocator_signal_stale_after_seconds}s."
            ),
            score=0.0,
        )

    @staticmethod
    def _instrument_open_position_count(
        open_positions: list[Position], instrument: str
    ) -> int:
        return len(
            [
                position
                for position in open_positions
                if position.instrument == instrument and position.is_open
            ]
        )

    def _suppress_weaker_duplicates(
        self,
        scored_candidates: list[tuple[SignalCandidate, float]],
        decisions: list[TradeAllocationDecision],
    ) -> dict[tuple[str, str], tuple[SignalCandidate, float]]:
        best_by_key: dict[tuple[str, str], tuple[SignalCandidate, float]] = {}
        for candidate, score in sorted(
            scored_candidates,
            key=lambda item: (
                -item[1],
                self._signal_time(item[0]),
                item[0].strategy_name,
            ),
        ):
            signal = candidate.signal
            assert isinstance(signal, EntrySignal)
            key = (candidate.instrument, signal.direction.value)
            existing = best_by_key.get(key)
            if existing is None:
                best_by_key[key] = (candidate, score)
                continue
            decisions.append(
                TradeAllocationDecision(
                    candidate=candidate,
                    selected=False,
                    reason_code="weaker_duplicate",
                    reason="A stronger signal already exists for this instrument and direction in the current allocation cycle.",
                    score=score,
                )
            )
        return best_by_key

    def _resolve_direction_conflicts(
        self,
        best_by_direction: dict[tuple[str, str], tuple[SignalCandidate, float]],
        decisions: list[TradeAllocationDecision],
    ) -> list[tuple[SignalCandidate, float]]:
        grouped: dict[str, list[tuple[SignalCandidate, float]]] = defaultdict(list)
        for (instrument, _direction), value in best_by_direction.items():
            grouped[instrument].append(value)

        selected: list[tuple[SignalCandidate, float]] = []
        for instrument, entries in grouped.items():
            if len(entries) == 1:
                selected.extend(entries)
                continue
            ranked = sorted(
                entries,
                key=lambda item: (
                    -item[1],
                    self._signal_time(item[0]),
                    item[0].strategy_name,
                ),
            )
            winner = ranked[0]
            selected.append(winner)
            for candidate, score in ranked[1:]:
                decisions.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=False,
                        reason_code="direction_conflict",
                        reason=f"A stronger conflicting signal was selected for {instrument}.",
                        score=score,
                    )
                )
        return selected

    def _apply_capacity_limits(
        self,
        shortlisted: list[tuple[SignalCandidate, float]],
        *,
        open_positions: list[Position],
    ) -> list[TradeAllocationDecision]:
        decisions: list[TradeAllocationDecision] = []
        ranked = sorted(
            shortlisted,
            key=lambda item: (
                -item[1],
                self._signal_time(item[0]),
                item[0].strategy_name,
            ),
        )
        selected_count = 0
        open_risk_percent = sum(
            position.risk_percent or 0.0
            for position in open_positions
            if position.is_open
        )
        strategy_open_counts = defaultdict(
            int,
            {
                strategy_name: len(
                    [
                        position
                        for position in open_positions
                        if position.strategy_name == strategy_name and position.is_open
                    ]
                )
                for strategy_name in {
                    position.strategy_name for position in open_positions
                }
            },
        )
        strategy_selected_counts: dict[str, int] = defaultdict(int)

        for candidate, score in ranked:
            signal = candidate.signal
            assert isinstance(signal, EntrySignal)
            strategy_name = candidate.strategy_name
            risk_percent = self._candidate_risk_percent(candidate)

            if selected_count >= self.settings.trade_allocator_max_decisions_per_cycle:
                decisions.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=False,
                        reason_code="cycle_capacity",
                        reason="Trade allocator decision cap reached for this cycle.",
                        score=score,
                    )
                )
                continue

            current_strategy_count = (
                strategy_open_counts[strategy_name]
                + strategy_selected_counts[strategy_name]
            )
            if (
                current_strategy_count
                >= self.settings.runtime_max_positions_per_strategy
            ):
                decisions.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=False,
                        reason_code="strategy_capacity",
                        reason="Strategy concurrent trade capacity is already fully used.",
                        score=score,
                    )
                )
                continue

            projected_open_risk = open_risk_percent + risk_percent
            if projected_open_risk > self.settings.runtime_max_open_risk_percent:
                decisions.append(
                    TradeAllocationDecision(
                        candidate=candidate,
                        selected=False,
                        reason_code="open_risk_capacity",
                        reason="Projected open risk would exceed the configured portfolio risk cap.",
                        score=score,
                    )
                )
                continue

            decisions.append(
                TradeAllocationDecision(
                    candidate=candidate,
                    selected=True,
                    reason_code="selected",
                    reason="Signal selected by trade allocator.",
                    score=score,
                )
            )
            selected_count += 1
            strategy_selected_counts[strategy_name] += 1
            open_risk_percent = projected_open_risk

        return decisions

    def _score_candidate(
        self,
        *,
        candidate: SignalCandidate,
        now: datetime,
    ) -> float:
        signal = candidate.signal
        assert isinstance(signal, EntrySignal)
        confidence = max(
            0.0,
            min(candidate.confidence if candidate.confidence is not None else 0.5, 1.0),
        )
        last_price_age_ms = max(
            (now - self._as_utc(signal.signal_at)).total_seconds() * 1000, 0.0
        )
        freshness = 0.0
        if self.settings.max_price_age_ms > 0:
            freshness = max(
                0.0,
                1.0
                - min(last_price_age_ms, self.settings.max_price_age_ms)
                / self.settings.max_price_age_ms,
            )
        spread = None
        if signal.bid is not None and signal.ask is not None:
            spread = signal.ask - signal.bid
        spread_score = 0.5
        if spread is not None and self.settings.max_spread_pips > 0:
            spread_score = max(
                0.0,
                1.0
                - min(spread, self.settings.max_spread_pips)
                / self.settings.max_spread_pips,
            )
        source_tier_bonus = 1.0 if candidate.source_tier == "TIER1" else 0.9
        score = (
            (confidence * 0.45) + (freshness * 0.35) + (spread_score * 0.2)
        ) * source_tier_bonus
        return round(score, 6)

    @staticmethod
    def _signal_time(candidate: SignalCandidate) -> datetime:
        signal = candidate.signal
        if isinstance(signal, EntrySignal):
            return signal.signal_at.astimezone(UTC)
        return datetime.max.replace(tzinfo=UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.astimezone(UTC)

    @staticmethod
    def _candidate_risk_percent(candidate: SignalCandidate) -> float:
        signal = candidate.signal
        if isinstance(signal, EntrySignal) and signal.risk_percent is not None:
            return float(signal.risk_percent)
        return 0.0
