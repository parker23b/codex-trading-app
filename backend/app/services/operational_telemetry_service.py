from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.services.health_service import get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.observability_state_service import ObservabilityStateService
from app.services.operational_state_service import OperationalStateService
from app.services.runtime_state_service import RuntimeStateService


class OperationalTelemetryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.health_service = get_health_service()
        self.runtime_state_service = RuntimeStateService(session)
        self.operational_state_service = OperationalStateService(session)

    def get_summary(self) -> dict[str, object]:
        now = datetime.now(UTC)
        health_report = self.health_service.get_health_report(session=self.session)
        details = health_report["details"]
        stream_health = get_ig_streaming_service().get_health()
        operational_state = self.operational_state_service.get_summary()
        runtimes = self.runtime_state_service.list_runtimes()
        active_runtimes = [
            runtime for runtime in runtimes if runtime.status == "RUNNING"
        ]
        heartbeat_stale_after_seconds = (
            self.settings.system_health_heartbeat_interval_seconds * 3
        )
        price_stale_after_seconds = max(
            self.settings.runtime_price_stale_after_seconds,
            self.settings.market_data_poll_interval_seconds * 3,
        )

        stale_runtime_count = len(
            [
                runtime
                for runtime in active_runtimes
                if runtime.last_heartbeat_at is None
                or (now - self._as_utc(runtime.last_heartbeat_at)).total_seconds()
                > heartbeat_stale_after_seconds
            ]
        )
        stale_price_runtime_count = len(
            [
                runtime
                for runtime in active_runtimes
                if runtime.last_price_seen_at is None
                or (now - self._as_utc(runtime.last_price_seen_at)).total_seconds()
                > price_stale_after_seconds
            ]
        )
        local_stream_degraded = operational_state.feed_health_state.value != "HEALTHY"
        observability = ObservabilityStateService(self.session).build_summary(
            now=now,
            local_details=details,
            stale_runtime_count=stale_runtime_count,
            stale_price_runtime_count=stale_price_runtime_count,
            local_stream_degraded=local_stream_degraded,
            local_polling_fallback_active=(
                operational_state.feed_source_state.value == "POLLING_FALLBACK"
            ),
        )
        audit_write_degraded = bool(observability["audit_write_degraded"])
        polling_fallback_active = bool(observability["polling_fallback_active"])
        stream_degraded = bool(observability["stream_degraded"])
        runtime_degraded = bool(observability["runtime_degraded"])
        last_audit_write_failure = observability["last_audit_write_failure"]
        return {
            "status": str(health_report["status"]),
            "last_heartbeat": details.last_heartbeat,
            "heartbeat_age_ms": self._age_ms(details.last_heartbeat, now),
            "last_price_update": details.last_price_update,
            "last_price_age_ms": self._age_ms(details.last_price_update, now),
            "last_reconciliation": details.last_reconciliation,
            "last_reconciliation_age_ms": self._age_ms(
                details.last_reconciliation, now
            ),
            "last_audit_write_failure": last_audit_write_failure,
            "last_audit_write_failure_age_ms": self._age_ms(
                last_audit_write_failure, now
            ),
            "stream_connected": operational_state.feed_source_state.value == "LIVE",
            "stream_last_tick_at": stream_health.last_tick_at,
            "stream_last_tick_age_ms": self._age_ms(stream_health.last_tick_at, now),
            "subscribed_instrument_count": len(stream_health.subscribed_instruments),
            "desired_instrument_count": len(stream_health.desired_instruments),
            "broker_connected": operational_state.broker_connectivity_state.value
            == "CONNECTED",
            "feed_source_state": operational_state.feed_source_state.value,
            "feed_health_state": operational_state.feed_health_state.value,
            "broker_connectivity_state": operational_state.broker_connectivity_state.value,
            "entry_eligible": operational_state.entry_eligible,
            "exit_eligible": operational_state.exit_eligible,
            "entry_block_reason": operational_state.entry_block_reason,
            "exit_block_reason": operational_state.exit_block_reason,
            "open_risk_management_state": operational_state.open_risk_management_state.value,
            "open_risk_management_reason": operational_state.open_risk_management_reason,
            "audit_write_degraded": audit_write_degraded,
            "polling_fallback_active": polling_fallback_active,
            "polling_fallback_active_instrument_count": int(
                observability["polling_fallback_active_instrument_count"]
            ),
            "stale_stream_instrument_count": int(
                observability["stale_stream_instrument_count"]
            ),
            "stream_degraded": stream_degraded,
            "runtime_degraded": runtime_degraded,
            "degradation_reasons": list(observability["degradation_reasons"]),
            "broker_latency_ms": details.broker_latency_ms,
            "runtime_count": len(runtimes),
            "active_runtime_count": len(active_runtimes),
            "stale_runtime_count": stale_runtime_count,
            "stale_price_runtime_count": stale_price_runtime_count,
            "reconciliation_mismatches": details.reconciliation_mismatches,
            "order_failures_last_5m": details.order_failures_last_5m,
            "rejected_orders_last_5m": details.rejected_orders_last_5m,
            "audit_write_failures_last_5m": int(
                observability["audit_write_failures_last_5m"]
            ),
            "strategies_paused_by_health": details.strategies_paused_by_health,
            "observability": observability,
        }

    @staticmethod
    def _age_ms(value: datetime | None, now: datetime) -> float | None:
        if value is None:
            return None
        normalized = (
            value.astimezone(UTC)
            if value.tzinfo is not None
            else value.replace(tzinfo=UTC)
        )
        return round((now - normalized).total_seconds() * 1000, 2)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
