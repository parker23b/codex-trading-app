from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.broker import (
    BrokerOrderResult,
    BrokerOrderStatus,
    OrderDirection,
    OrderRequest,
)
from tests.fakes import FakeBroker


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


@pytest.mark.parametrize(
    "status",
    [
        BrokerOrderStatus.ACKNOWLEDGED,
        BrokerOrderStatus.PENDING,
        BrokerOrderStatus.TIMED_OUT,
        BrokerOrderStatus.RATE_LIMITED,
        BrokerOrderStatus.UNKNOWN,
        BrokerOrderStatus.AMBIGUOUS,
    ],
)
def test_audit_broker_002_fake_order_non_final_results_keep_request_correlation(
    status,
):
    broker = FakeBroker()
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference=f"entry-{status.value.lower()}",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=now,
            status=status,
            reason="Queued live-like non-final outcome.",
            requires_manual_review=True,
        )
    )

    result = broker.place_order(
        OrderRequest(
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            strategy_name="smoke_test_hold",
            client_request_id="entry-client-request-1",
        )
    )

    assert result.status is status
    assert result.client_request_id == "entry-client-request-1"
    assert result.requested_size == pytest.approx(0.2)
    assert result.requires_manual_review is True


@pytest.mark.parametrize(
    "status",
    [
        BrokerOrderStatus.PARTIALLY_FILLED,
        BrokerOrderStatus.TIMED_OUT,
        BrokerOrderStatus.AMBIGUOUS,
        BrokerOrderStatus.REJECTED,
    ],
)
def test_audit_broker_002_fake_close_incomplete_results_keep_request_correlation(
    status,
):
    broker = FakeBroker()
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    broker.close_position_outcomes.append(
        BrokerOrderResult(
            broker_reference=f"close-{status.value.lower()}",
            instrument=INSTRUMENT,
            direction=OrderDirection.SELL,
            size=0.2,
            price=101.0,
            executed_at=now,
            status=status,
            filled_size=0.1 if status is BrokerOrderStatus.PARTIALLY_FILLED else None,
            average_fill_price=101.0
            if status is BrokerOrderStatus.PARTIALLY_FILLED
            else None,
            reason="Queued live-like incomplete close outcome.",
            requires_manual_review=status
            in {
                BrokerOrderStatus.PARTIALLY_FILLED,
                BrokerOrderStatus.TIMED_OUT,
                BrokerOrderStatus.AMBIGUOUS,
            },
        )
    )

    result = broker.close_position(
        INSTRUMENT,
        broker_reference="open-position-1",
        client_request_id="close-client-request-1",
    )

    assert result.status is status
    assert result.client_request_id == "close-client-request-1"
    assert result.requested_size == pytest.approx(0.2)
    assert broker.close_requests == [
        {
            "instrument": INSTRUMENT,
            "broker_reference": "open-position-1",
            "client_request_id": "close-client-request-1",
        }
    ]
