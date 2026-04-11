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
from app.models.strategy_governance import GovernanceApprovalState, StrategyFamilyGovernance
from app.models.trade import Position
from app.services.operator_control_service import OperatorControlService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class SystemHealth(BaseModel):
    last_heartbeat: datetime
    last_price_update: datetime | None
    last_reconciliation: datetime | None
    stream_connected: bool
    broker_connected: bool
    broker_latency_ms: float | None
    order_failures_last_5m: int
    rejected_orders_last_5m: int
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
            self._stream_connected = False
            self._broker_connected = False
            self._broker_latency_ms: float | None = None
            self._order_failures: deque[datetime] = deque()
            self._rejected_orders: deque[datetime] = deque()
            self._reconciliation_mismatches = 0
            self._strategies_paused_by_health = 0
            self._last_reported_status: str | None = None

    def heartbeat(self, when: datetime | None = None) -> None:
        with self._lock:
            self._last_heartbeat = self._normalize_time(when)
        self._emit_status_transition_if_needed()

    def record_price_update(self, when: datetime | None = None, *, stream_connected: bool | None = None) -> None:
        with self._lock:
            self._last_price_update = self._normalize_time(when)
            if stream_connected is not None:
                self._stream_connected = stream_connected
        self._emit_status_transition_if_needed()

    def set_stream_connected(self, connected: bool) -> None:
        with self._lock:
            self._stream_connected = connected
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

    def record_reconciliation(self, *, mismatches: int, when: datetime | None = None) -> None:
        with self._lock:
            self._last_reconciliation = self._normalize_time(when)
            self._reconciliation_mismatches = mismatches
        self._emit_status_transition_if_needed()

    def set_paused_strategies(self, count: int) -> None:
        with self._lock:
            self._strategies_paused_by_health = max(count, 0)
        self._emit_status_transition_if_needed()

    def get_system_health(self) -> SystemHealth:
        with self._lock:
            now = datetime.now(UTC)
            self._trim_windows(now)
            return SystemHealth(
                last_heartbeat=self._last_heartbeat,
                last_price_update=self._last_price_update,
                last_reconciliation=self._last_reconciliation,
                stream_connected=self._stream_connected,
                broker_connected=self._broker_connected,
                broker_latency_ms=self._broker_latency_ms,
                order_failures_last_5m=len(self._order_failures),
                rejected_orders_last_5m=len(self._rejected_orders),
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
        if details.last_price_update is None or not details.broker_connected or not details.stream_connected:
            return "critical"
        if not price_is_fresh or details.order_failures_last_5m >= 3:
            return "degraded"
        return "ok"

    def _is_idle(self) -> bool:
        return not self._has_live_operational_demand() and not self._has_autonomy_armed()

    def _is_armed(self) -> bool:
        return not self._has_live_operational_demand() and self._has_autonomy_armed()

    def _has_live_operational_demand(self) -> bool:
        if runtime_manager.list_active_instruments():
            return True
        with Session(engine) as session:
            has_open_positions = session.exec(select(Position.id).where(Position.is_open.is_(True)).limit(1)).first()
            if has_open_positions is not None:
                return True
            return TradeService(session).has_pending_trade_intents()

    def _has_autonomy_armed(self) -> bool:
        with Session(engine) as session:
            operator_control = OperatorControlService(session)
            if not operator_control.get_effective_autonomous_control_enabled():
                return False
            record = session.exec(
                select(StrategyFamilyGovernance.id).where(
                    StrategyFamilyGovernance.approval_state == GovernanceApprovalState.APPROVED.value,
                    StrategyFamilyGovernance.autonomous_operation_allowed.is_(True),
                    StrategyFamilyGovernance.emergency_stop.is_(False),
                ).limit(1)
            ).first()
            return record is not None

    def _is_price_fresh(self, last_price_update: datetime | None) -> bool:
        if last_price_update is None:
            return False
        return datetime.now(UTC) - last_price_update.astimezone(UTC) <= self.STALE_PRICE_THRESHOLD

    def _trim_windows(self, now: datetime) -> None:
        cutoff = now - self.WINDOW
        while self._order_failures and self._order_failures[0] < cutoff:
            self._order_failures.popleft()
        while self._rejected_orders and self._rejected_orders[0] < cutoff:
            self._rejected_orders.popleft()

    @staticmethod
    def _normalize_time(when: datetime | None) -> datetime:
        if when is None:
            return datetime.now(UTC)
        return when.astimezone(UTC)


_health_service: HealthService | None = None


def get_health_service() -> HealthService:
    global _health_service
    if _health_service is None:
        _health_service = HealthService()
    return _health_service
