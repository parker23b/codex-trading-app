from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Response, status
from app.api.routes.health import health_check, system_health_check
from app.models.runtime import StrategyRuntimeState
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


def test_health_service_classifies_degraded_when_audit_writes_fail(monkeypatch):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.record_price_update(now, stream_connected=True)
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    health_service.record_audit_write_failure(now)
    report = health_service.get_health_report()

    assert report["status"] == "degraded"
    assert report["details"].audit_write_failures_last_5m == 1
    assert report["details"].last_audit_write_failure == now


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


def test_system_health_response_surfaces_audit_market_data_and_runtime_degradation(
    session, monkeypatch
):
    health_service = get_health_service()
    now = datetime.now(UTC)
    monkeypatch.setattr(health_service, "_has_live_operational_demand", lambda: True)
    monkeypatch.setattr(health_service, "_has_autonomy_armed", lambda: False)

    health_service.heartbeat(now)
    health_service.record_price_update(now - timedelta(seconds=2))
    health_service.update_broker_state(connected=True, latency_ms=25.0)
    health_service.record_audit_write_failure(now - timedelta(seconds=1))
    health_service.set_polling_fallback_active("CS.D.EURUSD.MINI.IP", True)
    health_service.set_stream_stale("CS.D.EURUSD.MINI.IP", True)

    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-degraded-1",
            strategy_name="mean_reversion",
            strategy_version="1",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            control_mode="AUTO",
            runtime_mode="NORMAL",
            updated_at=now,
            last_heartbeat_at=now - timedelta(minutes=10),
            last_price_seen_at=now - timedelta(minutes=10),
        )
    )
    session.commit()

    stream_stub = type(
        "StreamService",
        (),
        {
            "get_health": lambda self: type(
                "Health",
                (),
                {
                    "enabled": True,
                    "connected": False,
                    "subscribed_instruments": ("CS.D.EURUSD.MINI.IP",),
                    "desired_instruments": ("CS.D.EURUSD.MINI.IP",),
                    "last_tick_at": now - timedelta(seconds=30),
                },
            )(),
        },
    )()
    monkeypatch.setattr(
        "app.services.operational_telemetry_service.get_ig_streaming_service",
        lambda: stream_stub,
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stream_stub,
    )

    payload = system_health_check(session)

    assert payload.status == "critical"
    assert payload.details.audit_write_failures_last_5m == 1
    assert payload.details.polling_fallback_active_instrument_count == 1
    assert payload.details.stale_stream_instrument_count == 1
    assert payload.degradations.audit_write_degraded is True
    assert payload.degradations.polling_fallback_active is True
    assert payload.degradations.stream_degraded is True
    assert payload.degradations.runtime_degraded is True
    assert "audit_write_degraded" in payload.degradations.degradation_reasons
    assert "polling_fallback_active" in payload.degradations.degradation_reasons
    assert "stream_stale" in payload.degradations.degradation_reasons
    assert "runtime_heartbeat_stale" in payload.degradations.degradation_reasons
    assert "runtime_price_stale" in payload.degradations.degradation_reasons


def test_health_service_counts_pending_trade_intents_as_live_operational_demand(
    session, monkeypatch
):
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
