from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.models.promotion_request import PromotionRequest, PromotionRequestStatus
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.services.coverage_allocator_service import CoverageAllocatorService


def test_allocator_accepts_high_scoring_request_into_tier1(session):
    requested_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    session.add(
        PromotionRequest(
            instrument="CS.D.GBPJPY.CFD.IP",
            source="tier2_refresh",
            reason="tier2_screen_score",
            score=0.88,
            status=PromotionRequestStatus.PENDING.value,
            requested_at=requested_at,
            expires_at=requested_at + timedelta(minutes=5),
            requested_frequency="2.0",
            updated_at=requested_at,
        )
    )
    session.commit()

    allocator = CoverageAllocatorService(session)
    allocator.settings.tier2_promotion_score_threshold = 0.75
    allocator.settings.ig_streaming_max_promotions_per_minute = 4
    result = allocator.allocate_pending_promotions(now=requested_at)

    request = session.exec(select(PromotionRequest)).one()
    entry = session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == "CS.D.GBPJPY.CFD.IP")
    ).one()
    assert result.accepted == 1
    assert request.status == PromotionRequestStatus.ACCEPTED.value
    assert entry.tier == WatchlistTier.TIER1.value
    assert entry.status == WatchlistStatus.ACTIVE.value
    assert entry.reason == "promotion_accepted"


def test_allocator_respects_promotion_budget(session):
    requested_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    session.add(
        PromotionRequest(
            instrument="CS.D.EURUSD.CFD.IP",
            source="tier2_refresh",
            reason="older_accept",
            score=0.91,
            status=PromotionRequestStatus.ACCEPTED.value,
            requested_at=requested_at - timedelta(seconds=30),
            expires_at=requested_at + timedelta(minutes=5),
            updated_at=requested_at - timedelta(seconds=30),
        )
    )
    session.add(
        PromotionRequest(
            instrument="IX.D.SP500.DAILY.IP",
            source="tier2_refresh",
            reason="tier2_screen_score",
            score=0.9,
            status=PromotionRequestStatus.PENDING.value,
            requested_at=requested_at,
            expires_at=requested_at + timedelta(minutes=5),
            updated_at=requested_at,
        )
    )
    session.commit()

    allocator = CoverageAllocatorService(session)
    allocator.settings.tier2_promotion_score_threshold = 0.75
    allocator.settings.ig_streaming_max_promotions_per_minute = 1
    result = allocator.allocate_pending_promotions(now=requested_at)

    pending = session.exec(
        select(PromotionRequest).where(
            PromotionRequest.instrument == "IX.D.SP500.DAILY.IP"
        )
    ).one()
    assert result.rejected == 1
    assert pending.status == PromotionRequestStatus.REJECTED.value


def test_allocator_rejects_request_when_watchlist_entry_is_in_cooldown(session):
    requested_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    session.add(
        WatchlistEntry(
            instrument="COM.D.XAUUSD.CFD.IP",
            tier=WatchlistTier.TIER1.value,
            status=WatchlistStatus.COOLDOWN.value,
            cooldown_until=requested_at + timedelta(minutes=2),
            assigned_at=requested_at - timedelta(minutes=5),
            updated_at=requested_at - timedelta(minutes=1),
        )
    )
    session.add(
        PromotionRequest(
            instrument="COM.D.XAUUSD.CFD.IP",
            source="tier2_refresh",
            reason="tier2_screen_score",
            score=0.86,
            status=PromotionRequestStatus.PENDING.value,
            requested_at=requested_at,
            expires_at=requested_at + timedelta(minutes=5),
            updated_at=requested_at,
        )
    )
    session.commit()

    allocator = CoverageAllocatorService(session)
    allocator.settings.tier2_promotion_score_threshold = 0.75
    result = allocator.allocate_pending_promotions(now=requested_at)

    request = session.exec(select(PromotionRequest)).one()
    assert result.rejected == 1
    assert request.status == PromotionRequestStatus.REJECTED.value
