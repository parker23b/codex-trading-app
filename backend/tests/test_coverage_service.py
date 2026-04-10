from __future__ import annotations

from datetime import UTC, datetime

from app.models.domain_event import DomainEvent
from app.services.market_status_service import MarketStatus
from app.models.promotion_request import PromotionRequest, PromotionRequestStatus
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.services.coverage_service import CoverageService


def test_coverage_service_summarizes_watchlist_and_promotion_state(session, monkeypatch):
    session.add(
        WatchlistEntry(
            instrument="CS.D.EURUSD.CFD.IP",
            tier=WatchlistTier.TIER1.value,
            status=WatchlistStatus.ACTIVE.value,
            pinned=True,
            reason="open_position",
            priority_score=100.0,
            assigned_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
        )
    )
    session.add(
        WatchlistEntry(
            instrument="COM.D.XAUUSD.CFD.IP",
            tier=WatchlistTier.TIER2.value,
            status=WatchlistStatus.ACTIVE.value,
            pinned=False,
            reason="tier2_seed",
            priority_score=35.0,
            assigned_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 9, 12, 1, tzinfo=UTC),
        )
    )
    session.add(
        PromotionRequest(
            instrument="IX.D.SP500.DAILY.IP",
            source="activity_surveillance_scanner",
            reason="activity_regime_alignment",
            score=0.88,
            status=PromotionRequestStatus.PENDING.value,
            requested_at=datetime(2026, 4, 9, 12, 2, tzinfo=UTC),
            updated_at=datetime(2026, 4, 9, 12, 2, tzinfo=UTC),
        )
    )
    session.add(
        DomainEvent(
            event_type="strategy.trade_allocator_selected",
            category="strategy",
            severity="info",
            source="strategy_service.allocate_signal_candidates",
            strategy_name="breakout_guard",
            instrument="CS.D.EURUSD.CFD.IP",
            title="Trade allocator selected signal candidate",
            payload_json={
                "reason_code": "selected",
                "reason": "Signal selected by trade allocator.",
                "score": 0.91,
                "direction": "BUY",
                "source_tier": "TIER1",
            },
            created_at=datetime(2026, 4, 9, 12, 3, tzinfo=UTC),
        )
    )
    session.add(
        DomainEvent(
            event_type="strategy.trade_allocator_rejected",
            category="strategy",
            severity="info",
            source="strategy_service.allocate_signal_candidates",
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
            title="Trade allocator rejected signal candidate",
            payload_json={
                "reason_code": "direction_conflict",
                "reason": "A stronger conflicting signal was selected.",
                "score": 0.72,
                "direction": "SELL",
                "source_tier": "TIER1",
            },
            created_at=datetime(2026, 4, 9, 12, 4, tzinfo=UTC),
        )
    )
    session.commit()

    service = CoverageService(session)
    service.watchlist_service.settings.ig_streaming_seed_instruments = ["CS.D.EURUSD.CFD.IP"]
    service.watchlist_service.settings.tier2_seed_instruments = ["COM.D.XAUUSD.CFD.IP"]
    monkeypatch.setattr(
        "app.services.coverage_service.get_market_status_service",
        lambda: type(
            "MarketStatusService",
            (),
            {
                "get_status": lambda self, instrument: MarketStatus(
                    instrument=instrument,
                    is_ok=True,
                    market_open=True,
                    tradable=True,
                    quote_fresh=True,
                    spread_ok=True,
                    session_valid=True,
                    dealing_allowed=True,
                    last_price_age_ms=120.0,
                    spread=0.0002,
                    reason=None,
                )
            },
        )(),
    )
    summary = service.get_summary()

    assert summary["streaming"]["active_instruments"][0]["instrument"] == "CS.D.EURUSD.CFD.IP"
    assert summary["streaming"]["execution_readiness"][0]["instrument"] == "CS.D.EURUSD.CFD.IP"
    assert summary["tier2"]["active_candidates"][0]["instrument"] == "COM.D.XAUUSD.CFD.IP"
    assert summary["promotions"]["pending_count"] == 1
    assert summary["trade_allocator"]["selected_count"] == 1
    assert summary["trade_allocator"]["rejected_count"] == 1
    assert summary["trade_allocator"]["reason_counts"]["selected"] == 1
    assert summary["trade_allocator"]["reason_counts"]["direction_conflict"] == 1
    assert summary["trade_allocator"]["recent_decisions"][0]["reason_code"] == "direction_conflict"
