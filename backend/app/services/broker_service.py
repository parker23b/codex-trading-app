from __future__ import annotations

from sqlmodel import Session

from app.core.broker import BrokerAccountSummary, BrokerPosition
from app.core.broker_factory import get_broker
from app.core.ig_broker import IGBrokerError
from app.core.logging import get_logger
from app.models.trade import Position
from app.services.reconciliation_service import ReconciliationService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class BrokerService:
    """Thin application service for read-only broker connectivity checks."""

    def list_remote_positions(self) -> list[BrokerPosition]:
        return get_broker().get_positions()

    def get_account_summary(self) -> BrokerAccountSummary:
        return get_broker().get_account_summary()

    def reconcile_positions(self, session: Session) -> list[Position]:
        trade_service = TradeService(session)
        try:
            return ReconciliationService(trade_service).reconcile_open_positions()
        except IGBrokerError as exc:
            logger.warning(
                "Broker reconciliation unavailable; returning persisted local positions",
                extra={"error": str(exc)},
            )
            return trade_service.list_positions()
