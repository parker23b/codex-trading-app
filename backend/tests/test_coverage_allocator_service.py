from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.models.domain_event import DomainEvent
from app.models.promotion_request import PromotionRequest, PromotionRequestStatus
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.services.coverage_allocator_service import CoverageAllocatorService
from app.services.domain_event_service import domain_event_service


def _domain_events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


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


def test_audit_test_002_allocator_accept_persists_session_bound_domain_event(session):
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
    allocator.allocate_pending_promotions(now=requested_at)

    request = session.exec(select(PromotionRequest)).one()
    events = _domain_events(session)
    assert [event.event_type for event in events] == ["coverage.promotion_accepted"]
    event = events[0]
    assert event.category == "coverage"
    assert event.severity == "info"
    assert event.source == "coverage_allocator.allocate_pending_promotions"
    assert event.actor_type == "service"
    assert event.actor_id == "coverage_allocator"
    assert event.instrument == "CS.D.GBPJPY.CFD.IP"
    assert event.payload_json["promotion_request_id"] == request.id
    assert event.payload_json["previous_state"] == "PENDING"
    assert event.payload_json["new_state"] == "ACCEPTED"
    assert event.payload_json["score"] == 0.88


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


def test_audit_test_002_allocator_reject_persists_session_bound_domain_event(session):
    requested_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
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
    allocator.settings.ig_streaming_max_promotions_per_minute = 0
    allocator.allocate_pending_promotions(now=requested_at)

    request = session.exec(select(PromotionRequest)).one()
    events = _domain_events(session)
    assert request.status == PromotionRequestStatus.REJECTED.value
    assert [event.event_type for event in events] == ["coverage.promotion_rejected"]
    event = events[0]
    assert event.actor_type == "service"
    assert event.actor_id == "coverage_allocator"
    assert event.instrument == "IX.D.SP500.DAILY.IP"
    assert event.payload_json["promotion_request_id"] == request.id
    assert event.payload_json["previous_state"] == "PENDING"
    assert event.payload_json["new_state"] == "REJECTED"
    assert event.payload_json["reason_code"] == "promotion_budget_exhausted"


def test_audit_obs_001_allocator_audit_failure_blocks_clean_mutation(
    session, monkeypatch
):
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
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    allocator = CoverageAllocatorService(session)
    allocator.settings.tier2_promotion_score_threshold = 0.75
    allocator.settings.ig_streaming_max_promotions_per_minute = 4
    with pytest.raises(RuntimeError, match="durable audit event"):
        allocator.allocate_pending_promotions(now=requested_at)

    request = session.exec(select(PromotionRequest)).one()
    assert request.status == PromotionRequestStatus.PENDING.value
    assert _domain_events(session) == []


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
