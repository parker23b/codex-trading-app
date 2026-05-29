from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.observability_state_service import (
    OBSERVABILITY_MODE_AGGREGATED,
    OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK,
    OBSERVABILITY_STATE_AUDIT_WRITE,
    OBSERVABILITY_STATE_POLLING_FALLBACK,
    OBSERVABILITY_STATE_RUNTIME_PAUSED,
    OBSERVABILITY_STATE_STREAM_CONNECTION,
    OBSERVABILITY_STATE_STREAM_STALE,
    ObservabilityStateService,
)


def _local_details(**overrides):
    defaults = {
        "audit_write_failures_last_5m": 0,
        "last_audit_write_failure": None,
        "polling_fallback_active_instrument_count": 0,
        "stale_stream_instrument_count": 0,
        "strategies_paused_by_health": 0,
        "broker_connected": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_observability_state_aggregates_multi_worker_degradations_and_marks_stale(
    session,
):
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    service = ObservabilityStateService(session)

    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
            source="test.audit.worker_a",
            active=True,
            observed_at=now,
            expires_at=now + timedelta(minutes=5),
            payload={"failure_count_window": 2},
            worker_id="worker-a",
            hostname="host-a",
            process_id=101,
        )
        is True
    )
    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
            source="test.audit.worker_b",
            active=True,
            observed_at=now - timedelta(minutes=6),
            expires_at=now - timedelta(seconds=1),
            payload={"failure_count_window": 9},
            worker_id="worker-b",
            hostname="host-b",
            process_id=202,
        )
        is True
    )
    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_POLLING_FALLBACK,
            source="test.market_data",
            active=True,
            observed_at=now,
            expires_at=now + timedelta(minutes=1),
            scope_type=ObservabilityStateService.INSTRUMENT_SCOPE,
            scope_id="CS.D.EURUSD.CFD.IP",
            payload={"instrument": "CS.D.EURUSD.CFD.IP"},
            worker_id="worker-a",
            hostname="host-a",
            process_id=101,
        )
        is True
    )
    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_STREAM_STALE,
            source="test.market_data",
            active=True,
            observed_at=now,
            expires_at=now + timedelta(minutes=1),
            scope_type=ObservabilityStateService.INSTRUMENT_SCOPE,
            scope_id="CS.D.EURUSD.CFD.IP",
            payload={"instrument": "CS.D.EURUSD.CFD.IP"},
            worker_id="worker-a",
            hostname="host-a",
            process_id=101,
        )
        is True
    )
    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_STREAM_CONNECTION,
            source="test.streaming",
            active=True,
            observed_at=now,
            expires_at=now + timedelta(minutes=1),
            payload={"connected": False},
            worker_id="worker-a",
            hostname="host-a",
            process_id=101,
        )
        is True
    )
    assert (
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_RUNTIME_PAUSED,
            source="test.runtime",
            active=True,
            observed_at=now,
            expires_at=now + timedelta(minutes=1),
            payload={"paused_count": 1},
            worker_id="worker-a",
            hostname="host-a",
            process_id=101,
        )
        is True
    )

    summary = service.build_summary(
        now=now,
        local_details=_local_details(),
        stale_runtime_count=0,
        stale_price_runtime_count=0,
        local_stream_degraded=False,
        local_polling_fallback_active=False,
    )

    assert summary["mode"] == OBSERVABILITY_MODE_AGGREGATED
    assert summary["aggregation_available"] is True
    assert summary["audit_write_degraded"] is True
    assert summary["audit_write_failures_last_5m"] == 2
    assert summary["polling_fallback_active"] is True
    assert summary["polling_fallback_active_instrument_count"] == 1
    assert summary["stale_stream_instrument_count"] == 1
    assert summary["stream_degraded"] is True
    assert summary["runtime_degraded"] is True
    assert summary["stale_observation_count"] == 1
    assert "audit_write_degraded" in summary["degradation_reasons"]
    assert "polling_fallback_active" in summary["degradation_reasons"]
    assert "stream_stale" in summary["degradation_reasons"]
    assert "runtime_paused_or_restricted" in summary["degradation_reasons"]
    assert any(
        observation["worker_id"] == "worker-b" and observation["stale"] is True
        for observation in summary["observations"]
    )


def test_observability_state_falls_back_to_local_process_when_aggregation_unavailable(
    session, monkeypatch
):
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    service = ObservabilityStateService(session)

    monkeypatch.setattr(
        service,
        "list_states",
        lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    summary = service.build_summary(
        now=now,
        local_details=_local_details(
            audit_write_failures_last_5m=1,
            last_audit_write_failure=now - timedelta(seconds=5),
            polling_fallback_active_instrument_count=2,
            stale_stream_instrument_count=1,
            strategies_paused_by_health=1,
            broker_connected=False,
        ),
        stale_runtime_count=1,
        stale_price_runtime_count=0,
        local_stream_degraded=True,
        local_polling_fallback_active=True,
    )

    assert summary["mode"] == OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK
    assert summary["aggregation_available"] is False
    assert summary["audit_write_degraded"] is True
    assert summary["polling_fallback_active"] is True
    assert summary["stale_stream_instrument_count"] == 1
    assert summary["stream_degraded"] is True
    assert summary["runtime_degraded"] is True
    assert summary["active_observation_count"] == 4
    assert "broker_disconnected" in summary["degradation_reasons"]
