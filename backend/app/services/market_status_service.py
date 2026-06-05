from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, perf_counter

from pydantic import BaseModel

from app.core.broker import Broker, BrokerMarketDetails
from app.core.broker_factory import get_broker
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.services.health_service import get_health_service

logger = get_logger(__name__)

OPEN_MARKET_STATES = {"TRADEABLE", "TRADEABLE_ONLINE"}
BLOCKED_MARKET_STATES = {
    "CLOSED",
    "DEALING_RESTRICTED",
    "EDITS_ONLY",
    "OFFLINE",
    "ON_AUCTION",
    "ON_AUCTION_NO_EDITS",
    "SUSPENDED",
    "TRADEABLE_NO_EDIT",
}
BLOCKED_ORDER_PREFERENCES = {"NOT_AVAILABLE", "LIMIT_ONLY", "STOP_ONLY"}


class MarketStatus(BaseModel):
    instrument: str
    is_ok: bool
    market_open: bool
    tradable: bool
    quote_fresh: bool
    spread_ok: bool
    session_valid: bool
    dealing_allowed: bool
    last_price_age_ms: float
    spread: float | None
    reason: str | None


@dataclass(slots=True)
class _CacheEntry:
    status: MarketStatus
    created_at: float


class MarketStatusService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[str, _CacheEntry] = {}

    def reset(self) -> None:
        self._cache.clear()

    def get_status(
        self,
        instrument: str,
        *,
        broker: Broker | None = None,
        now: datetime | None = None,
        force_refresh: bool = False,
    ) -> MarketStatus:
        cached = self._cache.get(instrument)
        now_monotonic = monotonic()
        ttl_seconds = self.settings.market_status_cache_ttl_ms / 1000
        if (
            not force_refresh
            and cached is not None
            and now_monotonic - cached.created_at <= ttl_seconds
        ):
            return cached.status

        active_broker = broker or get_broker()
        health_service = get_health_service()
        market_details: BrokerMarketDetails | None = None
        started_at = perf_counter()
        try:
            market_details = active_broker.get_market_details(instrument)
        except Exception:
            latency_ms = (perf_counter() - started_at) * 1000
            health_service.update_broker_state(connected=False, latency_ms=latency_ms)
            raise
        else:
            latency_ms = (perf_counter() - started_at) * 1000
            health_service.update_broker_state(connected=True, latency_ms=latency_ms)

        current_time = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        quote_timestamp = self._resolve_quote_timestamp(
            stream_timestamp=get_market_status_streaming_service().get_last_tick_at(
                instrument
            ),
            runtime_timestamp=runtime_manager.get_last_price_updated_at(instrument),
            broker_timestamp=market_details.update_time,
        )
        last_price_age_ms = self._get_last_price_age_ms(
            last_price_updated_at=quote_timestamp, now=current_time
        )
        spread = self._get_spread(market_details)
        market_open = self._is_market_open(market_details.market_status)
        tradable = bool(market_details.tradable)
        quote_fresh = last_price_age_ms <= self.settings.max_price_age_ms
        spread_ok = spread is None or spread <= self.settings.max_spread_pips
        session_valid = self._is_session_valid(current_time)
        dealing_allowed = self._is_dealing_allowed(market_details)
        reason = self._resolve_reason(
            market_open=market_open,
            tradable=tradable,
            quote_fresh=quote_fresh,
            spread_ok=spread_ok,
            session_valid=session_valid,
            dealing_allowed=dealing_allowed,
            last_price_age_ms=last_price_age_ms,
            spread=spread,
            market_status=market_details.market_status,
        )
        status = MarketStatus(
            instrument=instrument,
            is_ok=reason is None,
            market_open=market_open,
            tradable=tradable,
            quote_fresh=quote_fresh,
            spread_ok=spread_ok,
            session_valid=session_valid,
            dealing_allowed=dealing_allowed,
            last_price_age_ms=round(last_price_age_ms, 2),
            spread=round(spread, 5) if spread is not None else None,
            reason=reason,
        )
        self._cache[instrument] = _CacheEntry(status=status, created_at=now_monotonic)
        return status

    @staticmethod
    def _get_last_price_age_ms(
        *, last_price_updated_at: datetime | None, now: datetime
    ) -> float:
        if last_price_updated_at is None:
            return float("inf")
        return (now - last_price_updated_at.astimezone(UTC)).total_seconds() * 1000

    @staticmethod
    def _resolve_quote_timestamp(
        *,
        stream_timestamp: datetime | None,
        runtime_timestamp: datetime | None,
        broker_timestamp: str | None,
    ) -> datetime | None:
        candidates: list[datetime] = []
        if broker_timestamp:
            normalized = broker_timestamp.replace("Z", "+00:00")
            try:
                candidates.append(datetime.fromisoformat(normalized).astimezone(UTC))
            except ValueError:
                pass
        if stream_timestamp is not None:
            candidates.append(stream_timestamp.astimezone(UTC))
        if runtime_timestamp is not None:
            candidates.append(runtime_timestamp.astimezone(UTC))
        if not candidates:
            return None
        return max(candidates)

    @staticmethod
    def _get_spread(details: BrokerMarketDetails) -> float | None:
        if details.bid is None or details.offer is None:
            return None
        return details.offer - details.bid

    @staticmethod
    def _is_market_open(market_status: str | None) -> bool:
        if market_status is None:
            return False
        normalized = market_status.strip().upper()
        if not normalized:
            return False
        if normalized in BLOCKED_MARKET_STATES:
            return False
        return normalized in OPEN_MARKET_STATES

    @staticmethod
    def _is_session_valid(now: datetime) -> bool:
        return now.weekday() < 5

    @staticmethod
    def _is_dealing_allowed(details: BrokerMarketDetails) -> bool:
        preference = (details.market_order_preference or "").upper()
        return preference not in BLOCKED_ORDER_PREFERENCES and details.tradable

    @staticmethod
    def _resolve_reason(
        *,
        market_open: bool,
        tradable: bool,
        quote_fresh: bool,
        spread_ok: bool,
        session_valid: bool,
        dealing_allowed: bool,
        last_price_age_ms: float,
        spread: float | None,
        market_status: str | None,
    ) -> str | None:
        if not market_open:
            return f"Market is closed for current status {market_status or 'UNKNOWN'}."
        if not tradable:
            return "Instrument is not currently tradable."
        if not quote_fresh:
            if last_price_age_ms == float("inf"):
                return "No price has been received for this instrument."
            return f"Latest quote is stale at {round(last_price_age_ms, 2)}ms old."
        if not spread_ok:
            return f"Spread {round(spread or 0.0, 5)} exceeds max allowed {get_settings().max_spread_pips}."
        if not session_valid:
            return "Current session is outside the allowed dealing window."
        if not dealing_allowed:
            return "Broker reports dealing restrictions for this instrument."
        return None


_market_status_service: MarketStatusService | None = None


def get_market_status_service() -> MarketStatusService:
    global _market_status_service
    if _market_status_service is None:
        _market_status_service = MarketStatusService()
    return _market_status_service


def get_market_status_streaming_service():
    from app.services.ig_streaming_service import get_ig_streaming_service

    return get_ig_streaming_service()
