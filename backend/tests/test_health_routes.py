from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.broker_environment import IG_DEMO_BASE_URL, IG_LIVE_BASE_URL
from app.services.health_service import get_health_service
from app.services.observability_state_service import (
    OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK,
    OBSERVABILITY_STATE_AUDIT_WRITE,
    OBSERVABILITY_STATE_POLLING_FALLBACK,
    ObservabilityStateService,
)
from app.services.runtime_leadership_service import RuntimeLeadershipService


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
                "subscribed_instruments": ("CS.D.EURUSD.CFD.IP",),
                "desired_instruments": ("CS.D.EURUSD.CFD.IP",),
                "last_tick_at": self._last_tick_at,
            },
        )()


def test_system_telemetry_route_aggregates_multi_worker_observability_state(
    session, client_factory, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.heartbeat(now)
    health_service.record_price_update(
        now - timedelta(seconds=1), stream_connected=True
    )
    health_service.update_broker_state(connected=True, latency_ms=12.5)

    RuntimeLeadershipService(session, owner_id="worker-a").acquire(
        now=now,
        ttl=timedelta(seconds=30),
    )
    ObservabilityStateService.record_state(
        state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
        source="test.audit.worker_a",
        active=True,
        observed_at=now,
        expires_at=now + timedelta(minutes=5),
        payload={"failure_count_window": 1},
        worker_id="worker-a",
        hostname="host-a",
        process_id=101,
    )
    ObservabilityStateService.record_state(
        state_key=OBSERVABILITY_STATE_POLLING_FALLBACK,
        source="test.market.worker_b",
        active=True,
        observed_at=now,
        expires_at=now + timedelta(minutes=1),
        scope_type=ObservabilityStateService.INSTRUMENT_SCOPE,
        scope_id="CS.D.EURUSD.CFD.IP",
        payload={"instrument": "CS.D.EURUSD.CFD.IP"},
        worker_id="worker-b",
        hostname="host-b",
        process_id=202,
    )

    stream_service = _StubStreamingService(
        connected=False, last_tick_at=now - timedelta(seconds=30)
    )
    monkeypatch.setattr(
        "app.services.operational_telemetry_service.get_ig_streaming_service",
        lambda: stream_service,
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stream_service,
    )

    with client_factory(testing_routes_enabled=True) as client:
        response = client.get("/system/telemetry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["audit_write_degraded"] is True
    assert payload["polling_fallback_active"] is True
    assert payload["polling_fallback_active_instrument_count"] == 1
    assert payload["stream_degraded"] is True
    assert payload["observability"]["mode"] == "AGGREGATED"
    assert payload["observability"]["runtime_leader"]["owner_id"] == "worker-a"
    assert any(
        observation["worker_id"] == "worker-b"
        and observation["scope_id"] == "CS.D.EURUSD.CFD.IP"
        for observation in payload["observability"]["observations"]
    )


def test_system_health_route_labels_local_only_fallback_when_aggregation_unavailable(
    session, client_factory, monkeypatch
):
    now = datetime.now(UTC)
    health_service = get_health_service()
    health_service.heartbeat(now)
    health_service.record_price_update(
        now - timedelta(seconds=1), stream_connected=True
    )
    health_service.update_broker_state(connected=True, latency_ms=18.5)
    health_service.record_audit_write_failure(now - timedelta(seconds=3))
    health_service.set_polling_fallback_active("CS.D.EURUSD.CFD.IP", True)
    health_service.set_stream_stale("CS.D.EURUSD.CFD.IP", True)

    monkeypatch.setattr(
        ObservabilityStateService,
        "list_states",
        lambda self: (_ for _ in ()).throw(RuntimeError("aggregation unavailable")),
    )
    stream_service = _StubStreamingService(
        connected=False, last_tick_at=now - timedelta(seconds=30)
    )
    monkeypatch.setattr(
        "app.services.operational_telemetry_service.get_ig_streaming_service",
        lambda: stream_service,
    )
    monkeypatch.setattr(
        "app.services.operational_state_service.get_operational_streaming_service",
        lambda: stream_service,
    )

    with client_factory(testing_routes_enabled=True) as client:
        response = client.get("/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["degradations"]["audit_write_degraded"] is True
    assert payload["degradations"]["polling_fallback_active"] is True
    assert payload["degradations"]["stale_stream_instrument_count"] == 1
    assert payload["degradations"]["stream_degraded"] is True
    assert payload["observability"]["mode"] == OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK
    assert payload["observability"]["aggregation_available"] is False
    assert payload["observability"]["local_details_scope"] == "CURRENT_PROCESS"


def test_broker_environment_route_exposes_safe_classified_truth(client_factory):
    with client_factory(
        ig_api_base_url=IG_DEMO_BASE_URL,
        ig_trading_enabled=False,
        ig_streaming_enabled=False,
    ) as client:
        response = client.get("/system/broker-environment")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "IG",
        "environment": "DEMO",
        "endpoint_classification": "IG_DEMO_GATEWAY",
        "dealing_enabled": False,
        "streaming_enabled": False,
        "live_trading_acknowledged": False,
        "configuration_valid": True,
        "blocking_reason": None,
    }


def test_broker_environment_route_does_not_expose_secret_fields(client_factory):
    with client_factory(
        ig_api_base_url=IG_LIVE_BASE_URL,
        ig_trading_enabled=False,
        ig_live_trading_acknowledged=False,
        ig_api_key="secret-api-key",
        ig_username="secret-user",
        ig_password="secret-password",
        ig_account_id="secret-account-id",
    ) as client:
        response = client.get("/system/broker-environment")

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] == "LIVE"
    assert payload["endpoint_classification"] == "IG_LIVE_GATEWAY"
    for forbidden_field in {
        "api_key",
        "username",
        "password",
        "account_id",
        "ig_api_key",
        "ig_username",
        "ig_password",
        "ig_account_id",
        "cst",
        "x-security-token",
        "base_url",
    }:
        assert forbidden_field not in payload
