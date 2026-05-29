from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from threading import RLock

from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.models.strategy_governance import (
    GovernanceApprovalState,
    StrategyFamilyGovernance,
)
from app.models.trade import Position
from app.services.observability_state_service import (
    OBSERVABILITY_STATE_AUDIT_WRITE,
    OBSERVABILITY_STATE_POLLING_FALLBACK,
    OBSERVABILITY_STATE_RUNTIME_PAUSED,
    OBSERVABILITY_STATE_STREAM_CONNECTION,
    OBSERVABILITY_STATE_STREAM_STALE,
    ObservabilityStateService,
)
from app.services.operator_control_service import OperatorControlService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class SystemHealth(BaseModel):
    last_heartbeat: datetime
    last_price_update: datetime | None
    last_reconciliation: datetime | None
    last_audit_write_failure: datetime | None
    stream_connected: bool
    broker_connected: bool
    broker_latency_ms: float | None
    order_failures_last_5m: int
    rejected_orders_last_5m: int
    audit_write_failures_last_5m: int
    polling_fallback_active_instrument_count: int
    stale_stream_instrument_count: int
    reconciliation_mismatches: int
    strategies_paused_by_health: int


class HealthService:
    WINDOW = timedelta(minutes=5)
    STALE_PRICE_THRESHOLD = timedelta(seconds=5)

    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            now = datetime.now(UTC)
            self._last_heartbeat = now
            self._last_price_update: datetime | None = None
            self._last_reconciliation: datetime | None = None
            self._last_audit_write_failure: datetime | None = None
            self._stream_connected = False
            self._broker_connected = False
            self._broker_latency_ms: float | None = None
            self._order_failures: deque[datetime] = deque()
            self._rejected_orders: deque[datetime] = deque()
            self._audit_write_failures: deque[datetime] = deque()
            self._polling_fallback_active_instruments: set[str] = set()
            self._stale_stream_instruments: set[str] = set()
            self._reconciliation_mismatches = 0
            self._strategies_paused_by_health = 0
            self._last_reported_status: str | None = None

    def heartbeat(self, when: datetime | None = None) -> None:
        with self._lock:
            self._last_heartbeat = self._normalize_time(when)
        self._emit_status_transition_if_needed()

    def record_price_update(
        self, when: datetime | None = None, *, stream_connected: bool | None = None
    ) -> None:
        normalized_when = self._normalize_time(when)
        with self._lock:
            self._last_price_update = normalized_when
            if stream_connected is not None:
                self._stream_connected = stream_connected
        if stream_connected is not None:
            self._record_stream_connection_observability(
                connected=stream_connected,
                observed_at=normalized_when,
            )
        self._emit_status_transition_if_needed()

    def set_stream_connected(self, connected: bool) -> None:
        with self._lock:
            self._stream_connected = connected
        self._record_stream_connection_observability(connected=connected)
        self._emit_status_transition_if_needed()

    def update_broker_state(
        self,
        *,
        connected: bool,
        latency_ms: float | None = None,
    ) -> None:
        with self._lock:
            self._broker_connected = connected
            if latency_ms is not None:
                self._broker_latency_ms = round(latency_ms, 2)
        self._emit_status_transition_if_needed()

    def record_order_failure(self, when: datetime | None = None) -> None:
        timestamp = self._normalize_time(when)
        with self._lock:
            self._order_failures.append(timestamp)
            self._trim_windows(timestamp)
        self._emit_status_transition_if_needed()

    def record_order_rejection(self, when: datetime | None = None) -> None:
        timestamp = self._normalize_time(when)
        with self._lock:
            self._order_failures.append(timestamp)
            self._rejected_orders.append(timestamp)
            self._trim_windows(timestamp)
        self._emit_status_transition_if_needed()

    def record_reconciliation(
        self, *, mismatches: int, when: datetime | None = None
    ) -> None:
        with self._lock:
            self._last_reconciliation = self._normalize_time(when)
            self._reconciliation_mismatches = mismatches
        self._emit_status_transition_if_needed()

    def set_paused_strategies(self, count: int) -> None:
        with self._lock:
            self._strategies_paused_by_health = max(count, 0)
            paused_count = self._strategies_paused_by_health
        ttl = ObservabilityStateService.default_ttl(
            self.settings.system_health_heartbeat_interval_seconds * 3
        )
        observed_at = datetime.now(UTC)
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_RUNTIME_PAUSED,
            source="health_service.set_paused_strategies",
            active=paused_count > 0,
            observed_at=observed_at,
            expires_at=observed_at + ttl,
            payload={"paused_count": paused_count},
        )
        self._emit_status_transition_if_needed()

    def record_audit_write_failure(self, when: datetime | None = None) -> None:
        timestamp = self._normalize_time(when)
        with self._lock:
            self._last_audit_write_failure = timestamp
            self._audit_write_failures.append(timestamp)
            self._trim_windows(timestamp)
            failure_count = len(self._audit_write_failures)
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
            source="health_service.record_audit_write_failure",
            active=True,
            observed_at=timestamp,
            expires_at=timestamp + self.WINDOW,
            payload={"failure_count_window": failure_count},
        )
        self._emit_status_transition_if_needed()

    def set_polling_fallback_active(self, instrument: str, active: bool) -> None:
        normalized = str(instrument)
        with self._lock:
            if active:
                self._polling_fallback_active_instruments.add(normalized)
            else:
                self._polling_fallback_active_instruments.discard(normalized)
        ttl = ObservabilityStateService.default_ttl(
            max(
                self.settings.market_data_poll_interval_seconds * 3,
                self.settings.ig_streaming_stale_after_seconds,
            )
        )
        observed_at = datetime.now(UTC)
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_POLLING_FALLBACK,
            source="health_service.set_polling_fallback_active",
            active=active,
            observed_at=observed_at,
            expires_at=observed_at + ttl,
            scope_type=ObservabilityStateService.INSTRUMENT_SCOPE,
            scope_id=normalized,
            payload={"instrument": normalized},
        )
        self._emit_status_transition_if_needed()

    def set_stream_stale(self, instrument: str, stale: bool) -> None:
        normalized = str(instrument)
        with self._lock:
            if stale:
                self._stale_stream_instruments.add(normalized)
            else:
                self._stale_stream_instruments.discard(normalized)
        ttl = ObservabilityStateService.default_ttl(
            max(
                self.settings.market_data_poll_interval_seconds * 3,
                self.settings.ig_streaming_stale_after_seconds,
            )
        )
        observed_at = datetime.now(UTC)
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_STREAM_STALE,
            source="health_service.set_stream_stale",
            active=stale,
            observed_at=observed_at,
            expires_at=observed_at + ttl,
            scope_type=ObservabilityStateService.INSTRUMENT_SCOPE,
            scope_id=normalized,
            payload={"instrument": normalized},
        )
        self._emit_status_transition_if_needed()

    def get_system_health(self) -> SystemHealth:
        with self._lock:
            now = datetime.now(UTC)
            self._trim_windows(now)
            return SystemHealth(
                last_heartbeat=self._last_heartbeat,
                last_price_update=self._last_price_update,
                last_reconciliation=self._last_reconciliation,
                last_audit_write_failure=self._last_audit_write_failure,
                stream_connected=self._stream_connected,
                broker_connected=self._broker_connected,
                broker_latency_ms=self._broker_latency_ms,
                order_failures_last_5m=len(self._order_failures),
                rejected_orders_last_5m=len(self._rejected_orders),
                audit_write_failures_last_5m=len(self._audit_write_failures),
                polling_fallback_active_instrument_count=len(
                    self._polling_fallback_active_instruments
                ),
                stale_stream_instrument_count=len(self._stale_stream_instruments),
                reconciliation_mismatches=self._reconciliation_mismatches,
                strategies_paused_by_health=self._strategies_paused_by_health,
            )

    def get_health_report(self) -> dict[str, str | SystemHealth]:
        details = self.get_system_health()
        return {"status": self._classify_status(details), "details": details}

    def _emit_status_transition_if_needed(self) -> None:
        report = self.get_health_report()
        status = str(report["status"])
        with self._lock:
            previous_status = self._last_reported_status
            self._last_reported_status = status
        if status != previous_status and status in {"degraded", "critical"}:
            logger.warning(
                "System health degraded",
                extra={
                    "event": "health_degraded",
                    "status": status,
                    "details": report["details"].model_dump(mode="json"),
                },
            )

    def _classify_status(self, details: SystemHealth) -> str:
        if self._is_idle():
            return "idle"
        if self._is_armed():
            return "armed"
        price_is_fresh = self._is_price_fresh(details.last_price_update)
        if (
            details.last_price_update is None
            or not details.broker_connected
            or not details.stream_connected
        ):
            return "critical"
        if (
            not price_is_fresh
            or details.order_failures_last_5m >= 3
            or details.audit_write_failures_last_5m > 0
        ):
            return "degraded"
        return "ok"

    def _is_idle(self) -> bool:
        return (
            not self._has_live_operational_demand() and not self._has_autonomy_armed()
        )

    def _is_armed(self) -> bool:
        return not self._has_live_operational_demand() and self._has_autonomy_armed()

    def _has_live_operational_demand(self) -> bool:
        if runtime_manager.list_active_instruments():
            return True
        with Session(engine) as session:
            has_open_positions = session.exec(
                select(Position.id).where(Position.is_open.is_(True)).limit(1)
            ).first()
            if has_open_positions is not None:
                return True
            return TradeService(session).has_pending_trade_intents()

    def _has_autonomy_armed(self) -> bool:
        with Session(engine) as session:
            operator_control = OperatorControlService(session)
            if not operator_control.get_effective_autonomous_control_enabled():
                return False
            record = session.exec(
                select(StrategyFamilyGovernance.id)
                .where(
                    StrategyFamilyGovernance.approval_state
                    == GovernanceApprovalState.APPROVED.value,
                    StrategyFamilyGovernance.autonomous_operation_allowed.is_(True),
                    StrategyFamilyGovernance.emergency_stop.is_(False),
                )
                .limit(1)
            ).first()
            return record is not None

    def _is_price_fresh(self, last_price_update: datetime | None) -> bool:
        if last_price_update is None:
            return False
        return (
            datetime.now(UTC) - last_price_update.astimezone(UTC)
            <= self.STALE_PRICE_THRESHOLD
        )

    def _trim_windows(self, now: datetime) -> None:
        cutoff = now - self.WINDOW
        while self._order_failures and self._order_failures[0] < cutoff:
            self._order_failures.popleft()
        while self._rejected_orders and self._rejected_orders[0] < cutoff:
            self._rejected_orders.popleft()
        while self._audit_write_failures and self._audit_write_failures[0] < cutoff:
            self._audit_write_failures.popleft()

    @staticmethod
    def _normalize_time(when: datetime | None) -> datetime:
        if when is None:
            return datetime.now(UTC)
        return when.astimezone(UTC)

    def _record_stream_connection_observability(
        self, *, connected: bool, observed_at: datetime | None = None
    ) -> None:
        timestamp = self._normalize_time(observed_at)
        ttl = ObservabilityStateService.default_ttl(
            max(
                self.settings.market_data_poll_interval_seconds * 3,
                self.settings.ig_streaming_stale_after_seconds,
                self.settings.system_health_heartbeat_interval_seconds * 3,
            )
        )
        ObservabilityStateService.record_state(
            state_key=OBSERVABILITY_STATE_STREAM_CONNECTION,
            source="health_service.set_stream_connected",
            active=not connected,
            observed_at=timestamp,
            expires_at=timestamp + ttl,
            payload={"connected": connected},
        )


_health_service: HealthService | None = None


def get_health_service() -> HealthService:
    global _health_service
    if _health_service is None:
        _health_service = HealthService()
    return _health_service
