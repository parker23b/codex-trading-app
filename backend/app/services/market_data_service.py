from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.core.broker import BrokerMarketDetails
from app.core.ig_broker import IGBrokerError
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.services.broker_service import BrokerService
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.strategy_service import StrategyService

logger = get_logger(__name__)


class MarketDataService:
    """
    Poll broker-backed prices and push them through the existing strategy flow.
    """

    def __init__(self, *, poll_prices: bool = True) -> None:
        self.settings = get_settings()
        self.poll_prices = poll_prices

    async def run(self) -> None:
        logger.info(
            "Market data loop started",
            extra={
                "poll_interval": self.settings.market_data_poll_interval_seconds,
                "poll_prices": self.poll_prices,
            },
        )
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
                if not self._should_poll_instrument(instrument):
                    continue
                try:
                    market_details = await asyncio.to_thread(trading_engine.broker.get_market_details, instrument)
                except IGBrokerError as exc:
                    runtime_manager.set_price_error(instrument, str(exc))
                    logger.warning("Market price unavailable", extra={"instrument": instrument, "error": str(exc)})
                    continue
                strategy_service.process_price_update(
                    instrument,
                    self._select_price(instrument, market_details),
                    bid=market_details.bid,
                    ask=market_details.offer,
                    high=market_details.high,
                    low=market_details.low,
                    market_status=market_details.market_status,
                    tradable=market_details.tradable,
                    received_at=datetime.now(UTC),
                )

    def _should_poll_instrument(self, instrument: str) -> bool:
        if self.poll_prices:
            return True

        stream_service = get_ig_streaming_service()
        health = stream_service.get_health()
        if not health.enabled or not health.connected:
            return True
        if instrument not in health.subscribed_instruments:
            return True
        if health.last_tick_at is None:
            return True

        seconds_since_last_tick = (datetime.now(UTC) - health.last_tick_at.astimezone(UTC)).total_seconds()
        stale_after_seconds = max(self.settings.market_data_poll_interval_seconds * 2, 5.0)
        return seconds_since_last_tick > stale_after_seconds

    @staticmethod
    def _select_price(instrument: str, details: BrokerMarketDetails) -> float:
        if details.bid is not None and details.offer is not None:
            return round((details.bid + details.offer) / 2, 5)
        if details.bid is not None:
            return details.bid
        if details.offer is not None:
            return details.offer
        if details.high is not None and details.low is not None:
            return round((details.high + details.low) / 2, 5)
        last_price = runtime_manager.get_last_price(instrument)
        if last_price is not None:
            return last_price
        raise ValueError(f"No usable price available for instrument '{instrument}'.")
