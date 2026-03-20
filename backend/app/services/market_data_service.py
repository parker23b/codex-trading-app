from __future__ import annotations

import asyncio

from sqlmodel import Session

from app.core.config import get_settings
from app.core.ig_broker import IGBrokerError
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.services.broker_service import BrokerService
from app.services.strategy_service import StrategyService

logger = get_logger(__name__)


class MarketDataService:
    """
    Poll broker-backed prices and push them through the existing strategy flow.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def run(self) -> None:
        logger.info("Market data loop started", extra={"poll_interval": self.settings.market_data_poll_interval_seconds})
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Market data poll failed", extra={"error": str(exc)})
            await asyncio.sleep(self.settings.market_data_poll_interval_seconds)

    async def _poll_once(self) -> None:
        active_engines = list(runtime_manager.engines.items())
        if not active_engines:
            return

        with Session(engine) as session:
            BrokerService().reconcile_positions(session)
            strategy_service = StrategyService(session)
            for instrument, trading_engine in active_engines:
                try:
                    latest_price = await asyncio.to_thread(trading_engine.broker.get_latest_price, instrument)
                except IGBrokerError as exc:
                    logger.warning("Market price unavailable", extra={"instrument": instrument, "error": str(exc)})
                    continue
                strategy_service.process_price_update(instrument, latest_price)
