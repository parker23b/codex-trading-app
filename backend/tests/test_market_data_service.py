from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.market_data_service import MarketDataService


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
    monkeypatch.setattr("app.services.market_data_service.get_ig_streaming_service", lambda: stream_service)

    assert service._polling_fallback_reason(instrument) is None


def test_polling_fallback_reason_marks_instrument_stale_only_after_relaxed_threshold(monkeypatch):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    service._now = lambda: now  # type: ignore[method-assign]
    instrument = "CS.D.EURUSD.CFD.IP"

    stream_service = _StubStreamingService(
        subscribed_instruments=(instrument,),
        global_last_tick_at=now - timedelta(seconds=1),
        instrument_ticks={instrument: now - timedelta(seconds=21)},
    )
    monkeypatch.setattr("app.services.market_data_service.get_ig_streaming_service", lambda: stream_service)

    assert service._polling_fallback_reason(instrument) == "stale_stream"


def test_polling_fallback_events_are_debounced(monkeypatch):
    now = datetime(2026, 4, 8, 18, 0, tzinfo=UTC)
    service = MarketDataService(poll_prices=False)
    instrument = "CS.D.EURUSD.CFD.IP"
    recorded_events: list[str] = []

    def record_event(*, event_type: str, **_: object) -> None:
        recorded_events.append(event_type)

    monkeypatch.setattr("app.services.market_data_service.domain_event_service.record_event", record_event)

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

    monkeypatch.setattr("app.services.market_data_service.get_ig_streaming_service", get_service)

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
