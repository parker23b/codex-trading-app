from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.broker import (
    AccountType,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerRiskSizingQuote,
    BrokerSizeNormalization,
    BrokerSizingMode,
    BrokerSizingPrecision,
    OrderDirection,
    OrderRequest,
)
from tests.fakes import FakeBroker


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def test_audit_broker_002_fake_account_summary_can_require_explicit_read_truth():
    broker = FakeBroker(require_explicit_account_summary=True)

    with pytest.raises(AssertionError, match="account summary"):
        broker.get_account_summary()

    broker.account_summary_outcomes.append(RuntimeError("account read unavailable"))
    with pytest.raises(RuntimeError, match="account read unavailable"):
        broker.get_account_summary()

    broker.account_summary_outcomes.append(
        BrokerAccountSummary(
            account_id="explicit-account",
            balance=500.0,
            available=0.0,
            profit_loss=-500.0,
            equity=0.0,
            account_type=AccountType.DEMO,
        )
    )

    summary = broker.get_account_summary()

    assert summary.account_id == "explicit-account"
    assert summary.available == pytest.approx(0.0)
    assert summary.equity == pytest.approx(0.0)


def test_audit_broker_002_fake_market_details_can_require_explicit_read_truth():
    broker = FakeBroker(require_explicit_market_details=True)

    with pytest.raises(AssertionError, match="market details"):
        broker.get_market_details(INSTRUMENT)

    broker.market_details_outcomes[INSTRUMENT] = [
        RuntimeError("market details unavailable"),
        BrokerMarketDetails(
            instrument=INSTRUMENT,
            name=INSTRUMENT,
            bid=100.0,
            offer=100.1,
            high=101.0,
            low=99.0,
            percentage_change=0.0,
            net_change=0.0,
            market_status="SUSPENDED",
            update_time=None,
            tradable=False,
        ),
    ]

    with pytest.raises(RuntimeError, match="market details unavailable"):
        broker.get_market_details(INSTRUMENT)

    details = broker.get_market_details(INSTRUMENT)

    assert details.market_status == "SUSPENDED"
    assert details.update_time is None
    assert details.tradable is False


def test_audit_broker_002_fake_sizing_quote_can_require_explicit_outcomes():
    broker = FakeBroker(require_explicit_risk_sizing_quote=True)

    with pytest.raises(AssertionError, match="sizing quote"):
        broker.quote_risk_sized_order(
            INSTRUMENT,
            entry_price=100.0,
            risk_amount=50.0,
            fallback_stop_distance=1.0,
        )

    broker.risk_sizing_quote_outcomes[INSTRUMENT] = [
        RuntimeError("sizing quote unavailable"),
        BrokerRiskSizingQuote(
            instrument=INSTRUMENT,
            precision=BrokerSizingPrecision.UNSUPPORTED,
            mode=BrokerSizingMode.UNSUPPORTED,
            sizing_available=False,
            reason_code="unsupported_sizing",
            reason="Broker cannot size this market.",
            entry_price=100.0,
            risk_amount=50.0,
        ),
    ]

    with pytest.raises(RuntimeError, match="sizing quote unavailable"):
        broker.quote_risk_sized_order(
            INSTRUMENT,
            entry_price=100.0,
            risk_amount=50.0,
            fallback_stop_distance=1.0,
        )

    quote = broker.quote_risk_sized_order(
        INSTRUMENT,
        entry_price=100.0,
        risk_amount=50.0,
        fallback_stop_distance=1.0,
    )

    assert quote.sizing_available is False
    assert quote.precision is BrokerSizingPrecision.UNSUPPORTED
    assert quote.reason_code == "unsupported_sizing"


def test_audit_broker_002_fake_sizing_understands_ig_point_value_metadata():
    broker = FakeBroker()
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name="EUR/USD",
        bid=1.2345,
        offer=1.2346,
        high=1.24,
        low=1.23,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime(2026, 5, 8, 12, 0, tzinfo=UTC).isoformat(),
        tradable=True,
        min_deal_size=0.1,
        min_normal_stop_or_limit_distance=0.0003,
        size_step=0.1,
        metadata={
            "provider": "IG",
            "ig_sizing": {
                "price_increment": 0.0001,
                "value_per_increment": 1.0,
                "instrument_type": "CURRENCIES",
                "size_unit": "AMOUNT",
            },
        },
    )

    quote = broker.quote_risk_sized_order(
        INSTRUMENT,
        entry_price=1.2346,
        risk_amount=10.0,
        stop_loss_price=1.2336,
    )

    assert quote.precision is BrokerSizingPrecision.EXACT
    assert quote.mode is BrokerSizingMode.EXACT_POINT_VALUE
    assert quote.sizing_available is True
    assert quote.stop_distance_price == pytest.approx(0.001)
    assert quote.risk_per_unit == pytest.approx(10.0)
    assert quote.requested_size == pytest.approx(1.0)
    assert quote.normalized_size == pytest.approx(1.0)


@pytest.mark.parametrize(
    (
        "sizing_profile",
        "expected_precision",
        "expected_mode",
        "expected_risk_per_unit",
        "expected_requested_size",
    ),
    [
        (
            {
                "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
                "price_increment": 0.5,
                "value_per_increment": 10.0,
            },
            BrokerSizingPrecision.EXACT,
            BrokerSizingMode.EXACT_POINT_VALUE,
            40.0,
            1.25,
        ),
        (
            {
                "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
                "contract_multiplier": 3.0,
            },
            BrokerSizingPrecision.EXACT,
            BrokerSizingMode.EXACT_CONTRACT_RISK,
            6.0,
            50.0 / 6.0,
        ),
        (
            {
                "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                "contract_multiplier": 2.0,
            },
            BrokerSizingPrecision.APPROXIMATE,
            BrokerSizingMode.APPROXIMATE_PRICE_DELTA,
            4.0,
            12.5,
        ),
    ],
)
def test_audit_broker_002_fake_derived_sizing_modes_are_contract_pinned(
    sizing_profile,
    expected_precision,
    expected_mode,
    expected_risk_per_unit,
    expected_requested_size,
):
    broker = FakeBroker()
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime(2026, 5, 8, 12, 0, tzinfo=UTC).isoformat(),
        tradable=True,
        metadata={"sizing_profile": sizing_profile},
    )

    quote = broker.quote_risk_sized_order(
        INSTRUMENT,
        entry_price=100.0,
        risk_amount=50.0,
        stop_loss_price=98.0,
    )

    assert quote.precision is expected_precision
    assert quote.mode is expected_mode
    assert quote.sizing_available is True
    assert quote.risk_per_unit == pytest.approx(expected_risk_per_unit)
    assert quote.requested_size == pytest.approx(expected_requested_size)
    assert quote.normalized_size == pytest.approx(expected_requested_size)
    assert quote.sizing_method == "stop_distance"


@pytest.mark.parametrize(
    "sizing_profile",
    [
        {
            "mode": BrokerSizingMode.EXACT_POINT_VALUE.value,
            "price_increment": 0.0,
            "value_per_increment": 10.0,
        },
        {
            "mode": BrokerSizingMode.EXACT_CONTRACT_RISK.value,
            "contract_multiplier": 0.0,
        },
        {"mode": "BROKER_MAGIC"},
    ],
)
def test_audit_broker_002_fake_derived_sizing_rejects_incomplete_profiles(
    sizing_profile,
):
    broker = FakeBroker()
    broker.market_details_by_instrument[INSTRUMENT] = BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.1,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status="TRADEABLE",
        update_time=datetime(2026, 5, 8, 12, 0, tzinfo=UTC).isoformat(),
        tradable=True,
        metadata={"sizing_profile": sizing_profile},
    )

    quote = broker.quote_risk_sized_order(
        INSTRUMENT,
        entry_price=100.0,
        risk_amount=50.0,
        stop_loss_price=98.0,
    )

    assert quote.precision is BrokerSizingPrecision.UNSUPPORTED
    assert quote.mode is BrokerSizingMode.UNSUPPORTED
    assert quote.sizing_available is False
    assert quote.reason_code == "unsupported_sizing"


def test_audit_broker_002_fake_normalization_can_require_explicit_outcomes():
    broker = FakeBroker(require_explicit_size_normalization=True)

    with pytest.raises(AssertionError, match="size normalization"):
        broker.normalize_order_size(INSTRUMENT, 0.2)

    broker.normalize_order_size_outcomes[INSTRUMENT] = [
        RuntimeError("normalization metadata drift"),
        BrokerSizeNormalization(
            instrument=INSTRUMENT,
            requested_size=0.2,
            normalized_size=0.0,
            accepted=False,
            reason_code="below_min_size",
            reason="Computed size is below broker minimum deal size.",
            min_deal_size=1.0,
            size_step=0.1,
        ),
    ]

    with pytest.raises(RuntimeError, match="normalization metadata drift"):
        broker.normalize_order_size(INSTRUMENT, 0.2)

    normalization = broker.normalize_order_size(INSTRUMENT, 0.2)

    assert normalization.accepted is False
    assert normalization.reason_code == "below_min_size"
    assert normalization.min_deal_size == pytest.approx(1.0)
    assert normalization.size_step == pytest.approx(0.1)


def test_audit_broker_002_fake_positions_can_require_explicit_reconciliation_truth():
    broker = FakeBroker(require_explicit_positions=True)
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)

    with pytest.raises(AssertionError, match="positions"):
        broker.get_positions()

    broker.position_outcomes.append(RuntimeError("positions unavailable"))

    with pytest.raises(RuntimeError, match="positions unavailable"):
        broker.get_positions()

    broker.position_outcomes.append(
        [
            BrokerPosition(
                broker_reference="remote-open-1",
                instrument=INSTRUMENT,
                direction=OrderDirection.BUY,
                size=0.2,
                open_price=100.5,
                opened_at=now,
            )
        ]
    )

    positions = broker.get_positions()

    assert len(positions) == 1
    assert positions[0].broker_reference == "remote-open-1"
    assert positions[0].size == pytest.approx(0.2)


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
        BrokerOrderStatus.REJECTED,
        BrokerOrderStatus.FAILED,
        BrokerOrderStatus.CANCELLED,
    ],
)
def test_audit_broker_002_fake_entry_incomplete_final_results_keep_correlation(
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
            filled_size=0.1 if status is BrokerOrderStatus.PARTIALLY_FILLED else None,
            average_fill_price=100.5
            if status is BrokerOrderStatus.PARTIALLY_FILLED
            else None,
            reason="Queued live-like incomplete final outcome.",
            requires_manual_review=status is BrokerOrderStatus.PARTIALLY_FILLED,
        )
    )

    result = broker.place_order(
        OrderRequest(
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            strategy_name="smoke_test_hold",
            client_request_id="entry-final-client-request-1",
        )
    )

    assert result.status is status
    assert result.client_request_id == "entry-final-client-request-1"
    assert result.requested_size == pytest.approx(0.2)
    if status is BrokerOrderStatus.PARTIALLY_FILLED:
        assert result.filled_size == pytest.approx(0.1)
        assert result.requires_manual_review is True


def test_audit_broker_002_fake_mutation_retries_never_auto_succeed():
    broker = FakeBroker()
    now = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    order = OrderRequest(
        instrument=INSTRUMENT,
        direction=OrderDirection.BUY,
        size=0.2,
        price=100.5,
        strategy_name="smoke_test_hold",
        client_request_id="entry-idempotency-1",
    )
    broker.place_order_outcomes.append(
        BrokerOrderResult(
            broker_reference="entry-idempotency",
            instrument=INSTRUMENT,
            direction=OrderDirection.BUY,
            size=0.2,
            price=100.5,
            executed_at=now,
        )
    )

    first = broker.place_order(order)

    with pytest.raises(AssertionError, match="place_order outcome"):
        broker.place_order(order)

    with pytest.raises(AssertionError, match="close_position outcome"):
        broker.close_position(
            INSTRUMENT,
            broker_reference="entry-idempotency",
            client_request_id="close-idempotency-1",
        )

    assert first.client_request_id == "entry-idempotency-1"
    assert first.requested_size == pytest.approx(0.2)
    assert len(broker.placed_orders) == 2
    assert broker.close_requests == [
        {
            "instrument": INSTRUMENT,
            "broker_reference": "entry-idempotency",
            "client_request_id": "close-idempotency-1",
        }
    ]


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
