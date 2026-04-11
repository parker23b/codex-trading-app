from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Response, status
from app.api.routes.health import health_check
from app.models.trade import TradeIntent
from app.services.health_service import get_health_service


def test_health_service_classifies_ok_when_feed_and_broker_are_healthy(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.heartbeat(now)
    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=42.0)
    report = health_service.get_health_report()

    assert report["status"] == "ok"
    assert report["details"].broker_latency_ms == 42.0


def test_health_service_classifies_idle_when_system_is_unarmed(monkeypatch):
    health_service = get_health_service()
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: False)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    report = health_service.get_health_report()

    assert report["status"] == "idle"


def test_health_service_classifies_armed_when_autonomy_is_enabled(monkeypatch):
    health_service = get_health_service()
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: False)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: True)

    report = health_service.get_health_report()

    assert report["status"] == "armed"


def test_health_service_classifies_degraded_when_order_failures_accumulate(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    health_service.record_order_failure(now)
    health_service.record_order_failure(now + timedelta(seconds=10))
    health_service.record_order_failure(now + timedelta(seconds=20))
    report = health_service.get_health_report()

    assert report["status"] == "degraded"
    assert report["details"].order_failures_last_5m == 3


def test_health_service_classifies_critical_when_broker_is_disconnected(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=False)
    report = health_service.get_health_report()

    assert report["status"] == "critical"


def test_health_check_returns_ok_when_system_is_healthy(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.heartbeat(now)
    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    response = Response()

    payload = health_check(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload == {"status": "ok"}


def test_health_check_returns_503_when_system_is_critical(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)
    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=False)
    response = Response()

    payload = health_check(response)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload == {"status": "critical"}


def test_health_service_counts_pending_trade_intents_as_live_operational_demand(session, monkeypatch):
    session.add(
        TradeIntent(
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            direction="BUY",
            state="APPROVED",
            signal_time=datetime.now(UTC),
        )
    )
    session.commit()

    health_service = get_health_service()
    monkeypatch.setattr("app.services.health_service.engine", session.get_bind())

    assert health_service._has_live_operational_demand() is True
