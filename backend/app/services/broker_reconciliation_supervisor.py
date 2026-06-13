from __future__ import annotations

import asyncio

from sqlmodel import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import engine
from app.services.broker_service import BrokerService

logger = get_logger(__name__)


class BrokerReconciliationSupervisor:
    """Reconcile broker truth independently of market-data coverage."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def run(self) -> None:
        logger.info(
            "Broker reconciliation supervisor started",
            extra={
                "interval": self.settings.broker_reconciliation_interval_seconds,
            },
        )
        while True:
            try:
                await asyncio.to_thread(self.reconcile_once)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Broker reconciliation supervisor failed",
                    extra={"error": str(exc)},
                )
            await asyncio.sleep(self.settings.broker_reconciliation_interval_seconds)

    def reconcile_once(self) -> None:
        with Session(engine) as session:
            BrokerService().reconcile_positions(session)
