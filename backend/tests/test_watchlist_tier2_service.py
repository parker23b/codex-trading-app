from __future__ import annotations

from datetime import UTC, datetime

from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.services.watchlist_service import WatchlistService


def test_tier2_refresh_plan_uses_capped_and_seed_candidates(session):
    service = WatchlistService(session)
    service.settings.ig_streaming_max_instruments = 1
    service.settings.ig_streaming_seed_instruments = [
        "CS.D.EURUSD.CFD.IP",
        "IX.D.SP500.DAILY.IP",
    ]
    service.settings.tier2_seed_instruments = ["COM.D.XAUUSD.CFD.IP"]
    service.settings.tier2_refresh_batch_size = 3
    now = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    service._sync_system_entries(session=session, now=now)
    service._sync_tier2_seed_entries(session=session, now=now)

    plan = service.get_tier2_refresh_plan()

    assert "IX.D.SP500.DAILY.IP" in plan.instruments
    assert "COM.D.XAUUSD.CFD.IP" in plan.instruments


def test_record_tier2_refresh_updates_timestamp(session):
    service = WatchlistService(session)
    refreshed_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)

    service.record_tier2_refresh(
        instrument="COM.D.XAUUSD.CFD.IP", refreshed_at=refreshed_at
    )

    entry = session.get(WatchlistEntry, 1)
    assert entry is not None
    assert entry.tier == WatchlistTier.TIER2.value
    assert entry.status == WatchlistStatus.ACTIVE.value
    assert entry.last_refreshed_at.replace(tzinfo=UTC) == refreshed_at
