from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.health_service import get_health_service
from app.services.operational_telemetry_service import OperationalTelemetryService


class _StubStreamingService:
    def __init__(
        self, *, connected: bool, last_tick_at: datetime | None = None
    ) -> None:
        self._connected = connected
        self._last_tick_at = last_tick_at

    def get_health(self):
        return type(
            "Health",
            (),
            {
                "enabled": True,
                "connected": self._connected,
                "subscribed_instruments": (),
                "desired_instruments": (),
                "last_tick_at": self._last_tick_at,
            },
        )()


def test_operational_telemetry_service_summarizes_runtime_stream_and_broker_health(
    session, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.heartbeat(now - timedelta(seconds=2))
    health_service.record_price_update(
        now - timedelta(seconds=1), stream_connected=True
    )
    health_service.update_broker_state(connected=True, latency_ms=18.5)
    health_service.record_reconciliation(mismatches=2, when=now - timedelta(seconds=4))
    health_service.record_order_failure(now - timedelta(seconds=10))
    health_service.record_order_rejection(now - timedelta(seconds=5))
    health_service.record_audit_write_failure(now - timedelta(seconds=3))
    health_service.set_paused_strategies(1)
    monkeypatch.setattr(
        "app.services.operational_telemetry_service.get_ig_streaming_service",
        lambda: _StubStreamingService(
            connected=True, last_tick_at=now - timedelta(seconds=1)
        ),
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(
            connected=True, last_tick_at=now - timedelta(seconds=1)
        ),
    )

    summary = OperationalTelemetryService(session).get_summary()

    assert summary["broker_connected"] is True
    assert summary["stream_connected"] is True
    assert summary["feed_source_state"] == "LIVE"
    assert summary["audit_write_degraded"] is True
    assert summary["polling_fallback_active"] is False
    assert summary["stream_degraded"] is False
    assert summary["runtime_degraded"] is True
    assert summary["entry_eligible"] is True
    assert summary["exit_eligible"] is True
    assert summary["broker_latency_ms"] == 18.5
    assert summary["reconciliation_mismatches"] == 2
    assert summary["order_failures_last_5m"] == 2
    assert summary["rejected_orders_last_5m"] == 1
    assert summary["audit_write_failures_last_5m"] == 1
    assert summary["last_audit_write_failure"] == now - timedelta(seconds=3)
    assert summary["last_audit_write_failure_age_ms"] is not None
    assert summary["strategies_paused_by_health"] == 1
    assert "audit_write_degraded" in summary["degradation_reasons"]
    assert "runtime_paused_or_restricted" in summary["degradation_reasons"]


def test_operational_telemetry_reports_fallback_without_marking_stream_connected(
    session, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.heartbeat(now - timedelta(seconds=2))
    health_service.record_price_update(now - timedelta(seconds=1))
    health_service.update_broker_state(connected=True, latency_ms=18.5)
    monkeypatch.setattr(
        "app.services.operational_telemetry_service.get_ig_streaming_service",
        lambda: _StubStreamingService(
            connected=False, last_tick_at=now - timedelta(seconds=30)
        ),
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: _StubStreamingService(
            connected=False, last_tick_at=now - timedelta(seconds=30)
        ),
    )

    summary = OperationalTelemetryService(session).get_summary()

    assert summary["stream_connected"] is False
    assert summary["feed_source_state"] == "POLLING_FALLBACK"
    assert summary["polling_fallback_active"] is True
    assert summary["stream_degraded"] is True
    assert summary["runtime_degraded"] is False
    assert summary["entry_eligible"] is False
    assert summary["entry_block_reason"] == "polling_fallback_active"
    assert summary["exit_eligible"] is True
    assert "polling_fallback_active" in summary["degradation_reasons"]
    assert "stream_degraded" in summary["degradation_reasons"]
