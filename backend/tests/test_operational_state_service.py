from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.runtime import runtime_manager
from app.services.health_service import get_health_service
from app.services.operational_state_service import OperationalStateService


class _StubStreamingService:
    def __init__(
        self,
        *,
        connected: bool,
        enabled: bool = True,
        last_tick_at: datetime | None = None,
        last_tick_at_by_instrument: dict[str, datetime] | None = None,
    ) -> None:
        self._connected = connected
        self._enabled = enabled
        self._last_tick_at = last_tick_at
        self._last_tick_at_by_instrument = last_tick_at_by_instrument or {}

    def get_health(self):
        return type(
            "Health",
            (),
            {
                "enabled": self._enabled,
                "connected": self._connected,
                "subscribed_instruments": (),
                "desired_instruments": (),
                "last_tick_at": self._last_tick_at,
            },
        )()

    def get_last_tick_at(self, instrument: str) -> datetime | None:
        return self._last_tick_at_by_instrument.get(instrument, self._last_tick_at)


def test_operational_state_live_stream_allows_entries(session, monkeypatch):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now, stream_connected=True)
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(connected=True, last_tick_at=now),
    )

    summary = OperationalStateService(session).get_summary()

    assert summary.feed_source_state == "LIVE"
    assert summary.feed_health_state == "HEALTHY"
    assert summary.broker_connectivity_state == "CONNECTED"
    assert summary.entry_eligible is True
    assert summary.exit_eligible is True
    assert summary.entry_block_reason is None


def test_operational_state_fallback_blocks_entries_but_keeps_exits(
    session, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now)
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(
            connected=False, last_tick_at=now - timedelta(seconds=30)
        ),
    )

    summary = OperationalStateService(session).get_summary()

    assert summary.feed_source_state == "POLLING_FALLBACK"
    assert summary.feed_health_state == "DEGRADED"
    assert summary.entry_eligible is False
    assert summary.exit_eligible is True
    assert summary.entry_block_reason == "polling_fallback_active"
    assert summary.exit_block_reason is None


def test_operational_state_stale_prices_block_entries_and_exits(session, monkeypatch):
    stale_at = datetime.now(UTC) - timedelta(seconds=30)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(stale_at)
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(connected=False, last_tick_at=stale_at),
    )

    summary = OperationalStateService(session).get_summary()

    assert summary.feed_source_state == "STALE"
    assert summary.entry_eligible is False
    assert summary.exit_eligible is False
    assert summary.entry_block_reason == "stale_price_data"
    assert summary.exit_block_reason == "stale_price_data"


def test_operational_state_broker_disconnect_blocks_entries_and_exits(
    session, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.update_broker_state(connected=False, latency_ms=None)
    health_service.record_price_update(now, stream_connected=True)
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(connected=True, last_tick_at=now),
    )

    summary = OperationalStateService(session).get_summary()

    assert summary.broker_connectivity_state == "DISCONNECTED"
    assert summary.entry_eligible is False
    assert summary.exit_eligible is False
    assert summary.entry_block_reason == "broker_disconnected"
    assert summary.exit_block_reason == "broker_disconnected"


def test_operational_state_disconnected_feed_blocks_entries_and_exits(
    session, monkeypatch
):
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(connected=False, last_tick_at=None),
    )

    summary = OperationalStateService(session).get_summary()

    assert summary.feed_source_state == "DISCONNECTED"
    assert summary.feed_health_state == "FAILED"
    assert summary.entry_eligible is False
    assert summary.exit_eligible is False
    assert summary.entry_block_reason == "data_disconnected"
    assert summary.exit_block_reason == "data_disconnected"


def test_operational_state_instrument_summary_uses_instrument_specific_freshness(
    session, monkeypatch
):
    now = datetime.now(UTC)
    stale_at = now - timedelta(seconds=30)
    health_service = get_health_service()
    health_service.update_broker_state(connected=True, latency_ms=5.0)
    health_service.record_price_update(now, stream_connected=True)
    runtime_manager.load_cached_price(
        "IX.D.FTSE.DAILY.IP", price=100.0, updated_at=stale_at
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(
            connected=True,
            last_tick_at=now,
            last_tick_at_by_instrument={"IX.D.FTSE.DAILY.IP": stale_at},
        ),
    )

    summary = OperationalStateService(session).get_summary_for_instrument(
        "IX.D.FTSE.DAILY.IP"
    )

    assert summary.feed_source_state == "STALE"
    assert summary.entry_eligible is False
    assert summary.exit_eligible is False
    assert summary.exit_block_reason == "stale_price_data"
