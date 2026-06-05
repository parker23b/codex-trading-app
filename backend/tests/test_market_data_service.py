from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.models.domain_event import DomainEvent
from app.models.promotion_request import PromotionRequest
from app.models.watchlist import WatchlistEntry, WatchlistTier
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.market_data_service import (
    AUDIT_PERSISTENCE_BEST_EFFORT,
    AUDIT_PERSISTENCE_REQUIRED,
    MarketDataService,
)
from app.services.watchlist_service import StreamingPlan, Tier2RefreshPlan


pytestmark = pytest.mark.usefixtures("audit_critical_domain_events")


def _domain_events(session) -> list[DomainEvent]:
    return list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))


class _StubStreamingService:
    def __init__(
        self,
        *,
        connected: bool = True,
        enabled: bool = True,
        subscribed_instruments: tuple[str, ...] = (),
        global_last_tick_at: datetime | None = None,
        instrument_ticks: dict[str, datetime] | None = None,
    ) -> None:
        self._connected = connected
        self._enabled = enabled
        self._subscribed_instruments = subscribed_instruments
        self._global_last_tick_at = global_last_tick_at
        self._instrument_ticks = instrument_ticks or {}

    def get_health(self):
        return type(
            "Health",
            (),
            {
                "enabled": self._enabled,
                "connected": self._connected,
                "subscribed_instruments": self._subscribed_instruments,
                "last_tick_at": self._global_last_tick_at,
                "last_error": None,
                "last_status": "CONNECTED:WS-STREAMING",
                "last_tick_at_by_instrument": self._instrument_ticks,
            },
        )()

    def get_last_tick_at(self, instrument: str) -> datetime | None:
        return self._instrument_ticks.get(instrument)


def test_polling_fallback_reason_uses_per_instrument_tick(monkeypatch):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    service.settings.market_data_poll_interval_seconds = 2
    service._now = lambda: now  # type: ignore[method-assign]
    instrument = "CS.D.EURUSD.CFD.IP"
    other_instrument = "CS.D.GBPUSD.CFD.IP"

    stream_service = _StubStreamingService(
        subscribed_instruments=(instrument, other_instrument),
        global_last_tick_at=now - timedelta(seconds=1),
        instrument_ticks={
            instrument: now - timedelta(seconds=8),
            other_instrument: now - timedelta(seconds=1),
        },
    )
    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service",
        lambda: stream_service,
    )

    assert service._polling_fallback_reason(instrument) is None


def test_polling_fallback_reason_marks_instrument_stale_only_after_relaxed_threshold(
    monkeypatch,
):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    service.settings.market_data_poll_interval_seconds = 2
    service._now = lambda: now  # type: ignore[method-assign]
    instrument = "CS.D.EURUSD.CFD.IP"

    stream_service = _StubStreamingService(
        subscribed_instruments=(instrument,),
        global_last_tick_at=now - timedelta(seconds=1),
        instrument_ticks={instrument: now - timedelta(seconds=21)},
    )
    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service",
        lambda: stream_service,
    )

    assert service._polling_fallback_reason(instrument) == "stale_stream"


def test_polling_fallback_events_are_debounced(monkeypatch):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    instrument = "CS.D.EURUSD.CFD.IP"
    recorded_events: list[str] = []

    def record_event(*, event_type: str, **_: object) -> None:
        recorded_events.append(event_type)

    monkeypatch.setattr(
        "app.services.market_data_service.domain_event_service.record_event",
        record_event,
    )

    state = {
        "connected": True,
        "instrument_tick": now - timedelta(seconds=35),
    }

    def get_service():
        return _StubStreamingService(
            connected=state["connected"],
            subscribed_instruments=(instrument,),
            global_last_tick_at=state["instrument_tick"],
            instrument_ticks={instrument: state["instrument_tick"]},
        )

    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service", get_service
    )

    service._now = lambda: now  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument)
    assert recorded_events == []

    service._now = lambda: now + timedelta(seconds=11)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument)
    assert recorded_events == ["health.polling_fallback_started", "health.stream_stale"]

    state["instrument_tick"] = now + timedelta(seconds=12)
    service._now = lambda: now + timedelta(seconds=18)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument)
    assert recorded_events == ["health.polling_fallback_started", "health.stream_stale"]

    service._now = lambda: now + timedelta(seconds=29)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument)
    assert recorded_events == [
        "health.polling_fallback_started",
        "health.stream_stale",
        "health.polling_fallback_stopped",
        "health.stream_recovered",
    ]


def test_audit_test_002_polling_health_transitions_persist_with_session(
    session, monkeypatch
):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    instrument = "CS.D.EURUSD.CFD.IP"
    state = {"instrument_tick": now - timedelta(seconds=35)}

    def get_service():
        return _StubStreamingService(
            subscribed_instruments=(instrument,),
            global_last_tick_at=state["instrument_tick"],
            instrument_ticks={instrument: state["instrument_tick"]},
        )

    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service", get_service
    )

    service._now = lambda: now  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument, session=session)

    service._now = lambda: now + timedelta(seconds=11)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument, session=session)

    state["instrument_tick"] = now + timedelta(seconds=12)
    service._now = lambda: now + timedelta(seconds=18)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument, session=session)

    service._now = lambda: now + timedelta(seconds=29)  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument, session=session)

    events = _domain_events(session)
    assert [event.event_type for event in events] == [
        "health.polling_fallback_started",
        "health.stream_stale",
        "health.polling_fallback_stopped",
        "health.stream_recovered",
    ]
    assert all(event.actor_type == "service" for event in events)
    assert all(event.actor_id == "market_data_service" for event in events)
    assert all(
        event.source == "market_data_service.polling_fallback" for event in events
    )
    assert events[0].instrument == instrument
    assert events[0].payload_json["audit_persistence"] == AUDIT_PERSISTENCE_REQUIRED
    assert events[0].payload_json["audit_role"] == "operational_degradation"
    assert events[0].payload_json["previous_state"] == "STREAM_HEALTHY"
    assert events[0].payload_json["new_state"] == "POLLING_FALLBACK"
    assert events[1].payload_json["previous_state"] == "STREAM_FRESH"
    assert events[1].payload_json["new_state"] == "STREAM_STALE"
    assert events[2].payload_json["previous_state"] == "POLLING_FALLBACK"
    assert events[2].payload_json["new_state"] == "STREAM_HEALTHY"
    assert events[3].payload_json["previous_state"] == "STREAM_STALE"
    assert events[3].payload_json["new_state"] == "STREAM_RECOVERED"
    details = get_health_service().get_system_health()
    assert details.polling_fallback_active_instrument_count == 0
    assert details.stale_stream_instrument_count == 0


def test_audit_obs_001_sessionless_polling_events_are_explicitly_best_effort(
    monkeypatch,
):
    service = MarketDataService(poll_prices=False)
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        domain_event_service,
        "record_event",
        lambda **kwargs: captured.append(kwargs) or None,
        raising=False,
    )

    service._record_polling_health_event(
        audit_persistence=AUDIT_PERSISTENCE_BEST_EFFORT,
        event_type="health.polling_fallback_started",
        category="health",
        source="market_data_service.polling_fallback",
        title="Polling fallback started",
        instrument="CS.D.EURUSD.CFD.IP",
        payload_json={
            "previous_state": "STREAM_HEALTHY",
            "new_state": "POLLING_FALLBACK",
        },
    )

    assert captured[0]["payload_json"] == {
        "previous_state": "STREAM_HEALTHY",
        "new_state": "POLLING_FALLBACK",
        "audit_persistence": AUDIT_PERSISTENCE_BEST_EFFORT,
        "audit_role": "operational_degradation",
    }


def test_audit_obs_001_polling_health_audit_failure_blocks_clean_transition(
    session, monkeypatch
):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    instrument = "CS.D.EURUSD.CFD.IP"
    stream_service = _StubStreamingService(
        subscribed_instruments=(instrument,),
        global_last_tick_at=now - timedelta(seconds=35),
        instrument_ticks={instrument: now - timedelta(seconds=35)},
    )
    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service",
        lambda: stream_service,
    )
    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    service._now = lambda: now  # type: ignore[method-assign]
    service._update_polling_health_transition(instrument, session=session)

    service._now = lambda: now + timedelta(seconds=11)  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="durable audit event"):
        service._update_polling_health_transition(instrument, session=session)

    assert _domain_events(session) == []


def test_successful_polling_fallback_does_not_mark_stream_as_connected(monkeypatch):
    service = MarketDataService(poll_prices=False)
    instrument = "CS.D.EURUSD.CFD.IP"
    health_service = get_health_service()
    health_service.set_stream_connected(False)
    stream_service = _StubStreamingService(
        connected=False,
        subscribed_instruments=(instrument,),
        global_last_tick_at=None,
        instrument_ticks={},
    )
    watchlist = type(
        "Watchlist",
        (),
        {
            "get_streaming_plan": lambda self: StreamingPlan(
                instruments=(instrument,),
                pinned_instruments=(),
                capped_instruments=(),
                asset_class_usage={},
            )
        },
    )()
    fake_engine = type(
        "Engine",
        (),
        {
            "broker": type(
                "Broker",
                (),
                {
                    "get_market_details": lambda self, _: type(
                        "Details",
                        (),
                        {
                            "bid": 1.1,
                            "offer": 1.2,
                            "high": 1.3,
                            "low": 1.0,
                            "market_status": "TRADEABLE",
                            "tradable": True,
                        },
                    )()
                },
            )()
        },
    )()

    monkeypatch.setattr(
        "app.services.market_data_service.get_watchlist_service", lambda: watchlist
    )
    monkeypatch.setattr(
        "app.services.market_data_service.get_ig_streaming_service",
        lambda: stream_service,
    )
    monkeypatch.setattr(
        "app.services.market_data_service.runtime_manager.get_engines_for_instrument",
        lambda _: [("test", fake_engine)],
    )
    monkeypatch.setattr(
        "app.services.market_data_service.BrokerService.reconcile_positions",
        lambda *args, **kwargs: None,
    )
    processed: list[str] = []
    monkeypatch.setattr(
        "app.services.market_data_service.StrategyService.process_price_update",
        lambda self, *args, **kwargs: processed.append(args[0]),
    )

    import asyncio

    asyncio.run(service._process_tier1_fallback_once())

    assert processed == [instrument]
    assert get_health_service().get_system_health().stream_connected is False


def test_broker_reconciliation_uses_slow_cadence(session, monkeypatch):
    service = MarketDataService(poll_prices=False)
    service.settings.broker_reconciliation_interval_seconds = 60
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service._now = lambda: now  # type: ignore[method-assign]
    calls = 0

    def fake_reconcile(self, active_session):
        nonlocal calls
        calls += 1
        assert active_session is session
        return []

    monkeypatch.setattr(
        "app.services.market_data_service.BrokerService.reconcile_positions",
        fake_reconcile,
    )

    service._reconcile_positions_if_due(session=session)
    service._now = lambda: now + timedelta(seconds=10)  # type: ignore[method-assign]
    service._reconcile_positions_if_due(session=session)
    service._now = lambda: now + timedelta(seconds=61)  # type: ignore[method-assign]
    service._reconcile_positions_if_due(session=session)

    assert calls == 2


def test_tier2_refresh_creates_promotion_request_for_high_scoring_candidate(
    session, monkeypatch
):
    service = MarketDataService(poll_prices=False)
    service.settings.tier2_refresh_interval_seconds = 1
    service.settings.tier2_promotion_score_threshold = 0.7
    service.settings.tier2_promotion_ttl_seconds = 300
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service._now = lambda: now  # type: ignore[method-assign]

    broker = type(
        "Broker",
        (),
        {
            "get_market_details": lambda self, instrument: type(
                "Details",
                (),
                {
                    "bid": 1.0,
                    "offer": 1.1,
                    "high": 1.2,
                    "low": 0.9,
                    "market_status": "TRADEABLE",
                    "tradable": True,
                    "percentage_change": 1.2,
                },
            )()
        },
    )()
    service.broker = broker

    watchlist = type(
        "Watchlist",
        (),
        {
            "get_tier2_refresh_plan": lambda self: Tier2RefreshPlan(
                instruments=("CS.D.GBPJPY.CFD.IP",),
                streamed_instruments=(),
                capped_instruments=("CS.D.GBPJPY.CFD.IP",),
            ),
            "record_tier2_refresh": lambda self, *, instrument, refreshed_at: (
                session.add(
                    WatchlistEntry(
                        instrument=instrument,
                        tier=WatchlistTier.TIER2.value,
                        status="ACTIVE",
                        assigned_at=refreshed_at,
                        last_refreshed_at=refreshed_at,
                        updated_at=refreshed_at,
                    )
                )
                or session.commit()
            ),
        },
    )()
    monkeypatch.setattr(
        "app.services.market_data_service.get_watchlist_service", lambda: watchlist
    )
    monkeypatch.setattr(
        "app.services.market_data_service.domain_event_service.record_event",
        lambda **_: None,
    )
    monkeypatch.setattr("app.services.market_data_service.engine", session.get_bind())

    import asyncio

    asyncio.run(service._refresh_tier2_once())

    request = session.exec(select(PromotionRequest)).one()
    assert request.instrument == "CS.D.GBPJPY.CFD.IP"
    assert request.status == "ACCEPTED"
    assert request.source == "activity_surveillance_scanner"
    assert request.score >= 0.7
    entry = session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == "CS.D.GBPJPY.CFD.IP")
    ).all()[-1]
    assert entry.tier == WatchlistTier.TIER1.value


def test_audit_test_002_tier2_refresh_persists_session_bound_domain_events(
    session, monkeypatch
):
    service = MarketDataService(poll_prices=False)
    service.settings.tier2_refresh_interval_seconds = 1
    service.settings.tier2_promotion_score_threshold = 0.7
    service.settings.tier2_promotion_ttl_seconds = 300
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service._now = lambda: now  # type: ignore[method-assign]

    broker = type(
        "Broker",
        (),
        {
            "get_market_details": lambda self, instrument: type(
                "Details",
                (),
                {
                    "bid": 1.0,
                    "offer": 1.1,
                    "high": 1.2,
                    "low": 0.9,
                    "market_status": "TRADEABLE",
                    "tradable": True,
                    "percentage_change": 1.2,
                },
            )()
        },
    )()
    service.broker = broker

    watchlist = type(
        "Watchlist",
        (),
        {
            "get_tier2_refresh_plan": lambda self: Tier2RefreshPlan(
                instruments=("CS.D.GBPJPY.CFD.IP",),
                streamed_instruments=(),
                capped_instruments=("CS.D.GBPJPY.CFD.IP",),
            ),
            "record_tier2_refresh": lambda self, *, instrument, refreshed_at: (
                session.add(
                    WatchlistEntry(
                        instrument=instrument,
                        tier=WatchlistTier.TIER2.value,
                        status="ACTIVE",
                        assigned_at=refreshed_at,
                        last_refreshed_at=refreshed_at,
                        updated_at=refreshed_at,
                    )
                )
                or session.commit()
            ),
        },
    )()
    monkeypatch.setattr(
        "app.services.market_data_service.get_watchlist_service", lambda: watchlist
    )
    monkeypatch.setattr("app.services.market_data_service.engine", session.get_bind())

    import asyncio

    asyncio.run(service._refresh_tier2_once())

    request = session.exec(select(PromotionRequest)).one()
    events = _domain_events(session)
    coverage_events = [
        event
        for event in events
        if event.event_type
        in {
            "market.tier2_refreshed",
            "coverage.promotion_requested",
            "coverage.promotion_accepted",
            "coverage.allocation_cycle_completed",
        }
    ]
    assert [event.event_type for event in coverage_events] == [
        "market.tier2_refreshed",
        "coverage.promotion_requested",
        "coverage.promotion_accepted",
        "coverage.allocation_cycle_completed",
    ]
    assert coverage_events[0].source == "market_data_service.tier2_refresh"
    assert coverage_events[0].instrument == "CS.D.GBPJPY.CFD.IP"
    assert coverage_events[0].payload_json["market_status"] == "TRADEABLE"
    assert coverage_events[1].actor_type == "service"
    assert coverage_events[1].actor_id == "activity_surveillance_scanner"
    assert coverage_events[1].payload_json["promotion_request_id"] == request.id
    assert coverage_events[2].source == "coverage_allocator.allocate_pending_promotions"
    assert coverage_events[2].payload_json["previous_state"] == "PENDING"
    assert coverage_events[2].payload_json["new_state"] == "ACCEPTED"
    assert coverage_events[3].payload_json["accepted"] == 1


def test_audit_test_002_tier2_refresh_persists_reconcile_cycle_event(
    session, monkeypatch
):
    service = MarketDataService(poll_prices=False)
    service.settings.tier2_refresh_interval_seconds = 1
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service._now = lambda: now  # type: ignore[method-assign]

    broker = type(
        "Broker",
        (),
        {
            "get_market_details": lambda self, instrument: type(
                "Details",
                (),
                {
                    "bid": 1.0,
                    "offer": 1.1,
                    "high": 1.2,
                    "low": 0.9,
                    "market_status": "TRADEABLE",
                    "tradable": True,
                    "percentage_change": 1.2,
                },
            )()
        },
    )()
    service.broker = broker

    watchlist = type(
        "Watchlist",
        (),
        {
            "get_tier2_refresh_plan": lambda self: Tier2RefreshPlan(
                instruments=("CS.D.GBPJPY.CFD.IP",),
                streamed_instruments=(),
                capped_instruments=("CS.D.GBPJPY.CFD.IP",),
            ),
            "record_tier2_refresh": lambda self, *, instrument, refreshed_at: (
                session.add(
                    WatchlistEntry(
                        instrument=instrument,
                        tier=WatchlistTier.TIER2.value,
                        status="ACTIVE",
                        assigned_at=refreshed_at,
                        last_refreshed_at=refreshed_at,
                        updated_at=refreshed_at,
                    )
                )
                or session.commit()
            ),
        },
    )()
    reconcile_result = type(
        "ReconcileResult",
        (),
        {
            "deployed": 1,
            "paused": 0,
            "blocked": 0,
            "degraded": 0,
            "emergency_stopped": 0,
        },
    )()
    monkeypatch.setattr(
        "app.services.market_data_service.get_watchlist_service", lambda: watchlist
    )
    monkeypatch.setattr("app.services.market_data_service.engine", session.get_bind())
    monkeypatch.setattr(
        "app.services.market_data_service.StrategyDeploymentManagerService.reconcile",
        lambda self, now=None: reconcile_result,
    )

    import asyncio

    asyncio.run(service._refresh_tier2_once())

    events = _domain_events(session)
    cycle_event = next(
        event
        for event in events
        if event.event_type == "control_plane.reconciliation_cycle_completed"
    )
    assert cycle_event.source == "market_data_service.tier2_refresh"
    assert cycle_event.actor_type == "service"
    assert cycle_event.actor_id == "market_data_service"
    assert cycle_event.payload_json == {
        "deployed": 1,
        "paused": 0,
        "blocked": 0,
        "degraded": 0,
        "emergency_stopped": 0,
    }
