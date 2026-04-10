from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.health_service import get_health_service
from app.services.operational_telemetry_service import OperationalTelemetryService


def test_operational_telemetry_service_summarizes_runtime_stream_and_broker_health(session):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.heartbeat(now - timedelta(seconds=2))
    health_service.record_price_update(now - timedelta(seconds=1), stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=18.5)
    health_service.record_reconciliation(mismatches=2, when=now - timedelta(seconds=4))
    health_service.record_order_failure(now - timedelta(seconds=10))
    health_service.record_order_rejection(now - timedelta(seconds=5))
    health_service.set_paused_strategies(1)

    summary = OperationalTelemetryService(session).get_summary()

    assert summary["broker_connected"] is True
    assert summary["stream_connected"] is True
    assert summary["broker_latency_ms"] == 18.5
    assert summary["reconciliation_mismatches"] == 2
    assert summary["order_failures_last_5m"] == 2
    assert summary["rejected_orders_last_5m"] == 1
    assert summary["strategies_paused_by_health"] == 1
