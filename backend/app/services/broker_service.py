from __future__ import annotations

from app.core.broker import BrokerPosition
from sqlmodel import Session

from app.core.broker import BrokerAccountSummary, BrokerPosition
from app.core.broker_factory import get_broker
from app.models.trade import Position
from app.services.reconciliation_service import ReconciliationService
from app.services.trade_service import TradeService


class BrokerService:
    """Thin application service for read-only broker connectivity checks."""

    def list_remote_positions(self) -> list[BrokerPosition]:
        return get_broker().get_positions()

    def get_account_summary(self) -> BrokerAccountSummary:
        return get_broker().get_account_summary()

    def reconcile_positions(self, session: Session) -> list[Position]:
        return ReconciliationService(TradeService(session)).reconcile_open_positions()
