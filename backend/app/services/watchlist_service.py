from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Iterator

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.instrument_catalog import InstrumentDefinition, list_market_instruments
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.models.trade import Position
from app.models.watchlist import (
    OperatorShortlistEntry,
    WatchlistEntry,
    WatchlistStatus,
    WatchlistTier,
)
from app.services.trade_service import TradeService

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
    PIN_PRIORITY = 100.0
    SEED_PRIORITY = 75.0
    RUNTIME_PRIORITY = 50.0
    OPERATOR_PRIORITY = 60.0
    TIER2_SEED_PRIORITY = 25.0
    OPERATOR_STRATEGY_WATCHLIST_REASON = "operator_strategy_watchlist"
    FOREX_MAJOR_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD"}
    REASON_DETAILS: dict[str, tuple[str, str]] = {
        "added_to_strategy_watchlist": (
            "Added to strategy watchlist",
            "No action needed. The backend can now consider this instrument for streaming and evaluation.",
        ),
        "already_in_strategy_watchlist": (
            "Already in strategy watchlist",
            "No action needed. This instrument is already eligible.",
        ),
        "operator_strategy_watchlist": (
            "Added by operator",
            "Remove it from the strategy watchlist when it should no longer be eligible.",
        ),
        "runtime_active": (
            "Active strategy runtime",
            "Stop the runtime if this instrument should no longer be evaluated.",
        ),
        "seed_watchlist": (
            "Configured seed instrument",
            "Update backend streaming seed settings if this should not be automatically eligible.",
        ),
        "promotion_accepted": (
            "Promoted by coverage",
            "Review the promotion source if this instrument should not remain eligible.",
        ),
        "open_position": (
            "Protective coverage for open position",
            "Keep streaming until the open position is closed or reconciled.",
        ),
        "pending_trade_intent": (
            "Protective coverage for pending intent",
            "Keep streaming until the pending intent reaches a terminal state.",
        ),
        "unknown_instrument": (
            "Instrument is not in the catalogue",
            "Choose a catalogue instrument before adding it to the strategy watchlist.",
        ),
        "strategy_watchlist_limit_reached": (
            "Strategy watchlist limit reached",
            "Remove another operator-added instrument or wait for protective coverage to clear.",
        ),
        "no_active_strategy_runtime": (
            "No active strategy runtime",
            "Start or authorize a strategy runtime before expecting evaluation.",
        ),
        "market_readiness_blocked": (
            "Market readiness blocked",
            "Review market status, dealing permission, quote freshness, and spread.",
        ),
        "streaming": (
            "Streaming",
            "No action needed. Live ticks are flowing for this instrument.",
        ),
        "desired": (
            "Waiting for stream",
            "The instrument is eligible; wait for the streaming loop to subscribe.",
        ),
        "capped": (
            "Capped by watchlist limit",
            "Remove lower-priority instruments or increase the backend cap deliberately.",
        ),
        "stale_stream": (
            "Stream is stale",
            "Check streaming connectivity and market-data freshness before enabling entries.",
        ),
        "inactive": (
            "Not streaming",
            "Add the instrument to the strategy watchlist if it should become eligible.",
        ),
        "eligible": (
            "Eligible",
            "No action needed. Current feed and runtime state allow evaluation.",
        ),
        "unsupported_chart_instrument": (
            "Chart unavailable for this instrument",
            "Select a supported catalogue instrument with backend candle coverage.",
        ),
        "empty_candles": (
            "No candles returned",
            "Wait for backend candle data or choose another timeframe/instrument.",
        ),
        "broker_candles_unavailable": (
            "Candle source unavailable",
            "The chart endpoint is available, but no candle data could be loaded.",
        ),
    }

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
        self._definition_by_instrument = {
            instrument.epic: instrument for instrument in list_market_instruments()
        }

    def list_catalogue(self) -> list[dict[str, object]]:
        with self._session_scope() as session:
            shortlist = {
                entry.instrument
                for entry in session.exec(select(OperatorShortlistEntry)).all()
            }
            active_entries = {
                entry.instrument: entry
                for entry in session.exec(
                    select(WatchlistEntry)
                    .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                    .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
                ).all()
            }
            streamed = self._streaming_now_set()
            return [
                self._serialize_catalogue_definition(
                    definition=definition,
                    shortlisted=definition.epic in shortlist,
                    in_strategy_watchlist=definition.epic in active_entries,
                    streaming_now=definition.epic in streamed,
                )
                for definition in list_market_instruments()
            ]

    def catalogue_response(self) -> dict[str, object]:
        rows = self.list_catalogue()
        return {
            "generated_at": self._now(),
            "instruments": rows,
            "summary": {
                "total_count": len(rows),
                "shortlisted_count": len([row for row in rows if row["shortlisted"]]),
                "strategy_watchlist_count": len(
                    [row for row in rows if row["in_strategy_watchlist"]]
                ),
                "streaming_count": len([row for row in rows if row["streaming_now"]]),
            },
        }

    def list_shortlist(self) -> list[dict[str, object]]:
        with self._session_scope() as session:
            entries = list(
                session.exec(
                    select(OperatorShortlistEntry).order_by(
                        OperatorShortlistEntry.created_at
                    )
                ).all()
            )
            active = {
                entry.instrument
                for entry in session.exec(
                    select(WatchlistEntry)
                    .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                    .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
                ).all()
            }
            streamed = self._streaming_now_set()
            return [
                {
                    **self._serialize_catalogue_definition(
                        definition=self._definition_by_instrument.get(entry.instrument),
                        instrument=entry.instrument,
                        shortlisted=True,
                        in_strategy_watchlist=entry.instrument in active,
                        streaming_now=entry.instrument in streamed,
                    ),
                    "shortlisted_at": entry.created_at,
                    "note": entry.note,
                }
                for entry in entries
            ]

    def shortlist_response(self) -> dict[str, object]:
        rows = self.list_shortlist()
        return {"generated_at": self._now(), "instruments": rows, "count": len(rows)}

    def set_shortlisted(
        self, instrument: str, *, actor_id: str = "operator"
    ) -> dict[str, object]:
        definition = self._definition_by_instrument.get(instrument)
        if definition is None:
            raise ValueError(f"Unknown instrument '{instrument}'.")
        with self._session_scope() as session:
            now = self._now()
            entry = session.exec(
                select(OperatorShortlistEntry).where(
                    OperatorShortlistEntry.instrument == instrument
                )
            ).first()
            if entry is None:
                entry = OperatorShortlistEntry(
                    instrument=instrument,
                    actor_id=actor_id,
                    created_at=now,
                    updated_at=now,
                )
            else:
                entry.actor_id = actor_id
                entry.updated_at = now
            session.add(entry)
            session.commit()
            return self._serialize_catalogue_definition(
                definition=definition,
                shortlisted=True,
                in_strategy_watchlist=self._is_active_tier1(
                    session=session, instrument=instrument
                ),
                streaming_now=instrument in self.get_streaming_plan().instruments,
            )

    def remove_shortlisted(self, instrument: str) -> None:
        with self._session_scope() as session:
            entry = session.exec(
                select(OperatorShortlistEntry).where(
                    OperatorShortlistEntry.instrument == instrument
                )
            ).first()
            if entry is None:
                return
            session.delete(entry)
            session.commit()

    def list_strategy_watchlist(self, *, sync: bool = True) -> list[dict[str, object]]:
        with self._session_scope() as session:
            if sync:
                self._sync_system_entries(session=session, now=self._now())
            entries = list(
                session.exec(
                    select(WatchlistEntry)
                    .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                    .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
                ).all()
            )
            streamed = self._streaming_now_set()
            return [
                self._serialize_strategy_watchlist_entry(
                    entry, streamed=entry.instrument in streamed
                )
                for entry in sorted(
                    entries,
                    key=lambda item: (
                        0 if item.pinned else 1,
                        -item.priority_score,
                        item.instrument,
                    ),
                )
            ]

    def strategy_watchlist_response(self, *, sync: bool = True) -> dict[str, object]:
        rows = self.list_strategy_watchlist(sync=sync)
        protective_count = len([row for row in rows if row.get("protective")])
        normal_count = len(rows) - protective_count
        limit = self.settings.ig_streaming_max_instruments
        return {
            "generated_at": self._now(),
            "limit": limit,
            "active_count": len(rows),
            "normal_count": normal_count,
            "streaming_count": len([row for row in rows if row["streamed"]]),
            "protective_count": protective_count,
            "cap_exceeded_by_protective_coverage": bool(
                limit > 0 and len(rows) > limit and protective_count
            ),
            "instruments": rows,
        }

    def add_to_strategy_watchlist(self, instruments: list[str]) -> dict[str, object]:
        added: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        unique_instruments = list(dict.fromkeys(instruments))
        with self._session_scope() as session:
            now = self._now()
            self._sync_system_entries(session=session, now=now)
            active_entries = session.exec(
                select(WatchlistEntry)
                .where(WatchlistEntry.tier == WatchlistTier.TIER1.value)
                .where(WatchlistEntry.status == WatchlistStatus.ACTIVE.value)
            ).all()
            normal_count = len(
                [
                    entry
                    for entry in active_entries
                    if not entry.pinned and not self._is_protective_reason(entry.reason)
                ]
            )
            max_instruments = self.settings.ig_streaming_max_instruments
            existing_entries = {
                entry.instrument: entry
                for entry in session.exec(select(WatchlistEntry)).all()
            }
            for instrument in unique_instruments:
                definition = self._definition_by_instrument.get(instrument)
                if definition is None:
                    skipped.append(
                        {
                            "instrument": instrument,
                            "reason": self.reason_detail("unknown_instrument")["label"],
                            "reason_detail": self.reason_detail("unknown_instrument"),
                        }
                    )
                    continue
                existing = existing_entries.get(instrument)
                already_active = (
                    existing is not None
                    and existing.tier == WatchlistTier.TIER1.value
                    and existing.status == WatchlistStatus.ACTIVE.value
                )
                existing_is_normal = bool(
                    existing is not None
                    and not existing.pinned
                    and not self._is_protective_reason(existing.reason)
                )
                if (
                    not already_active
                    and max_instruments > 0
                    and normal_count >= max_instruments
                ):
                    skipped.append(
                        {
                            "instrument": instrument,
                            "reason": self.reason_detail(
                                "strategy_watchlist_limit_reached"
                            )["label"],
                            "reason_detail": self.reason_detail(
                                "strategy_watchlist_limit_reached",
                                operator_action=(
                                    f"Remove another operator-added instrument first. "
                                    f"The current phase cap is {max_instruments} instruments."
                                ),
                            ),
                        }
                    )
                    continue
                entry = self._upsert_entry(
                    session=session,
                    now=now,
                    instrument=instrument,
                    existing=existing,
                    pinned=False,
                    priority_score=self.OPERATOR_PRIORITY,
                    reason=self.OPERATOR_STRATEGY_WATCHLIST_REASON,
                )
                existing_entries[instrument] = entry
                if not already_active or not existing_is_normal:
                    normal_count += 1
                added.append(
                    {
                        "instrument": instrument,
                        "reason": self.reason_detail(
                            "already_in_strategy_watchlist"
                            if already_active
                            else "added_to_strategy_watchlist"
                        )["label"],
                        "reason_detail": self.reason_detail(
                            "already_in_strategy_watchlist"
                            if already_active
                            else "added_to_strategy_watchlist"
                        ),
                    }
                )
            session.commit()
        return {
            "added": added,
            "skipped": skipped,
            "limit": self.settings.ig_streaming_max_instruments,
        }

    def feed_state_response(self, *, sync: bool = True) -> dict[str, object]:
        watchlist = self.list_strategy_watchlist(sync=sync)
        rows = [
            self.feed_state_for_instrument(str(row["instrument"]), watchlist_entry=row)
            for row in watchlist
        ]
        return {"generated_at": self._now(), "instruments": rows}

    def feed_state_for_instrument(
        self,
        instrument: str,
        *,
        watchlist_entry: dict[str, object] | None = None,
    ) -> dict[str, object]:
        from app.services.ig_streaming_service import get_ig_streaming_service
        from app.services.market_status_service import get_market_status_service

        now = self._now()
        stream_health = get_ig_streaming_service().get_health()
        last_tick_at = (stream_health.last_tick_at_by_instrument or {}).get(instrument)
        last_tick_age_ms = (
            round((now - last_tick_at.astimezone(UTC)).total_seconds() * 1000, 2)
            if last_tick_at is not None
            else None
        )
        subscribed = instrument in stream_health.subscribed_instruments
        desired = instrument in stream_health.desired_instruments
        capped = instrument in stream_health.capped_instruments
        stale_threshold_ms = self.settings.ig_streaming_stale_after_seconds * 1000
        stale = bool(
            subscribed
            and (
                not stream_health.connected
                or last_tick_age_ms is None
                or last_tick_age_ms > stale_threshold_ms
            )
        )
        stream_status = (
            "stale"
            if stale
            else "streaming"
            if subscribed and stream_health.connected
            else "desired"
            if desired
            else "capped"
            if capped
            else "inactive"
        )
        market_status = None
        market_error = None
        try:
            market_status = (
                get_market_status_service().get_status(instrument).model_dump()
            )
        except Exception as exc:  # pragma: no cover - defensive read model degradation
            market_error = str(exc)

        runtime_count = len(runtime_manager.get_engines_for_instrument(instrument))
        market_ok = bool(market_status and market_status.get("is_ok"))
        strategies_may_evaluate = bool(runtime_count and market_ok and not stale)
        reason_code = (
            "eligible" if strategies_may_evaluate else "market_readiness_blocked"
        )
        if runtime_count == 0:
            reason_code = "no_active_strategy_runtime"
        elif stale:
            reason_code = "stale_stream"
        elif market_status and not market_status.get("is_ok"):
            reason_code = "market_readiness_blocked"
        has_snapshot = bool(
            instrument in self._definition_by_instrument
            and market_status
            and market_status.get("last_price_age_ms") is not None
            and isfinite(float(market_status.get("last_price_age_ms") or 0.0))
        )
        source = (
            "STALE"
            if stale
            else "STREAM"
            if subscribed and stream_health.connected
            else "SNAPSHOT"
            if has_snapshot
            else "UNAVAILABLE"
        )
        stream_reason_code = "stale_stream" if stale else stream_status
        return {
            "instrument": instrument,
            "stream_status": stream_status,
            "stream_reason": self.reason_detail(stream_reason_code),
            "stream_connected": stream_health.connected,
            "stream_enabled": stream_health.enabled,
            "streaming_now": subscribed and stream_health.connected and not stale,
            "desired": desired,
            "capped": capped,
            "last_tick_at": last_tick_at,
            "last_tick_age_ms": last_tick_age_ms,
            "spread": market_status.get("spread") if market_status else None,
            "price_source": source,
            "market_status": market_status,
            "market_error": market_error,
            "entry_eligibility": self.reason_detail(reason_code)["label"],
            "entry_eligibility_reason": self.reason_detail(
                reason_code,
                label=str(market_status.get("reason"))
                if reason_code == "market_readiness_blocked" and market_status
                else None,
            ),
            "strategies_may_evaluate": strategies_may_evaluate,
            "active_strategy_runtime_count": runtime_count,
            "watchlist_entry": watchlist_entry,
        }

    def remove_from_strategy_watchlist(self, instrument: str) -> None:
        with self._session_scope() as session:
            entry = session.exec(
                select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
            ).first()
            if entry is None or entry.reason != self.OPERATOR_STRATEGY_WATCHLIST_REASON:
                return
            entry.status = WatchlistStatus.COOLDOWN.value
            entry.cooldown_until = self._now() + timedelta(
                seconds=self.settings.ig_streaming_demotion_cooldown_seconds
            )
            entry.updated_at = self._now()
            session.add(entry)
            session.commit()

    def get_streaming_plan(self, *, sync: bool = True) -> StreamingPlan:
        with self._session_scope() as session:
            now = self._now()
            if sync:
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
            normal_selected_count = 0

            for entry in entries:
                asset_class = (entry.asset_class or "UNCLASSIFIED").upper()
                if entry.pinned:
                    selected.append(entry.instrument)
                    pinned.append(entry.instrument)
                    asset_usage[asset_class] += 1
                    continue

                if max_instruments > 0 and normal_selected_count >= max_instruments:
                    capped.append(entry.instrument)
                    continue

                budget = asset_budgets.get(asset_class)
                if budget is not None and asset_usage[asset_class] >= budget:
                    capped.append(entry.instrument)
                    continue

                selected.append(entry.instrument)
                normal_selected_count += 1
                asset_usage[asset_class] += 1

            if sync:
                for instrument in selected:
                    entry = next(
                        (
                            candidate
                            for candidate in entries
                            if candidate.instrument == instrument
                        ),
                        None,
                    )
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

    def get_tier2_refresh_plan(self, *, sync: bool = True) -> Tier2RefreshPlan:
        streaming_plan = self.get_streaming_plan(sync=sync)
        streamed = set(streaming_plan.instruments)
        with self._session_scope() as session:
            now = self._now()
            if sync:
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
                    self._as_utc(entry.last_refreshed_at)
                    or datetime(1970, 1, 1, tzinfo=UTC),
                    -entry.priority_score,
                    entry.instrument,
                )
            )

            candidates: list[str] = []
            for instrument in streaming_plan.capped_instruments:
                if instrument not in streamed and instrument not in candidates:
                    candidates.append(instrument)

            stale_cutoff = now - timedelta(
                seconds=self.settings.tier2_refresh_stale_after_seconds
            )
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
            existing = session.exec(
                select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
            ).first()
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
            entry = session.exec(
                select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
            ).first()
            if entry is None:
                return
            entry.promotion_expires_at = expires_at
            entry.requested_frequency = requested_frequency
            entry.updated_at = promoted_at
            session.add(entry)
            session.commit()

    def record_tier2_refresh(self, *, instrument: str, refreshed_at: datetime) -> None:
        with self._session_scope() as session:
            entry = session.exec(
                select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
            ).first()
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

        operator_instruments = {
            instrument
            for instrument, entry in existing_entries.items()
            if entry.reason == self.OPERATOR_STRATEGY_WATCHLIST_REASON
            and entry.status == WatchlistStatus.ACTIVE.value
        }

        desired_active = (
            set(pinned_instruments)
            | runtime_instruments
            | seed_instruments
            | promoted_instruments
            | operator_instruments
        )

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

        for instrument in operator_instruments:
            if (
                instrument in pinned_instruments
                or instrument in runtime_instruments
                or instrument in seed_instruments
            ):
                continue
            self._upsert_entry(
                session=session,
                now=now,
                instrument=instrument,
                existing=existing_entries.get(instrument),
                pinned=False,
                priority_score=self.OPERATOR_PRIORITY,
                reason=self.OPERATOR_STRATEGY_WATCHLIST_REASON,
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
            entry.cooldown_until = now + timedelta(
                seconds=self.settings.ig_streaming_demotion_cooldown_seconds
            )
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
                min_residency_until=now
                + timedelta(
                    seconds=self.settings.ig_streaming_min_tier1_residency_seconds
                ),
                updated_at=now,
            )
        else:
            entry = existing
            cooldown_until = self._as_utc(entry.cooldown_until)
            if (
                entry.status == WatchlistStatus.COOLDOWN.value
                and cooldown_until
                and cooldown_until > now
                and pinned
            ):
                logger.info(
                    "Pinned instrument bypassed watchlist cooldown",
                    extra={
                        "instrument": instrument,
                        "cooldown_until": cooldown_until.isoformat(),
                    },
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
                entry.min_residency_until = now + timedelta(
                    seconds=self.settings.ig_streaming_min_tier1_residency_seconds
                )
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
                entry.priority_score = max(
                    entry.priority_score, self._tier2_priority(instrument)
                )
                entry.updated_at = now
            session.add(entry)
        session.commit()

    def _collect_pinned_instruments(self, *, session: Session) -> dict[str, str]:
        reasons: dict[str, set[str]] = defaultdict(set)
        positions = session.exec(
            select(Position).where(Position.is_open.is_(True))
        ).all()
        for position in positions:
            reasons[position.instrument].add("open_position")

        pending_intents = TradeService(session).list_trade_intents(limit=500)
        for intent in pending_intents:
            if intent.state in {
                "PROPOSED",
                "APPROVED",
                "SUBMITTED",
                "ACKNOWLEDGED",
                "PARTIALLY_FILLED",
                "CLOSE_REQUESTED",
                "EXTERNAL_POSITION_ADOPTED",
                "RECOVERED_POSITION_ATTACHED",
            }:
                reasons[intent.instrument].add("pending_trade_intent")

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
        activity_level = self._activity_level_by_instrument.get(
            instrument, "LOW"
        ).upper()
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

    def _is_active_tier1(self, *, session: Session, instrument: str) -> bool:
        entry = session.exec(
            select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
        ).first()
        return bool(
            entry is not None
            and entry.tier == WatchlistTier.TIER1.value
            and entry.status == WatchlistStatus.ACTIVE.value
        )

    def _serialize_catalogue_definition(
        self,
        *,
        definition: InstrumentDefinition | None,
        instrument: str | None = None,
        shortlisted: bool,
        in_strategy_watchlist: bool,
        streaming_now: bool,
    ) -> dict[str, object]:
        epic = definition.epic if definition is not None else str(instrument)
        symbol = definition.symbol if definition is not None else epic
        asset_class = definition.category if definition is not None else "UNKNOWN"
        base_currency, quote_currency = self._currency_pair(symbol)
        return {
            "id": epic,
            "instrument": epic,
            "name": definition.label if definition is not None else epic,
            "symbol": symbol,
            "asset_class": asset_class,
            "category": asset_class.lower(),
            "currency": quote_currency,
            "base_currency": base_currency,
            "quote_currency": quote_currency,
            "forex_major": symbol.upper() in self.FOREX_MAJOR_SYMBOLS,
            "tradable": True,
            "shortlisted": shortlisted,
            "in_strategy_watchlist": in_strategy_watchlist,
            "streaming_now": streaming_now,
            "activity_level": definition.activity_level
            if definition is not None
            else "LOW",
            "strategy_compatibility": list(definition.compatible_strategies)
            if definition is not None
            else [],
            "reference_price": definition.reference_price
            if definition is not None
            else None,
        }

    @staticmethod
    def _is_protective_reason(reason: str | None) -> bool:
        if not reason:
            return False
        parts = {part.strip() for part in reason.split(",")}
        return bool(parts & {"open_position", "pending_trade_intent"})

    def _serialize_strategy_watchlist_entry(
        self, entry: WatchlistEntry, *, streamed: bool
    ) -> dict[str, object]:
        reason_code = entry.reason or "strategy_watchlist"
        protective = self._is_protective_reason(entry.reason)
        return {
            "instrument": entry.instrument,
            "tier": entry.tier,
            "status": entry.status,
            "asset_class": entry.asset_class,
            "pinned": entry.pinned,
            "reason": entry.reason,
            "reason_detail": self.reason_detail(reason_code),
            "protective": protective,
            "priority_score": entry.priority_score,
            "requested_frequency": entry.requested_frequency,
            "promotion_expires_at": entry.promotion_expires_at,
            "last_streamed_at": entry.last_streamed_at,
            "last_refreshed_at": entry.last_refreshed_at,
            "streamed": streamed,
        }

    def reason_detail(
        self,
        code: str,
        *,
        label: str | None = None,
        operator_action: str | None = None,
    ) -> dict[str, object]:
        if "," in code:
            parts = [part.strip() for part in code.split(",") if part.strip()]
            if len(parts) == 1:
                code = parts[0]
            elif parts:
                details = [self.reason_detail(part) for part in parts]
                return {
                    "code": code,
                    "label": label or "Protective coverage",
                    "operator_action": operator_action
                    or "Keep streaming until all protective conditions clear.",
                    "components": details,
                }
        default_label, default_action = self.REASON_DETAILS.get(
            code,
            (
                code.replace("_", " ").capitalize(),
                "Review the underlying system state before taking action.",
            ),
        )
        return {
            "code": code,
            "label": label or default_label,
            "operator_action": operator_action or default_action,
        }

    @staticmethod
    def _currency_pair(symbol: str) -> tuple[str | None, str | None]:
        normalized = symbol.replace("/", "").upper()
        if len(normalized) == 6 and normalized.isalpha():
            return normalized[:3], normalized[3:]
        return None, normalized if normalized.isalpha() else None

    def _streaming_now_set(self) -> set[str]:
        from app.services.ig_streaming_service import get_ig_streaming_service

        health = get_ig_streaming_service().get_health()
        if not health.connected:
            return set()
        now = self._now()
        stale_threshold_ms = self.settings.ig_streaming_stale_after_seconds * 1000
        active: set[str] = set()
        last_ticks = health.last_tick_at_by_instrument or {}
        for instrument in health.subscribed_instruments:
            tick_at = last_ticks.get(instrument)
            if tick_at is None:
                continue
            age_ms = (now - tick_at.astimezone(UTC)).total_seconds() * 1000
            if age_ms <= stale_threshold_ms:
                active.add(instrument)
        return active


_watchlist_service: WatchlistService | None = None


def get_watchlist_service() -> WatchlistService:
    global _watchlist_service
    if _watchlist_service is None:
        _watchlist_service = WatchlistService()
    return _watchlist_service
