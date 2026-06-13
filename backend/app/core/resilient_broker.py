from __future__ import annotations

from dataclasses import asdict, dataclass
import random
import time
from typing import Any, Callable, TypeVar

from app.core.broker import (
    AccountType,
    Broker,
    BrokerAccountSummary,
    BrokerCapabilities,
    BrokerCircuitOpenError,
    BrokerError,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerPosition,
    BrokerRiskSizingQuote,
    BrokerSizeNormalization,
    OrderRequest,
)


T = TypeVar("T")
_latest_resilience_snapshot: dict[str, Any] = {}


def get_broker_resilience_snapshot() -> dict[str, Any]:
    return {
        **_latest_resilience_snapshot,
        "circuits": dict(_latest_resilience_snapshot.get("circuits", {})),
    }


@dataclass(slots=True)
class BrokerCircuitState:
    consecutive_failures: int = 0
    opened_until: float | None = None
    last_failure_at: float | None = None
    last_success_at: float | None = None


class ResilientBroker(Broker):
    """Operation-aware resilience wrapper for broker-neutral adapters."""

    def __init__(
        self,
        delegate: Broker,
        *,
        read_max_attempts: int = 3,
        read_backoff_base_seconds: float = 0.1,
        read_backoff_max_seconds: float = 1.0,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.delegate = delegate
        self.read_max_attempts = read_max_attempts
        self.read_backoff_base_seconds = read_backoff_base_seconds
        self.read_backoff_max_seconds = read_backoff_max_seconds
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_cooldown_seconds = circuit_cooldown_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._jitter = jitter
        self._circuits: dict[str, BrokerCircuitState] = {}

    @property
    def account_type(self) -> AccountType:
        return self.delegate.account_type

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self.delegate.capabilities

    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        return self.delegate.place_order(order)

    def close_position(
        self,
        instrument: str,
        *,
        broker_reference: str | None = None,
        client_request_id: str | None = None,
    ) -> BrokerOrderResult:
        return self.delegate.close_position(
            instrument,
            broker_reference=broker_reference,
            client_request_id=client_request_id,
        )

    def get_positions(self) -> list[BrokerPosition]:
        return self._execute_read("positions", self.delegate.get_positions)

    def get_latest_price(self, instrument: str) -> float:
        return self._execute_read(
            "market_data", lambda: self.delegate.get_latest_price(instrument)
        )

    def get_account_summary(self) -> BrokerAccountSummary:
        return self._execute_read("account", self.delegate.get_account_summary)

    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        return self._execute_read(
            "market_data", lambda: self.delegate.get_market_details(instrument)
        )

    def get_market_details_many(
        self, instruments: list[str]
    ) -> dict[str, BrokerMarketDetails]:
        return self._execute_read(
            "market_data",
            lambda: self.delegate.get_market_details_many(instruments),
        )

    def quote_risk_sized_order(
        self,
        instrument: str,
        *,
        entry_price: float,
        risk_amount: float,
        stop_loss_price: float | None = None,
        fallback_stop_distance: float | None = None,
    ) -> BrokerRiskSizingQuote:
        return self._execute_read(
            "sizing",
            lambda: self.delegate.quote_risk_sized_order(
                instrument,
                entry_price=entry_price,
                risk_amount=risk_amount,
                stop_loss_price=stop_loss_price,
                fallback_stop_distance=fallback_stop_distance,
            ),
        )

    def normalize_order_size(
        self, instrument: str, requested_size: float
    ) -> BrokerSizeNormalization:
        return self._execute_read(
            "sizing",
            lambda: self.delegate.normalize_order_size(instrument, requested_size),
        )

    def get_resilience_snapshot(self) -> dict[str, Any]:
        global _latest_resilience_snapshot
        now = self._monotonic()
        snapshot = {
            "read_max_attempts": self.read_max_attempts,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_cooldown_seconds": self.circuit_cooldown_seconds,
            "circuits": {
                operation: {
                    **asdict(state),
                    "open": (
                        state.opened_until is not None and now < state.opened_until
                    ),
                }
                for operation, state in sorted(self._circuits.items())
            },
        }
        _latest_resilience_snapshot = snapshot
        return snapshot

    def _execute_read(self, operation: str, call: Callable[[], T]) -> T:
        state = self._circuits.setdefault(operation, BrokerCircuitState())
        now = self._monotonic()
        if state.opened_until is not None:
            if now < state.opened_until:
                raise BrokerCircuitOpenError(f"Broker {operation} circuit is open.")
            state.opened_until = None
            state.consecutive_failures = 0

        for attempt in range(1, self.read_max_attempts + 1):
            try:
                result = call()
            except (BrokerError, TimeoutError, ConnectionError, OSError):
                failure_time = self._monotonic()
                state.consecutive_failures += 1
                state.last_failure_at = failure_time
                if state.consecutive_failures >= self.circuit_failure_threshold:
                    state.opened_until = failure_time + self.circuit_cooldown_seconds
                self.get_resilience_snapshot()
                if attempt >= self.read_max_attempts:
                    raise
                delay_cap = min(
                    self.read_backoff_max_seconds,
                    self.read_backoff_base_seconds * (2 ** (attempt - 1)),
                )
                self._sleep(self._jitter(0.0, delay_cap))
                continue
            state.consecutive_failures = 0
            state.opened_until = None
            state.last_success_at = self._monotonic()
            self.get_resilience_snapshot()
            return result
        raise AssertionError("Broker read retry loop exited unexpectedly.")


def unwrap_broker(broker: Broker) -> Broker:
    if isinstance(broker, ResilientBroker):
        return broker.delegate
    return broker
