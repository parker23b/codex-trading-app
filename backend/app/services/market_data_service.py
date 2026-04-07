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
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
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
        self.health_service = get_health_service()
        self._fallback_active_instruments: set[str] = set()
        self._stale_stream_instruments: set[str] = set()

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
        active_instruments = runtime_manager.list_active_instruments()
        if not active_instruments:
            return
        self.health_service.set_stream_connected(True)

        with Session(engine) as session:
            BrokerService().reconcile_positions(session)
            strategy_service = StrategyService(session)
            for instrument in active_instruments:
                self._update_polling_health_transition(instrument)
                if not self._should_poll_instrument(instrument):
                    continue
                instrument_engines = runtime_manager.get_engines_for_instrument(instrument)
                if not instrument_engines:
                    continue
                trading_engine = instrument_engines[0][1]
                try:
                    market_details = await asyncio.to_thread(trading_engine.broker.get_market_details, instrument)
                except IGBrokerError as exc:
                    runtime_manager.set_price_error(instrument, str(exc))
                    logger.error(
                        "Market price unavailable",
                        extra={
                            "instrument": instrument,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "event_category": "health",
                            "event_type": "health.market_data_error",
                            "event_title": "Market price lookup failed",
                        },
                    )
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
                self.health_service.record_price_update(stream_connected=True)

    def _should_poll_instrument(self, instrument: str) -> bool:
        return self._polling_fallback_reason(instrument) is not None

    def _polling_fallback_reason(self, instrument: str) -> str | None:
        if self.poll_prices:
            return "polling_primary"

        stream_service = get_ig_streaming_service()
        health = stream_service.get_health()
        if not health.enabled or not health.connected:
            self.health_service.set_stream_connected(False)
            return "stream_unavailable"
        if instrument not in health.subscribed_instruments:
            return "instrument_not_subscribed"
        if health.last_tick_at is None:
            self.health_service.set_stream_connected(False)
            return "no_ticks_seen"

        seconds_since_last_tick = (datetime.now(UTC) - health.last_tick_at.astimezone(UTC)).total_seconds()
        stale_after_seconds = max(self.settings.market_data_poll_interval_seconds * 2, 5.0)
        if seconds_since_last_tick > stale_after_seconds:
            self.health_service.set_stream_connected(False)
            return "stale_stream"
        self.health_service.set_stream_connected(True)
        return None

    def _update_polling_health_transition(self, instrument: str) -> None:
        if self.poll_prices:
            return

        stream_service = get_ig_streaming_service()
        health = stream_service.get_health()
        reason = self._polling_fallback_reason(instrument)
        payload = {
            "reason": reason,
            "stream_enabled": health.enabled,
            "stream_connected": health.connected,
            "subscribed_instruments": list(health.subscribed_instruments),
            "last_tick_at": health.last_tick_at.isoformat() if health.last_tick_at is not None else None,
        }
        if reason is not None and instrument not in self._fallback_active_instruments:
            self._fallback_active_instruments.add(instrument)
            domain_event_service.record_event(
                event_type="health.polling_fallback_started",
                category="health",
                severity="warning",
                source="market_data_service.polling_fallback",
                title="Polling fallback started",
                message=f"Polling fallback activated for {instrument}.",
                instrument=instrument,
                payload_json=payload,
            )
        if reason is None and instrument in self._fallback_active_instruments:
            self._fallback_active_instruments.remove(instrument)
            domain_event_service.record_event(
                event_type="health.polling_fallback_stopped",
                category="health",
                severity="info",
                source="market_data_service.polling_fallback",
                title="Polling fallback stopped",
                message=f"Streaming resumed cleanly for {instrument}.",
                instrument=instrument,
                payload_json=payload,
            )
        if reason == "stale_stream" and instrument not in self._stale_stream_instruments:
            self._stale_stream_instruments.add(instrument)
            domain_event_service.record_event(
                event_type="health.stream_stale",
                category="health",
                severity="warning",
                source="market_data_service.polling_fallback",
                title="Streaming data went stale",
                message=f"Streaming data became stale for {instrument}.",
                instrument=instrument,
                payload_json=payload,
            )
        if reason != "stale_stream" and instrument in self._stale_stream_instruments:
            self._stale_stream_instruments.remove(instrument)
            domain_event_service.record_event(
                event_type="health.stream_recovered",
                category="health",
                severity="info",
                source="market_data_service.polling_fallback",
                title="Streaming data recovered",
                message=f"Streaming data freshness recovered for {instrument}.",
                instrument=instrument,
                payload_json=payload,
            )

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
