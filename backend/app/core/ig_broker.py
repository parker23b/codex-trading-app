from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.broker import (
    AccountType,
    Broker,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPosition,
    OrderDirection,
    OrderRequest,
    now_utc,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class IGSession:
    cst: str
    security_token: str
    current_account_id: str | None
    lightstreamer_endpoint: str | None


@dataclass(slots=True)
class CachedMarketDetails:
    details: BrokerMarketDetails
    fetched_at: float


@dataclass(frozen=True, slots=True)
class IGStreamingCredentials:
    account_id: str
    cst: str
    security_token: str
    lightstreamer_endpoint: str


class IGBrokerError(RuntimeError):
    pass


class IGBroker(Broker):
    """
    IG broker adapter with real demo/live authentication.

    Authentication uses IG's `/session` flow and keeps session tokens inside
    the adapter so the rest of the backend can keep talking to the normalized
    Broker interface only.
    """

    def __init__(
        self,
        account_type: AccountType,
        *,
        api_key: str | None,
        username: str | None,
        password: str | None,
        account_id: str | None,
        base_url: str | None,
        request_timeout_seconds: float = 10.0,
        trading_enabled: bool = False,
        verify_ssl: bool = True,
        ca_bundle_path: str | None = None,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._username = username
        self._password = password
        self._account_id = account_id
        self._base_url = (base_url or self._default_base_url(account_type)).rstrip("/")
        self._request_timeout_seconds = request_timeout_seconds
        self._trading_enabled = trading_enabled
        self._verify_ssl = verify_ssl
        self._ca_bundle_path = ca_bundle_path
        self._market_cache_ttl_seconds = get_settings().ig_market_cache_ttl_seconds
        self._market_cache_stale_ttl_seconds = get_settings().ig_market_cache_stale_ttl_seconds
        self._positions: dict[str, BrokerPosition] = {}
        self._last_prices: dict[str, float] = {}
        self._market_details_cache: dict[str, CachedMarketDetails] = {}
        self._account_currency: str | None = None
        self._session: IGSession | None = None

    @property
    def account_type(self) -> AccountType:
        return self._account_type

    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        submitted_at = now_utc()
        if not self._trading_enabled:
            logger.info(
                "IG trading disabled; using local simulated fill",
                extra={"instrument": order.instrument, "direction": order.direction.value},
            )
            return self._simulate_place_order(order, submitted_at=submitted_at)

        self._ensure_authenticated()
        payload = {
            "currencyCode": self._get_account_currency(),
            "direction": order.direction.value,
            "epic": order.instrument,
            "expiry": "-",
            "forceOpen": True,
            "guaranteedStop": False,
            "orderType": "MARKET",
            "size": order.size,
            "timeInForce": "FILL_OR_KILL",
        }
        response = self._request("POST", "/positions/otc", version="2", body=payload)
        deal_reference = response.get("dealReference")
        if not deal_reference:
            raise IGBrokerError("IG order placement did not return a dealReference.")

        confirmation = self._wait_for_deal_confirmation(deal_reference)
        deal_id = confirmation.get("dealId")
        executed_price = float(confirmation.get("level") or order.price)
        executed_at = self._parse_ig_timestamp(confirmation.get("date")) or now_utc()
        position = BrokerPosition(
            broker_reference=deal_id or deal_reference,
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            open_price=executed_price,
            opened_at=executed_at,
        )
        self._positions[position.broker_reference] = position
        logger.info(
            "IG order opened",
            extra={
                "instrument": order.instrument,
                "deal_id": deal_id,
                "broker_reference": position.broker_reference,
                "direction": order.direction.value,
            },
        )
        return BrokerOrderResult(
            broker_reference=position.broker_reference,
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            price=executed_price,
            executed_at=executed_at,
            status=BrokerOrderStatus.FILLED,
            requested_size=order.size,
            filled_size=order.size,
            average_fill_price=executed_price,
            submitted_at=submitted_at,
            acknowledged_at=executed_at,
        )

    def close_position(self, instrument: str, *, broker_reference: str | None = None) -> BrokerOrderResult:
        submitted_at = now_utc()
        if not self._trading_enabled:
            logger.info(
                "IG trading disabled; using local simulated close",
                extra={"instrument": instrument, "broker_reference": broker_reference},
            )
            return self._simulate_close_position(
                instrument,
                broker_reference=broker_reference,
                submitted_at=submitted_at,
            )

        self._ensure_authenticated()
        open_position = self._positions.get(broker_reference) if broker_reference is not None else None
        if open_position is None:
            remote_positions = self.get_positions()
            if broker_reference is not None:
                open_position = next(
                    (position for position in remote_positions if position.broker_reference == broker_reference),
                    None,
                )
            if open_position is None:
                open_position = next((position for position in remote_positions if position.instrument == instrument), None)
        if open_position is None:
            raise IGBrokerError(
                f"No broker position found for instrument '{instrument}'"
                + (f" and broker reference '{broker_reference}'." if broker_reference else ".")
            )

        deal_id = open_position.broker_reference
        opposite_direction = OrderDirection.SELL if open_position.direction is OrderDirection.BUY else OrderDirection.BUY
        payload = {
            "direction": opposite_direction.value,
            "epic": open_position.instrument,
            "expiry": "-",
            "orderType": "MARKET",
            "size": open_position.size,
            "timeInForce": "FILL_OR_KILL",
        }
        if deal_id:
            payload["dealId"] = deal_id
        response = self._request("DELETE", "/positions/otc", version="1", body=payload)
        deal_reference = response.get("dealReference")
        if not deal_reference:
            raise IGBrokerError("IG close-position request did not return a dealReference.")

        confirmation = self._wait_for_deal_confirmation(deal_reference)
        executed_price = float(confirmation.get("level") or open_position.open_price)
        executed_at = self._parse_ig_timestamp(confirmation.get("date")) or now_utc()
        closed_deal_id = confirmation.get("dealId") or deal_reference
        self._positions.pop(open_position.broker_reference, None)
        logger.info(
            "IG position closed",
            extra={
                "instrument": open_position.instrument,
                "deal_id": closed_deal_id,
                "broker_reference": open_position.broker_reference,
            },
        )
        return BrokerOrderResult(
            broker_reference=closed_deal_id,
            instrument=open_position.instrument,
            direction=opposite_direction,
            size=open_position.size,
            price=executed_price,
            executed_at=executed_at,
            status=BrokerOrderStatus.FILLED,
            requested_size=open_position.size,
            filled_size=open_position.size,
            average_fill_price=executed_price,
            submitted_at=submitted_at,
            acknowledged_at=executed_at,
        )

    def get_positions(self) -> list[BrokerPosition]:
        self._ensure_authenticated()
        payload = self._request("GET", "/positions", version="2")
        positions: list[BrokerPosition] = []
        for item in payload.get("positions", []):
            position_data = item.get("position", {})
            market_data = item.get("market", {})
            direction_value = position_data.get("direction")
            if direction_value not in {"BUY", "SELL"}:
                continue
            instrument = market_data.get("epic") or position_data.get("epic") or position_data.get("dealId")
            if not instrument:
                continue
            opened_at = self._parse_ig_timestamp(position_data.get("createdDateUTC")) or now_utc()
            deal_id = position_data.get("dealId") or position_data.get("dealReference")
            if not deal_id:
                deal_id = f"ig-{instrument}-{len(positions) + 1}"
            positions.append(
                BrokerPosition(
                    broker_reference=deal_id,
                    instrument=instrument,
                    direction=OrderDirection(direction_value),
                    size=float(position_data.get("size", 0.0)),
                    open_price=float(position_data.get("level", 0.0)),
                    opened_at=opened_at,
                )
            )
        self._positions = {position.broker_reference: position for position in positions}
        return positions

    def get_latest_price(self, instrument: str) -> float:
        details = self._load_market_details(instrument, use_cache=False)
        price: float | None = None
        if details.bid is not None and details.offer is not None:
            price = round((details.bid + details.offer) / 2, 5)
        elif details.bid is not None:
            price = details.bid
        elif details.offer is not None:
            price = details.offer
        elif details.high is not None and details.low is not None:
            price = round((details.high + details.low) / 2, 5)
        elif instrument in self._last_prices:
            price = self._last_prices[instrument]
        else:
            matching_position = next((position for position in self._positions.values() if position.instrument == instrument), None)
            if matching_position is not None:
                price = matching_position.open_price

        if price is None:
            raise IGBrokerError(f"IG market snapshot for '{instrument}' did not include a usable price.")

        self._last_prices[instrument] = price
        return price

    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        return self._load_market_details(instrument, use_cache=True)

    def get_streaming_credentials(self) -> IGStreamingCredentials:
        self._ensure_authenticated()
        if self._session is None:
            raise IGBrokerError("IG session was not established for streaming.")
        if not self._session.current_account_id:
            raise IGBrokerError("IG session did not expose an active account id for streaming.")
        if not self._session.lightstreamer_endpoint:
            raise IGBrokerError("IG session did not expose a Lightstreamer endpoint.")
        return IGStreamingCredentials(
            account_id=self._session.current_account_id,
            cst=self._session.cst,
            security_token=self._session.security_token,
            lightstreamer_endpoint=self._session.lightstreamer_endpoint,
        )

    def _load_market_details(self, instrument: str, *, use_cache: bool) -> BrokerMarketDetails:
        cached = self._market_details_cache.get(instrument)
        if use_cache and cached is not None and self._is_cache_fresh(cached):
            return cached.details

        self._ensure_authenticated()
        try:
            payload = self._request("GET", f"/markets/{instrument}", version="4")
        except IGBrokerError as exc:
            if cached is not None and self._is_cache_still_usable(cached) and self._should_fallback_to_stale_market_details(exc):
                logger.warning(
                    "Using stale IG market cache after upstream error",
                    extra={"instrument": instrument, "error": str(exc)},
                )
                return cached.details
            raise
        instrument_data = payload.get("instrument", {})
        snapshot = payload.get("snapshot", {})
        dealing_rules = payload.get("dealingRules", {})
        bid = self._coerce_float(snapshot.get("bid"))
        offer = self._coerce_float(snapshot.get("offer"))
        high = self._coerce_float(snapshot.get("high"))
        low = self._coerce_float(snapshot.get("low"))
        market_status = snapshot.get("marketStatus")
        market_order_preference = str(dealing_rules.get("marketOrderPreference") or "").upper()
        tradable = market_status in {"TRADEABLE", "TRADEABLE_ONLINE"} and market_order_preference != "NOT_AVAILABLE"

        details = BrokerMarketDetails(
            instrument=instrument,
            name=instrument_data.get("name") or instrument,
            bid=bid,
            offer=offer,
            high=high,
            low=low,
            percentage_change=self._coerce_float(snapshot.get("percentageChange")),
            net_change=self._coerce_float(snapshot.get("netChange")),
            market_status=market_status,
            update_time=snapshot.get("updateTime"),
            tradable=tradable,
        )
        self._market_details_cache[instrument] = CachedMarketDetails(details=details, fetched_at=time.monotonic())
        return details

    def get_account_summary(self) -> BrokerAccountSummary:
        self._ensure_authenticated()
        payload = self._request("GET", "/accounts", version="1")
        accounts = payload.get("accounts", [])
        selected_account = None
        for account in accounts:
            account_id = account.get("accountId")
            if self._account_id and account_id == self._account_id:
                selected_account = account
                break
            if not self._account_id and account_id == self._session.current_account_id:
                selected_account = account
                break
        if selected_account is None and accounts:
            selected_account = accounts[0]
        if selected_account is None:
            raise IGBrokerError("IG accounts response did not include any accounts.")

        balance_info = selected_account.get("balance", {})
        balance = self._coerce_float(balance_info.get("balance")) or self._coerce_float(selected_account.get("balance")) or 0.0
        available = (
            self._coerce_float(balance_info.get("available"))
            or self._coerce_float(balance_info.get("availableToDeal"))
            or self._coerce_float(selected_account.get("available"))
            or balance
        )
        profit_loss = (
            self._coerce_float(balance_info.get("profitLoss"))
            or self._coerce_float(balance_info.get("pl"))
            or self._coerce_float(selected_account.get("profitLoss"))
            or 0.0
        )
        equity = self._coerce_float(balance_info.get("equity")) or (balance + profit_loss)

        return BrokerAccountSummary(
            account_id=selected_account.get("accountId") or self._session.current_account_id or "UNKNOWN",
            balance=balance,
            available=available,
            profit_loss=profit_loss,
            equity=equity,
            account_type=self._account_type,
        )

    def _simulate_place_order(self, order: OrderRequest, *, submitted_at: datetime | None = None) -> BrokerOrderResult:
        logger.info(
            "Stub order placed via IG broker",
            extra={"instrument": order.instrument, "direction": order.direction.value},
        )
        executed_at = now_utc()
        broker_reference = f"ig-{uuid4()}"
        self._positions[broker_reference] = BrokerPosition(
            broker_reference=broker_reference,
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            open_price=order.price,
            opened_at=executed_at,
        )
        return BrokerOrderResult(
            broker_reference=broker_reference,
            instrument=order.instrument,
            direction=order.direction,
            size=order.size,
            price=order.price,
            executed_at=executed_at,
            status=BrokerOrderStatus.FILLED,
            requested_size=order.size,
            filled_size=order.size,
            average_fill_price=order.price,
            submitted_at=submitted_at or executed_at,
            acknowledged_at=executed_at,
        )

    def _simulate_close_position(
        self,
        instrument: str,
        *,
        broker_reference: str | None = None,
        submitted_at: datetime | None = None,
    ) -> BrokerOrderResult:
        position: BrokerPosition | None = None
        if broker_reference is not None:
            position = self._positions.pop(broker_reference, None)
        if position is None:
            position_key = next(
                (key for key, value in self._positions.items() if value.instrument == instrument),
                None,
            )
            if position_key is not None:
                position = self._positions.pop(position_key)
        if position is None:
            raise ValueError(f"No open position for instrument '{instrument}'.")

        logger.info(
            "Stub position closed via IG broker",
            extra={"instrument": instrument, "broker_reference": position.broker_reference},
        )
        return BrokerOrderResult(
            broker_reference=f"ig-{uuid4()}",
            instrument=position.instrument,
            direction=position.direction,
            size=position.size,
            price=position.open_price,
            executed_at=now_utc(),
            status=BrokerOrderStatus.FILLED,
            requested_size=position.size,
            filled_size=position.size,
            average_fill_price=position.open_price,
            submitted_at=submitted_at or now_utc(),
            acknowledged_at=now_utc(),
        )

    def _ensure_authenticated(self) -> None:
        if self._session is not None:
            return
        self._login()

    def _login(self) -> None:
        self._validate_auth_config()
        payload = {
            "identifier": self._username,
            "password": self._password,
            "encryptedPassword": False,
        }
        response_body, response_headers = self._raw_request(
            "POST",
            "/session",
            version="2",
            body=payload,
            headers={"X-IG-API-KEY": self._api_key or ""},
        )
        cst = response_headers.get("CST")
        security_token = response_headers.get("X-SECURITY-TOKEN")
        if not cst or not security_token:
            raise IGBrokerError("IG login succeeded but did not return CST and X-SECURITY-TOKEN headers.")

        current_account_id = response_body.get("currentAccountId") or response_body.get("accountId")
        self._session = IGSession(
            cst=cst,
            security_token=security_token,
            current_account_id=current_account_id,
            lightstreamer_endpoint=response_body.get("lightstreamerEndpoint"),
        )
        logger.info(
            "Authenticated with IG",
            extra={"account_id": current_account_id, "mode": self._account_type.value},
        )

        if self._account_id and self._account_id != current_account_id:
            self._switch_account(self._account_id)

    def _switch_account(self, account_id: str) -> None:
        self._request(
            "PUT",
            "/session",
            version="1",
            body={"accountId": account_id, "defaultAccount": False},
        )
        response_body, response_headers = self._raw_request(
            "GET",
            f"/session?{urlencode({'fetchSessionTokens': 'true'})}",
            version="1",
        )
        cst = response_headers.get("CST")
        security_token = response_headers.get("X-SECURITY-TOKEN")
        if not cst or not security_token:
            raise IGBrokerError("IG account switch succeeded but refreshed session tokens were not returned.")
        self._session = IGSession(
            cst=cst,
            security_token=security_token,
            current_account_id=response_body.get("accountId") or account_id,
            lightstreamer_endpoint=response_body.get("lightstreamerEndpoint"),
        )
        logger.info("Switched IG account", extra={"account_id": account_id})

    def _request(
        self,
        method: str,
        path: str,
        *,
        version: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response_body, _ = self._raw_request(method, path, version=version, body=body)
        return response_body

    def _wait_for_deal_confirmation(self, deal_reference: str) -> dict[str, Any]:
        last_response: dict[str, Any] | None = None
        for _ in range(10):
            try:
                response = self._request("GET", f"/confirms/{deal_reference}", version="1")
            except IGBrokerError as exc:
                if "status 404" in str(exc):
                    time.sleep(0.4)
                    continue
                raise
            last_response = response
            deal_status = response.get("dealStatus")
            if deal_status == "ACCEPTED":
                return response
            if deal_status == "REJECTED":
                reason = response.get("reason") or "Unknown rejection"
                raise IGBrokerError(f"IG rejected deal {deal_reference}: {reason}")
            time.sleep(0.4)
        raise IGBrokerError(f"Timed out waiting for IG confirmation for deal {deal_reference}: {last_response}")

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        version: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        request_headers = {
            "Accept": "application/json; charset=UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
            "VERSION": version,
            **(headers or {}),
        }
        if self._api_key:
            request_headers.setdefault("X-IG-API-KEY", self._api_key)
        if self._session is not None:
            request_headers.setdefault("CST", self._session.cst)
            request_headers.setdefault("X-SECURITY-TOKEN", self._session.security_token)

        raw_body = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url=f"{self._base_url}{path}",
            data=raw_body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(
                request,
                timeout=self._request_timeout_seconds,
                context=self._build_ssl_context(),
            ) as response:
                response_text = response.read().decode("utf-8")
                response_body = json.loads(response_text) if response_text else {}
                response_headers = {key: value for key, value in response.headers.items()}
                return response_body, response_headers
        except HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "IG request failed",
                extra={"status_code": exc.code, "path": path, "body": response_text[:500]},
            )
            raise IGBrokerError(f"IG request failed with status {exc.code}: {response_text}") from exc
        except URLError as exc:
            logger.error("IG network error", extra={"path": path, "reason": str(exc.reason)})
            raise IGBrokerError(f"Unable to reach IG API: {exc.reason}") from exc

    def _validate_auth_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("IG_API_KEY", self._api_key),
                ("IG_USERNAME", self._username),
                ("IG_PASSWORD", self._password),
            )
            if not value
        ]
        if missing:
            raise IGBrokerError(f"Missing required IG settings: {', '.join(missing)}")

    def _get_account_currency(self) -> str:
        if self._account_currency is not None:
            return self._account_currency

        payload = self._request("GET", "/accounts", version="1")
        for account in payload.get("accounts", []):
            account_id = account.get("accountId")
            if self._account_id and account_id != self._account_id:
                continue
            self._account_currency = (
                account.get("currency")
                or account.get("currencyIsoCode")
                or account.get("preferredCurrency")
                or "GBP"
            )
            return self._account_currency

        self._account_currency = "GBP"
        return self._account_currency

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_ssl_context(self) -> ssl.SSLContext:
        if not self._verify_ssl:
            logger.warning("IG SSL verification disabled", extra={"base_url": self._base_url})
            return ssl._create_unverified_context()
        if self._ca_bundle_path:
            return ssl.create_default_context(cafile=self._ca_bundle_path)
        return ssl.create_default_context()

    @staticmethod
    def _parse_ig_timestamp(raw_value: Any) -> datetime | None:
        if not raw_value or not isinstance(raw_value, str):
            return None
        normalized = raw_value.replace("/", "-")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _default_base_url(account_type: AccountType) -> str:
        if account_type is AccountType.DEMO:
            return "https://demo-api.ig.com/gateway/deal"
        return "https://api.ig.com/gateway/deal"

    def _is_cache_fresh(self, cached: CachedMarketDetails) -> bool:
        return (time.monotonic() - cached.fetched_at) <= self._market_cache_ttl_seconds

    def _is_cache_still_usable(self, cached: CachedMarketDetails) -> bool:
        return (time.monotonic() - cached.fetched_at) <= self._market_cache_stale_ttl_seconds

    @staticmethod
    def _should_fallback_to_stale_market_details(error: IGBrokerError) -> bool:
        message = str(error)
        return (
            "error.public-api.exceeded-api-key-allowance" in message
            or "Unable to reach IG API" in message
            or "status 5" in message
        )
