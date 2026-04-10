from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterator

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.instrument_catalog import list_market_instruments
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.models.trade import Execution, ExecutionStatus, Position
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StreamingPlan:
    instruments: tuple[str, ...]
    pinned_instruments: tuple[str, ...]
    capped_instruments: tuple[str, ...]
    asset_class_usage: dict[str, int]


@dataclass(frozen=True, slots=True)
class Tier2RefreshPlan:
    instruments: tuple[str, ...]
    streamed_instruments: tuple[str, ...]
    capped_instruments: tuple[str, ...]


class WatchlistService:
    PENDING_EXECUTION_STATUSES = {
        ExecutionStatus.SIGNAL_GENERATED.value,
        ExecutionStatus.RISK_APPROVED.value,
        ExecutionStatus.CLOSE_REQUESTED.value,
        ExecutionStatus.ORDER_SUBMITTED.value,
        ExecutionStatus.ORDER_ACKNOWLEDGED.value,
        ExecutionStatus.FILL_PARTIAL.value,
    }
    PIN_PRIORITY = 100.0
    SEED_PRIORITY = 75.0
    RUNTIME_PRIORITY = 50.0
    TIER2_SEED_PRIORITY = 25.0

    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self._asset_class_by_instrument = {
            instrument.epic: instrument.category
            for instrument in list_market_instruments()
        }
        self._activity_level_by_instrument = {
            instrument.epic: instrument.activity_level
            for instrument in list_market_instruments()
        }

    def get_streaming_plan(self) -> StreamingPlan:
        with self._session_scope() as session:
            now = self._now()
            self._sync_system_entries(session=session, now=now)
            entries = list(
                session.exec(
                    select(WatchlistEntry)
                    .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                    .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
                ).all()
            )
            entries.sort(
                key=lambda entry: (
                    0 if entry.pinned else 1,
                    -entry.priority_score,
                    entry.assigned_at,
                    entry.instrument,
                )
            )

            max_instruments = self.settings.ig_streaming_max_instruments
            asset_budgets = {
                asset_class.upper(): budget
                for asset_class, budget in self.settings.ig_streaming_asset_class_slot_budgets.items()
            }
            asset_usage: defaultdict[str, int] = defaultdict(int)
            selected: list[str] = []
            pinned: list[str] = []
            capped: list[str] = []

            for entry in entries:
                asset_class = (entry.asset_class or "UNCLASSIFIED").upper()
                if entry.pinned:
                    selected.append(entry.instrument)
                    pinned.append(entry.instrument)
                    asset_usage[asset_class] += 1
                    continue

                if max_instruments > 0 and len(selected) >= max_instruments:
                    capped.append(entry.instrument)
                    continue

                budget = asset_budgets.get(asset_class)
                if budget is not None and asset_usage[asset_class] >= budget:
                    capped.append(entry.instrument)
                    continue

                selected.append(entry.instrument)
                asset_usage[asset_class] += 1

            for instrument in selected:
                entry = next((candidate for candidate in entries if candidate.instrument == instrument), None)
                if entry is not None:
                    entry.last_streamed_at = now
                    entry.updated_at = now
                    session.add(entry)
            session.commit()

            return StreamingPlan(
                instruments=tuple(selected),
                pinned_instruments=tuple(pinned),
                capped_instruments=tuple(capped),
                asset_class_usage=dict(asset_usage),
            )

    def get_tier2_refresh_plan(self) -> Tier2RefreshPlan:
        streaming_plan = self.get_streaming_plan()
        streamed = set(streaming_plan.instruments)
        with self._session_scope() as session:
            now = self._now()
            self._sync_tier2_seed_entries(session=session, now=now)
            tier2_entries = list(
                session.exec(
                    select(WatchlistEntry)
                    .where(WatchlistEntry.tier == WatchlistTier.TIER2.value)
                    .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
                ).all()
            )
            tier2_entries.sort(
                key=lambda entry: (
                    self._as_utc(entry.last_refreshed_at) or datetime(1970, 1, 1, tzinfo=UTC),
                    -entry.priority_score,
                    entry.instrument,
                )
            )

            candidates: list[str] = []
            for instrument in streaming_plan.capped_instruments:
                if instrument not in streamed and instrument not in candidates:
                    candidates.append(instrument)

            stale_cutoff = now - timedelta(seconds=self.settings.tier2_refresh_stale_after_seconds)
            for entry in tier2_entries:
                if entry.instrument in streamed or entry.instrument in candidates:
                    continue
                last_refreshed_at = entry.last_refreshed_at
                if last_refreshed_at is not None:
                    last_refreshed_at = self._as_utc(last_refreshed_at)
                if last_refreshed_at is not None and last_refreshed_at > stale_cutoff:
                    continue
                candidates.append(entry.instrument)

            return Tier2RefreshPlan(
                instruments=tuple(candidates[: self.settings.tier2_refresh_batch_size]),
                streamed_instruments=streaming_plan.instruments,
                capped_instruments=streaming_plan.capped_instruments,
            )

    def promote_instrument(
        self,
        *,
        instrument: str,
        promoted_at: datetime,
        expires_at: datetime,
        score: float,
        requested_frequency: str,
        reason: str = "promotion_accepted",
    ) -> None:
        with self._session_scope() as session:
            existing = session.exec(select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)).first()
            priority_score = max(self.SEED_PRIORITY + 5.0, round(score * 100, 2))
            self._upsert_entry(
                session=session,
                now=promoted_at,
                instrument=instrument,
                existing=existing,
                pinned=False,
                priority_score=priority_score,
                reason=reason,
            )
            entry = session.exec(select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)).first()
            if entry is None:
                return
            entry.promotion_expires_at = expires_at
            entry.requested_frequency = requested_frequency
            entry.updated_at = promoted_at
            session.add(entry)
            session.commit()

    def record_tier2_refresh(self, *, instrument: str, refreshed_at: datetime) -> None:
        with self._session_scope() as session:
            entry = session.exec(select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)).first()
            if entry is None:
                entry = WatchlistEntry(
                    instrument=instrument,
                    tier=WatchlistTier.TIER2.value,
                    status=WatchlistStatus.ACTIVE.value,
                    asset_class=self._asset_class_by_instrument.get(instrument),
                    pinned=False,
                    reason="tier2_seed",
                    priority_score=self._tier2_priority(instrument),
                    assigned_at=refreshed_at,
                    updated_at=refreshed_at,
                )
            entry.last_refreshed_at = refreshed_at
            entry.updated_at = refreshed_at
            session.add(entry)
            session.commit()

    def _sync_system_entries(self, *, session: Session, now: datetime) -> None:
        existing_entries = {
            entry.instrument: entry
            for entry in session.exec(select(WatchlistEntry)).all()
        }
        pinned_instruments = self._collect_pinned_instruments(session=session)
        runtime_instruments = set(runtime_manager.list_active_instruments())
        seed_instruments = set(self.settings.ig_streaming_seed_instruments)
        promoted_instruments = {
            instrument
            for instrument, entry in existing_entries.items()
            if entry.reason == "promotion_accepted"
            and entry.status == WatchlistStatus.ACTIVE.value
            and self._promotion_still_valid(entry=entry, now=now)
        }

        desired_active = set(pinned_instruments) | runtime_instruments | seed_instruments | promoted_instruments

        for instrument, reason in pinned_instruments.items():
            self._upsert_entry(
                session=session,
                now=now,
                instrument=instrument,
                existing=existing_entries.get(instrument),
                pinned=True,
                priority_score=self.PIN_PRIORITY,
                reason=reason,
            )

        for instrument in runtime_instruments:
            if instrument in pinned_instruments:
                continue
            self._upsert_entry(
                session=session,
                now=now,
                instrument=instrument,
                existing=existing_entries.get(instrument),
                pinned=False,
                priority_score=self.RUNTIME_PRIORITY,
                reason="runtime_active",
            )

        for instrument in seed_instruments:
            if instrument in pinned_instruments or instrument in runtime_instruments:
                continue
            self._upsert_entry(
                session=session,
                now=now,
                instrument=instrument,
                existing=existing_entries.get(instrument),
                pinned=False,
                priority_score=self.SEED_PRIORITY,
                reason="seed_watchlist",
            )

        for instrument, entry in existing_entries.items():
            if instrument in desired_active:
                continue
            if entry.pinned:
                entry.pinned = False
            if entry.status != WatchlistStatus.ACTIVE.value:
                continue
            min_residency_until = self._as_utc(entry.min_residency_until)
            if min_residency_until is not None and min_residency_until > now:
                continue
            entry.status = WatchlistStatus.COOLDOWN.value
            entry.cooldown_until = now + timedelta(seconds=self.settings.ig_streaming_demotion_cooldown_seconds)
            entry.updated_at = now
            session.add(entry)

        session.commit()

    def _upsert_entry(
        self,
        *,
        session: Session,
        now: datetime,
        instrument: str,
        existing: WatchlistEntry | None,
        pinned: bool,
        priority_score: float,
        reason: str,
    ) -> WatchlistEntry:
        if existing is None:
            entry = WatchlistEntry(
                instrument=instrument,
                tier=WatchlistTier.TIER1.value,
                status=WatchlistStatus.ACTIVE.value,
                asset_class=self._asset_class_by_instrument.get(instrument),
                pinned=pinned,
                reason=reason,
                priority_score=priority_score,
                requested_frequency=self.settings.ig_streaming_requested_frequency,
                assigned_at=now,
                min_residency_until=now + timedelta(seconds=self.settings.ig_streaming_min_tier1_residency_seconds),
                updated_at=now,
            )
        else:
            entry = existing
            cooldown_until = self._as_utc(entry.cooldown_until)
            if entry.status == WatchlistStatus.COOLDOWN.value and cooldown_until and cooldown_until > now and pinned:
                logger.info(
                    "Pinned instrument bypassed watchlist cooldown",
                    extra={"instrument": instrument, "cooldown_until": cooldown_until.isoformat()},
                )
            entry.tier = WatchlistTier.TIER1.value
            entry.status = WatchlistStatus.ACTIVE.value
            entry.asset_class = self._asset_class_by_instrument.get(instrument)
            entry.pinned = pinned
            entry.reason = reason
            entry.priority_score = max(entry.priority_score, priority_score)
            entry.requested_frequency = self.settings.ig_streaming_requested_frequency
            entry.cooldown_until = None
            min_residency_until = self._as_utc(entry.min_residency_until)
            if min_residency_until is None or min_residency_until < now:
                entry.min_residency_until = now + timedelta(seconds=self.settings.ig_streaming_min_tier1_residency_seconds)
            if reason != "promotion_accepted":
                entry.promotion_expires_at = None
            entry.updated_at = now

        session.add(entry)
        return entry

    def _sync_tier2_seed_entries(self, *, session: Session, now: datetime) -> None:
        existing_entries = {
            entry.instrument: entry
            for entry in session.exec(select(WatchlistEntry)).all()
        }
        for instrument in self.settings.tier2_seed_instruments:
            existing = existing_entries.get(instrument)
            if existing is None:
                entry = WatchlistEntry(
                    instrument=instrument,
                    tier=WatchlistTier.TIER2.value,
                    status=WatchlistStatus.ACTIVE.value,
                    asset_class=self._asset_class_by_instrument.get(instrument),
                    pinned=False,
                    reason="tier2_seed",
                    priority_score=self._tier2_priority(instrument),
                    requested_frequency=None,
                    assigned_at=now,
                    updated_at=now,
                )
            else:
                entry = existing
                if entry.tier != WatchlistTier.TIER1.value:
                    entry.tier = WatchlistTier.TIER2.value
                entry.status = WatchlistStatus.ACTIVE.value
                entry.asset_class = self._asset_class_by_instrument.get(instrument)
                entry.reason = entry.reason or "tier2_seed"
                entry.priority_score = max(entry.priority_score, self._tier2_priority(instrument))
                entry.updated_at = now
            session.add(entry)
        session.commit()

    def _collect_pinned_instruments(self, *, session: Session) -> dict[str, str]:
        reasons: dict[str, set[str]] = defaultdict(set)
        positions = session.exec(select(Position).where(Position.is_open.is_(True))).all()
        for position in positions:
            reasons[position.instrument].add("open_position")

        pending_executions = session.exec(
            select(Execution).where(Execution.status.in_(tuple(self.PENDING_EXECUTION_STATUSES)))
        ).all()
        for execution in pending_executions:
            reasons[execution.instrument].add("pending_execution")

        return {
            instrument: ",".join(sorted(reason_set))
            for instrument, reason_set in reasons.items()
        }

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        if self.session is not None:
            yield self.session
            return
        with Session(engine) as session:
            yield session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _tier2_priority(self, instrument: str) -> float:
        activity_level = self._activity_level_by_instrument.get(instrument, "LOW").upper()
        if activity_level == "HIGH":
            return self.TIER2_SEED_PRIORITY + 10.0
        if activity_level == "MEDIUM":
            return self.TIER2_SEED_PRIORITY + 5.0
        return self.TIER2_SEED_PRIORITY

    def _promotion_still_valid(self, *, entry: WatchlistEntry, now: datetime) -> bool:
        promotion_expires_at = self._as_utc(entry.promotion_expires_at)
        if promotion_expires_at is None:
            return False
        return promotion_expires_at >= now


_watchlist_service: WatchlistService | None = None


def get_watchlist_service() -> WatchlistService:
    global _watchlist_service
    if _watchlist_service is None:
        _watchlist_service = WatchlistService()
    return _watchlist_service
