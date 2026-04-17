from __future__ import annotations

import pytest

from app.core.broker import AccountType, BrokerSizingMode, BrokerSizingPrecision
from app.core.ig_broker import IGBroker


def test_ig_market_details_parse_sizing_semantics():
    broker = IGBroker(
        AccountType.DEMO,
        api_key=None,
        username=None,
        password=None,
        account_id=None,
        base_url=None,
        trading_enabled=False,
    )
    payload = {
        "instrument": {
            "name": "EUR/USD",
            "type": "CURRENCIES",
            "unit": "AMOUNT",
            "lotSize": "0.1",
            "contractSize": "1",
            "valueOfOnePip": "1",
            "scalingFactor": "10000",
            "onePipMeans": "0.0001 USD/EUR",
            "currencies": [{"code": "USD", "isDefault": True}],
        },
        "snapshot": {
            "bid": "1.2345",
            "offer": "1.2346",
            "high": "1.24",
            "low": "1.23",
            "percentageChange": "0.0",
            "netChange": "0.0",
            "marketStatus": "TRADEABLE",
            "updateTime": "12:00:00",
        },
        "dealingRules": {
            "minDealSize": {"value": "0.1"},
            "minNormalStopOrLimitDistance": {"value": "0.0003"},
            "marketOrderPreference": "AVAILABLE_DEFAULT_ON",
        },
    }

    details = broker._parse_market_details("CS.D.EURUSD.MINI.IP", payload)

    assert details.min_deal_size == 0.1
    assert details.size_step == 0.1
    assert details.metadata["provider"] == "IG"
    assert details.metadata["size_unit"] == "AMOUNT"
    assert details.metadata["ig_sizing"]["value_per_increment"] == 1.0
    assert details.metadata["ig_sizing"]["scaling_factor"] == 10_000.0
    assert details.metadata["ig_sizing"]["price_increment"] == 0.0001
    assert details.metadata["ig_sizing"]["instrument_type"] == "CURRENCIES"


def test_ig_quote_risk_sized_order_is_exact_when_metadata_is_complete(monkeypatch):
    broker = IGBroker(
        AccountType.DEMO,
        api_key=None,
        username=None,
        password=None,
        account_id=None,
        base_url=None,
        trading_enabled=False,
    )
    monkeypatch.setattr(
        broker,
        "get_market_details",
        lambda instrument: broker._parse_market_details(
            instrument,
            {
                "instrument": {
                    "name": "EUR/USD",
                    "type": "CURRENCIES",
                    "unit": "AMOUNT",
                    "lotSize": "0.1",
                    "contractSize": "1",
                    "valueOfOnePip": "1",
                    "scalingFactor": "10000",
                    "onePipMeans": "0.0001 USD/EUR",
                    "currencies": [{"code": "USD", "isDefault": True}],
                },
                "snapshot": {
                    "bid": "1.2345",
                    "offer": "1.2346",
                    "high": "1.24",
                    "low": "1.23",
                    "percentageChange": "0.0",
                    "netChange": "0.0",
                    "marketStatus": "TRADEABLE",
                    "updateTime": "12:00:00",
                },
                "dealingRules": {
                    "minDealSize": {"value": "0.1"},
                    "minNormalStopOrLimitDistance": {"value": "0.0003"},
                    "marketOrderPreference": "AVAILABLE_DEFAULT_ON",
                },
            },
        ),
    )
    monkeypatch.setattr(broker, "_get_account_currency", lambda: "USD")

    quote = broker.quote_risk_sized_order(
        "CS.D.EURUSD.MINI.IP",
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
