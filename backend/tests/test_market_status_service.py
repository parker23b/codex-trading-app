from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.broker import BrokerMarketDetails
from app.core.runtime import runtime_manager
from app.services.market_status_service import get_market_status_service


INSTRUMENT = "CS.D.EURUSD.MINI.IP"


def _market_details(
    *,
    market_status: str | None,
    update_time: str | None,
    tradable: bool = True,
    market_order_preference: str | None = None,
) -> BrokerMarketDetails:
    return BrokerMarketDetails(
        instrument=INSTRUMENT,
        name=INSTRUMENT,
        bid=100.0,
        offer=100.01,
        high=101.0,
        low=99.0,
        percentage_change=0.0,
        net_change=0.0,
        market_status=market_status,
        update_time=update_time,
        tradable=tradable,
        market_order_preference=market_order_preference,
    )


@pytest.mark.parametrize("market_status", [None, "", "UNKNOWN", "DEALING_RESTRICTED"])
def test_audit_broker_003_market_status_fails_closed_for_missing_or_unknown_values(
    broker, fixed_now, market_status
):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status=market_status,
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is False
    assert status.market_open is False
    assert "closed" in (status.reason or "").lower()


@pytest.mark.parametrize("market_status", ["CLOSED", "SUSPENDED", "OFFLINE"])
def test_market_status_blocks_known_closed_or_unavailable_states(
    broker, fixed_now, market_status
):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status=market_status,
        update_time=fixed_now.isoformat(),
        tradable=True,
    )
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is False
    assert status.market_open is False


def test_market_status_blocks_missing_broker_update_time_even_with_price(
    broker, fixed_now
):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status="TRADEABLE",
        update_time=None,
        tradable=True,
    )

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is False
    assert status.quote_fresh is False
    assert "no price" in (status.reason or "").lower()


def test_market_status_accepts_fresh_stream_tick_without_runtime_price(
    broker, fixed_now, monkeypatch: pytest.MonkeyPatch
):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status="TRADEABLE",
        update_time=None,
        tradable=True,
    )

    class StubStreamingService:
        @staticmethod
        def get_last_tick_at(instrument: str):
            assert instrument == INSTRUMENT
            return fixed_now

    monkeypatch.setattr(
        "app.services.market_status_service.get_market_status_streaming_service",
        lambda: StubStreamingService(),
    )

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is True
    assert status.quote_fresh is True
    assert status.last_price_age_ms == 0.0
    assert status.reason is None


def test_market_status_blocks_stale_broker_update_time(broker, fixed_now):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status="TRADEABLE",
        update_time=(fixed_now - timedelta(seconds=10)).isoformat(),
        tradable=True,
    )

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is False
    assert status.quote_fresh is False
    assert "stale" in (status.reason or "").lower()


def test_market_status_blocks_broker_dealing_restrictions(broker, fixed_now):
    broker.market_details_by_instrument[INSTRUMENT] = _market_details(
        market_status="TRADEABLE",
        update_time=fixed_now.isoformat(),
        tradable=True,
        market_order_preference="LIMIT_ONLY",
    )
    runtime_manager.last_price_updated_at[INSTRUMENT] = fixed_now

    status = get_market_status_service().get_status(
        INSTRUMENT, broker=broker, now=fixed_now
    )

    assert status.is_ok is False
    assert status.dealing_allowed is False
    assert "dealing restrictions" in (status.reason or "").lower()
