from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.broker import BrokerError, BrokerMarketDetails
from app.core.broker_factory import get_broker
from app.core.config import get_settings
from app.core.instrument_catalog import list_market_instruments
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.strategies.base import ScreeningSnapshot
from app.strategies.registry import strategy_registry
from app.db.session import engine
from app.services.broker_service import BrokerService
from app.services.coverage_allocator_service import CoverageAllocatorService
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.promotion_request_service import PromotionRequestService
from app.services.strategy_deployment_manager_service import (
    StrategyDeploymentManagerService,
)
from app.services.strategy_service import StrategyService
from app.services.watchlist_service import get_watchlist_service

logger = get_logger(__name__)


class MarketDataService:
    """
    Manage bounded Tier 1 fallback pricing plus low-frequency Tier 2 screening refresh.
    """

    def __init__(self, *, poll_prices: bool = True) -> None:
        self.settings = get_settings()
        self.poll_prices = poll_prices
        self.health_service = get_health_service()
        self.broker = get_broker()
        self._activity_level_by_instrument = {
            instrument.epic: instrument.activity_level
            for instrument in list_market_instruments()
        }
        self._fallback_active_instruments: set[str] = set()
        self._stale_stream_instruments: set[str] = set()
        self._fallback_reason_first_seen_at: dict[str, datetime] = {}
        self._healthy_first_seen_at: dict[str, datetime] = {}
        self._last_tier2_refresh_at: datetime | None = None
        self._screeners = strategy_registry.create_screeners()

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
        await self._process_tier1_fallback_once()
        await self._refresh_tier2_once()

    async def _process_tier1_fallback_once(self) -> None:
        active_instruments = list(
            get_watchlist_service().get_streaming_plan().instruments
        )
        if not active_instruments:
            return

        with Session(engine) as session:
            BrokerService().reconcile_positions(session)
            strategy_service = StrategyService(session)
            for instrument in active_instruments:
                self._update_polling_health_transition(instrument)
                if not self._should_poll_instrument(instrument):
                    continue
                instrument_engines = runtime_manager.get_engines_for_instrument(
                    instrument
                )
                if not instrument_engines:
                    continue
                trading_engine = instrument_engines[0][1]
                try:
                    market_details = await asyncio.to_thread(
                        trading_engine.broker.get_market_details, instrument
                    )
                except BrokerError as exc:
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
                self.health_service.record_price_update()

    async def _refresh_tier2_once(self) -> None:
        if not self.settings.tier2_refresh_enabled:
            return
        now = self._now()
        if self._last_tier2_refresh_at is not None:
            elapsed = (now - self._last_tier2_refresh_at).total_seconds()
            if elapsed < self.settings.tier2_refresh_interval_seconds:
                return

        refresh_plan = get_watchlist_service().get_tier2_refresh_plan()
        if not refresh_plan.instruments:
            self._last_tier2_refresh_at = now
            return

        with Session(engine) as session:
            promotion_service = PromotionRequestService(session)
            for instrument in refresh_plan.instruments:
                try:
                    market_details = await asyncio.to_thread(
                        self.broker.get_market_details, instrument
                    )
                except BrokerError as exc:
                    logger.warning(
                        "Tier 2 market refresh failed",
                        extra={
                            "instrument": instrument,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue
                refreshed_at = self._now()
                get_watchlist_service().record_tier2_refresh(
                    instrument=instrument, refreshed_at=refreshed_at
                )
                snapshot = ScreeningSnapshot(
                    instrument=instrument,
                    market_details=market_details,
                    refreshed_at=refreshed_at,
                    streamed=instrument in refresh_plan.streamed_instruments,
                    source_tier="TIER2",
                )
                intents = [
                    intent
                    for intent in (
                        scanner.evaluate(snapshot) for scanner in self._screeners
                    )
                    if intent is not None
                ]
                top_intent = max(intents, key=lambda intent: intent.score, default=None)
                domain_event_service.record_event(
                    event_type="market.tier2_refreshed",
                    category="market",
                    severity="info",
                    source="market_data_service.tier2_refresh",
                    title="Tier 2 market refresh completed",
                    message=f"Tier 2 refresh evaluated {instrument}.",
                    instrument=instrument,
                    payload_json={
                        "scanner_count": len(self._screeners),
                        "promotion_score": top_intent.score
                        if top_intent is not None
                        else None,
                        "promotion_source": top_intent.scanner_name
                        if top_intent is not None
                        else None,
                        "market_status": market_details.market_status,
                        "tradable": market_details.tradable,
                        "streamed": instrument in refresh_plan.streamed_instruments,
                    },
                    created_at=refreshed_at,
                )
                if instrument in refresh_plan.streamed_instruments:
                    continue
                if top_intent is None:
                    continue
                request = promotion_service.create_or_refresh(
                    instrument=instrument,
                    source=top_intent.scanner_name,
                    reason=top_intent.reason,
                    score=top_intent.score,
                    requested_at=refreshed_at,
                    expires_at=refreshed_at.replace(tzinfo=UTC)
                    + self._promotion_ttl_delta(),
                    market_status=market_details.market_status,
                    tradable=market_details.tradable,
                    requested_frequency=top_intent.requested_frequency
                    or self.settings.ig_streaming_requested_frequency,
                )
                domain_event_service.record_event(
                    event_type="coverage.promotion_requested",
                    category="coverage",
                    severity="info",
                    source="market_data_service.tier2_refresh",
                    title="Tier 2 promotion request created",
                    message=f"Tier 2 screening requested live coverage for {instrument}.",
                    instrument=instrument,
                    actor_type="service",
                    actor_id=top_intent.scanner_name,
                    payload_json={
                        "promotion_request_id": request.id,
                        "score": top_intent.score,
                        "source": top_intent.scanner_name,
                        "reason": top_intent.reason,
                        "market_status": market_details.market_status,
                        "tradable": market_details.tradable,
                    },
                    created_at=refreshed_at,
                )

            allocation_result = CoverageAllocatorService(
                session
            ).allocate_pending_promotions(now=self._now())
            if any(
                [
                    allocation_result.accepted,
                    allocation_result.rejected,
                    allocation_result.expired,
                ]
            ):
                domain_event_service.record_event(
                    event_type="coverage.allocation_cycle_completed",
                    category="coverage",
                    severity="info",
                    source="market_data_service.tier2_refresh",
                    title="Coverage allocation cycle completed",
                    message="Coverage allocator processed pending promotion requests.",
                    payload_json={
                        "accepted": allocation_result.accepted,
                        "rejected": allocation_result.rejected,
                        "expired": allocation_result.expired,
                        "skipped": allocation_result.skipped,
                    },
                    created_at=self._now(),
                )

            deployment_result = StrategyDeploymentManagerService(session).reconcile(
                now=self._now()
            )
            if any(
                [
                    deployment_result.deployed,
                    deployment_result.paused,
                    deployment_result.blocked,
                    deployment_result.degraded,
                    deployment_result.emergency_stopped,
                ]
            ):
                domain_event_service.record_event(
                    event_type="control_plane.reconciliation_cycle_completed",
                    category="strategy",
                    severity="info",
                    source="market_data_service.tier2_refresh",
                    title="Autonomous deployment cycle completed",
                    message="Deployment manager evaluated approved strategy families.",
                    payload_json={
                        "deployed": deployment_result.deployed,
                        "paused": deployment_result.paused,
                        "blocked": deployment_result.blocked,
                        "degraded": deployment_result.degraded,
                        "emergency_stopped": deployment_result.emergency_stopped,
                    },
                    created_at=self._now(),
                )

        self._last_tier2_refresh_at = now

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
        last_tick_at = stream_service.get_last_tick_at(instrument)
        if last_tick_at is None:
            self.health_service.set_stream_connected(False)
            return "no_ticks_seen"

        seconds_since_last_tick = (
            self._now() - last_tick_at.astimezone(UTC)
        ).total_seconds()
        stale_after_seconds = max(
            self.settings.market_data_poll_interval_seconds * 3,
            self.settings.ig_streaming_stale_after_seconds,
        )
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
        now = self._now()
        instrument_last_tick_at = stream_service.get_last_tick_at(instrument)
        payload = {
            "reason": reason,
            "stream_enabled": health.enabled,
            "stream_connected": health.connected,
            "subscribed_instruments": list(health.subscribed_instruments),
            "last_tick_at": health.last_tick_at.isoformat()
            if health.last_tick_at is not None
            else None,
            "instrument_last_tick_at": (
                instrument_last_tick_at.isoformat()
                if instrument_last_tick_at is not None
                else None
            ),
        }
        debounce_window = self.settings.ig_streaming_transition_debounce_seconds

        if reason is not None:
            self._healthy_first_seen_at.pop(instrument, None)
            first_seen_at = self._fallback_reason_first_seen_at.setdefault(
                instrument, now
            )
            if (now - first_seen_at).total_seconds() < debounce_window:
                return
        else:
            self._fallback_reason_first_seen_at.pop(instrument, None)
            if (
                instrument in self._fallback_active_instruments
                or instrument in self._stale_stream_instruments
            ):
                healthy_since = self._healthy_first_seen_at.setdefault(instrument, now)
                if (now - healthy_since).total_seconds() < debounce_window:
                    return
            else:
                self._healthy_first_seen_at.pop(instrument, None)

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
            self._healthy_first_seen_at.pop(instrument, None)
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
        if (
            reason == "stale_stream"
            and instrument not in self._stale_stream_instruments
        ):
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
            self._healthy_first_seen_at.pop(instrument, None)
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
    def _now() -> datetime:
        return datetime.now(UTC)

    def _promotion_ttl_delta(self):
        from datetime import timedelta

        return timedelta(seconds=self.settings.tier2_promotion_ttl_seconds)

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
