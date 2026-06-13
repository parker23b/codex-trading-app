from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.broker import (
    BrokerCircuitOpenError,
    BrokerError,
    BrokerOrderResult,
    OrderDirection,
    OrderRequest,
)
from app.core.resilient_broker import ResilientBroker
from tests.fakes import FakeBroker


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def _wrapper(broker: FakeBroker, *, attempts: int = 3, threshold: int = 3):
    sleeps: list[float] = []
    clock = {"now": 10.0}
    wrapper = ResilientBroker(
        broker,
        read_max_attempts=attempts,
        read_backoff_base_seconds=0.1,
        read_backoff_max_seconds=1.0,
        circuit_failure_threshold=threshold,
        circuit_cooldown_seconds=30.0,
        monotonic=lambda: clock["now"],
        sleep=sleeps.append,
        jitter=lambda _low, high: high,
    )
    return wrapper, sleeps, clock


def test_audit_broker_006_retry_safe_read_uses_bounded_exponential_backoff():
    broker = FakeBroker()
    broker.account_summary_outcomes.extend(
        [BrokerError("temporary"), BrokerError("temporary")]
    )
    wrapper, sleeps, _ = _wrapper(broker)

    summary = wrapper.get_account_summary()

    assert summary.account_id == "fake-account"
    assert sleeps == [0.1, 0.2]
    assert (
        wrapper.get_resilience_snapshot()["circuits"]["account"]["consecutive_failures"]
        == 0
    )


def test_audit_broker_006_read_circuit_opens_and_blocks_without_adapter_call():
    broker = FakeBroker(require_explicit_positions=True)
    broker.position_outcomes.extend(
        [BrokerError("down"), BrokerError("down"), BrokerError("down")]
    )
    wrapper, _, _ = _wrapper(broker, attempts=3, threshold=3)

    with pytest.raises(BrokerError, match="down"):
        wrapper.get_positions()
    assert broker.position_outcomes == []

    with pytest.raises(BrokerCircuitOpenError, match="positions circuit"):
        wrapper.get_positions()


def test_audit_broker_006_mutations_are_never_retried():
    broker = FakeBroker()
    broker.place_order_outcomes.append(BrokerError("ambiguous transport loss"))
    wrapper, sleeps, _ = _wrapper(broker)
    order = OrderRequest(
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        size=0.2,
        price=100.0,
        strategy_name="smoke_test_hold",
        client_request_id="entry-once-1",
    )

    with pytest.raises(BrokerError, match="ambiguous transport loss"):
        wrapper.place_order(order)

    assert len(broker.placed_orders) == 1
    assert sleeps == []


def test_audit_broker_006_capability_contract_is_preserved():
    broker = FakeBroker()
    wrapper, _, _ = _wrapper(broker)
    broker.close_position_outcomes.append(
        BrokerOrderResult(
            broker_reference="close-1",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=101.0,
            executed_at=datetime(2026, 6, 13, 8, 0, tzinfo=UTC),
        )
    )

    result = wrapper.close_position(
        INSTRUMENT,
        broker_reference="open-1",
        client_request_id="close-once-1",
    )

    assert result.client_request_id == "close-once-1"
    assert wrapper.capabilities == broker.capabilities
