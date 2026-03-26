from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session

from app.core.broker_factory import get_broker
from app.core.config import get_settings
from app.core.ig_broker import IGBroker, IGBrokerError, IGStreamingCredentials
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.db.session import engine
from app.services.strategy_service import StrategyService

try:
    from lightstreamer.client import (
        ClientListener,
        LightstreamerClient,
        Subscription,
        SubscriptionListener,
    )
except ImportError:  # pragma: no cover - exercised only when optional runtime dependency is missing
    ClientListener = object  # type: ignore[assignment]
    LightstreamerClient = None  # type: ignore[assignment]
    Subscription = None  # type: ignore[assignment]
    SubscriptionListener = object  # type: ignore[assignment]

if TYPE_CHECKING:
    from lightstreamer.client import ItemUpdate

logger = get_logger(__name__)

PRICE_FIELDS = ["BIDPRICE1", "ASKPRICE1", "TIMESTAMP"]


@dataclass(frozen=True, slots=True)
class StreamPriceUpdate:
    instrument: str
    price: float
    bid: float | None
    ask: float | None
    timestamp: int | None


@dataclass(slots=True)
class StreamHealthState:
    enabled: bool = False
    connected: bool = False
    subscribed_instruments: tuple[str, ...] = ()
    last_tick_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    dependency_ready: bool = False


class _StreamClientListener(ClientListener):
    def __init__(self, service: "IGStreamingService"):
        self._service = service

    def onStatusChange(self, status: str) -> None:  # noqa: N802 - SDK callback shape
        self._service._health.connected = status.startswith("CONNECTED:")
        self._service._health.last_status = status
        logger.info("IG Lightstreamer status changed", extra={"status": status})

    def onServerError(self, code: int, message: str) -> None:  # noqa: N802 - SDK callback shape
        self._service._health.last_error = f"{code}: {message}"
        logger.error("IG Lightstreamer server error", extra={"code": code, "message": message})


class _PriceSubscriptionListener(SubscriptionListener):
    def __init__(self, service: "IGStreamingService"):
        self._service = service

    def onSubscription(self) -> None:  # noqa: N802 - SDK callback shape
        logger.info("IG Lightstreamer price subscription active", extra={"count": len(self._service._subscribed_instruments)})

    def onSubscriptionError(self, code: int, message: str) -> None:  # noqa: N802 - SDK callback shape
        logger.error("IG Lightstreamer subscription failed", extra={"code": code, "message": message})

    def onUnsubscription(self) -> None:  # noqa: N802 - SDK callback shape
        logger.info("IG Lightstreamer price subscription removed")

    def onItemUpdate(self, update: "ItemUpdate") -> None:  # noqa: N802 - SDK callback shape
        item_name = update.getItemName()
        if not item_name:
            return
        parts = item_name.split(":", 2)
        if len(parts) != 3:
            return
        instrument = parts[2]
        bid = self._service._coerce_float(update.getValue("BIDPRICE1"))
        ask = self._service._coerce_float(update.getValue("ASKPRICE1"))
        price = self._service._select_price(bid=bid, ask=ask)
        if price is None:
            return
        timestamp = self._service._coerce_int(update.getValue("TIMESTAMP"))
        self._service.publish_price_update(
            StreamPriceUpdate(
                instrument=instrument,
                price=price,
                bid=bid,
                ask=ask,
                timestamp=timestamp,
            )
        )


class IGStreamingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._queue: asyncio.Queue[StreamPriceUpdate] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broker = get_broker()
        self._client: Any | None = None
        self._client_listener: Any | None = None
        self._subscription: Any | None = None
        self._subscription_listener: Any | None = None
        self._credentials: IGStreamingCredentials | None = None
        self._subscribed_instruments: tuple[str, ...] = ()
        self._latest_prices: dict[str, float] = {}
        self._missing_dependency_logged = False
        self._health = StreamHealthState()

    def is_enabled(self) -> bool:
        if not self.settings.ig_streaming_enabled:
            self._health.enabled = False
            return False
        if not isinstance(self._broker, IGBroker):
            self._health.enabled = False
            self._health.last_error = "Active broker is not an IG broker."
            logger.warning("IG streaming requested, but active broker is not an IG broker.")
            return False
        if LightstreamerClient is None or Subscription is None:
            self._health.enabled = False
            self._health.dependency_ready = False
            self._health.last_error = "lightstreamer-client-lib is not installed."
            if not self._missing_dependency_logged:
                logger.warning("IG streaming disabled because lightstreamer-client-lib is not installed.")
                self._missing_dependency_logged = True
            return False
        self._health.enabled = True
        self._health.dependency_ready = True
        self._health.last_error = None
        return True

    def get_health(self) -> StreamHealthState:
        return StreamHealthState(
            enabled=self._health.enabled,
            connected=self._health.connected,
            subscribed_instruments=self._health.subscribed_instruments,
            last_tick_at=self._health.last_tick_at,
            last_status=self._health.last_status,
            last_error=self._health.last_error,
            dependency_ready=self._health.dependency_ready,
        )

    def get_last_price(self, instrument: str) -> float | None:
        return self._latest_prices.get(instrument)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        logger.info(
            "IG streaming service started",
            extra={"watch_interval": self.settings.ig_streaming_watch_interval_seconds},
        )
        try:
            while True:
                try:
                    await self._reconcile_subscription()
                    await self._drain_price_queue(timeout=self.settings.ig_streaming_watch_interval_seconds)
                except asyncio.CancelledError:
                    raise
                except IGBrokerError as exc:
                    self._health.last_error = str(exc)
                    logger.warning("IG streaming loop encountered a broker error", extra={"error": str(exc)})
                    await asyncio.sleep(self.settings.ig_streaming_watch_interval_seconds)
                except Exception as exc:  # pragma: no cover - defensive runtime protection
                    self._health.last_error = str(exc)
                    logger.exception("IG streaming loop failed unexpectedly", extra={"error": str(exc)})
                    await asyncio.sleep(self.settings.ig_streaming_watch_interval_seconds)
        finally:
            self._teardown_client()

    def publish_price_update(self, update: StreamPriceUpdate) -> None:
        if self._loop is None:
            return
        self._latest_prices[update.instrument] = update.price
        self._health.last_tick_at = datetime.now(UTC)
        self._health.last_error = None
        self._loop.call_soon_threadsafe(self._queue.put_nowait, update)

    async def _reconcile_subscription(self) -> None:
        active_instruments = tuple(sorted(runtime_manager.engines.keys()))
        if not active_instruments:
            if self._subscription is not None:
                logger.info("No active instruments remain; closing IG price subscription.")
            self._unsubscribe_price_stream()
            return

        credentials = await asyncio.to_thread(self._broker.get_streaming_credentials)
        if credentials != self._credentials or self._client is None:
            self._reset_client(credentials)

        if active_instruments != self._subscribed_instruments:
            self._resubscribe(active_instruments)

    async def _drain_price_queue(self, *, timeout: float) -> None:
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return

        updates = [first]
        while True:
            try:
                updates.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        latest_by_instrument = {update.instrument: update for update in updates}
        with Session(engine) as session:
            strategy_service = StrategyService(session)
            for update in latest_by_instrument.values():
                logger.info(
                    "IG streaming tick received",
                    extra={
                        "instrument": update.instrument,
                        "price": update.price,
                        "bid": update.bid,
                        "ask": update.ask,
                        "timestamp": update.timestamp,
                    },
                )
                strategy_service.process_price_update(update.instrument, update.price)

    def _reset_client(self, credentials: IGStreamingCredentials) -> None:
        self._teardown_client()
        self._credentials = credentials
        self._client = LightstreamerClient(credentials.lightstreamer_endpoint, None)
        self._client.connectionDetails.setUser(credentials.account_id)
        self._client.connectionDetails.setPassword(f"CST-{credentials.cst}|XST-{credentials.security_token}")
        self._client_listener = _StreamClientListener(self)
        self._client.addListener(self._client_listener)
        self._client.connect()
        logger.info(
            "IG Lightstreamer client connected",
            extra={"account_id": credentials.account_id, "endpoint": credentials.lightstreamer_endpoint},
        )

    def _resubscribe(self, instruments: tuple[str, ...]) -> None:
        self._unsubscribe_price_stream()
        items = [f"PRICE:{self._credentials.account_id}:{instrument}" for instrument in instruments]
        subscription = Subscription("MERGE", items, PRICE_FIELDS)
        subscription.setDataAdapter("Pricing")
        subscription.setRequestedSnapshot("yes")
        listener = _PriceSubscriptionListener(self)
        subscription.addListener(listener)
        self._client.subscribe(subscription)
        self._subscription = subscription
        self._subscription_listener = listener
        self._subscribed_instruments = instruments
        self._health.subscribed_instruments = instruments
        logger.info("IG Lightstreamer price subscription requested", extra={"instruments": list(instruments)})

    def _unsubscribe_price_stream(self) -> None:
        if self._client is not None and self._subscription is not None:
            try:
                self._client.unsubscribe(self._subscription)
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                logger.warning("Failed to unsubscribe IG price stream cleanly", extra={"error": str(exc)})
        self._subscription = None
        self._subscription_listener = None
        self._subscribed_instruments = ()
        self._health.subscribed_instruments = ()

    def _teardown_client(self) -> None:
        self._unsubscribe_price_stream()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                logger.warning("Failed to disconnect IG Lightstreamer client cleanly", extra={"error": str(exc)})
        self._client = None
        self._client_listener = None
        self._credentials = None
        self._health.connected = False


_streaming_service: IGStreamingService | None = None


def get_ig_streaming_service() -> IGStreamingService:
    global _streaming_service
    if _streaming_service is None:
        _streaming_service = IGStreamingService()
    return _streaming_service

    @staticmethod
    def _coerce_float(raw_value: str | None) -> float | None:
        if raw_value in (None, ""):
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(raw_value: str | None) -> int | None:
        if raw_value in (None, ""):
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _select_price(*, bid: float | None, ask: float | None) -> float | None:
        if bid is not None and ask is not None:
            return round((bid + ask) / 2, 5)
        if bid is not None:
            return bid
        if ask is not None:
            return ask
        return None
