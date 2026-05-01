from __future__ import annotations

from time import perf_counter

from sqlmodel import Session

from app.core.broker import BrokerAccountSummary, BrokerPosition
from app.core.broker_factory import get_broker
from app.core.ig_broker import IGBrokerError
from app.core.logging import get_logger
from app.models.trade import Position
from app.services.health_service import get_health_service
from app.services.reconciliation_service import ReconciliationService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class BrokerService:
    """Thin application service for read-only broker connectivity checks."""

    def list_remote_positions(self) -> list[BrokerPosition]:
        started_at = perf_counter()
        try:
            positions = get_broker().get_positions()
        except Exception:
            get_health_service().update_broker_state(
                connected=False, latency_ms=(perf_counter() - started_at) * 1000
            )
            raise
        get_health_service().update_broker_state(
            connected=True, latency_ms=(perf_counter() - started_at) * 1000
        )
        return positions

    def get_account_summary(self) -> BrokerAccountSummary:
        started_at = perf_counter()
        try:
            summary = get_broker().get_account_summary()
        except Exception:
            get_health_service().update_broker_state(
                connected=False, latency_ms=(perf_counter() - started_at) * 1000
            )
            raise
        get_health_service().update_broker_state(
            connected=True, latency_ms=(perf_counter() - started_at) * 1000
        )
        return summary

    def reconcile_positions(self, session: Session) -> list[Position]:
        trade_service = TradeService(session)
        try:
            return ReconciliationService(trade_service).reconcile_open_positions()
        except IGBrokerError as exc:
            get_health_service().update_broker_state(connected=False)
            logger.error(
                "Broker reconciliation unavailable; returning persisted local positions",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "event_category": "reconciliation",
                    "event_type": "reconciliation.broker_unavailable",
                    "event_title": "Broker reconciliation failed",
                },
            )
            return trade_service.list_positions()
