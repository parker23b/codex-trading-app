from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Response, status

from app.api.routes.health import health_check
from app.services.health_service import get_health_service


def test_health_service_classifies_ok_when_feed_and_broker_are_healthy():
    health_service = get_health_service()
    now = datetime.now(UTC)

    health_service.heartbeat(now)
    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=42.0)
    report = health_service.get_health_report()

    assert report["status"] == "ok"
    assert report["details"].broker_latency_ms == 42.0


def test_health_service_classifies_degraded_when_order_failures_accumulate():
    health_service = get_health_service()
    now = datetime.now(UTC)

    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    health_service.record_order_failure(now)
    health_service.record_order_failure(now + timedelta(seconds=10))
    health_service.record_order_failure(now + timedelta(seconds=20))
    report = health_service.get_health_report()

    assert report["status"] == "degraded"
    assert report["details"].order_failures_last_5m == 3


def test_health_service_classifies_critical_when_broker_is_disconnected():
    health_service = get_health_service()
    now = datetime.now(UTC)

    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=False)
    report = health_service.get_health_report()

    assert report["status"] == "critical"


def test_health_check_returns_ok_when_system_is_healthy():
    health_service = get_health_service()
    now = datetime.now(UTC)

    health_service.heartbeat(now)
    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    response = Response()

    payload = health_check(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload == {"status": "ok"}


def test_health_check_returns_503_when_system_is_critical():
    response = Response()

    payload = health_check(response)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload == {"status": "critical"}
