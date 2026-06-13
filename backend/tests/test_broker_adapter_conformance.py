from __future__ import annotations

import pytest

from app.core.broker import AccountType, Broker, BrokerCapabilities
from app.core.ig_broker import IGBroker
from tests.fakes import FakeBroker


@pytest.fixture(params=["fake", "ig"])
def adapter(request) -> Broker:
    if request.param == "fake":
        return FakeBroker()
    return IGBroker(
        api_key=None,
        username=None,
        password=None,
        account_id=None,
        base_url="https://demo-api.ig.com/gateway/deal",
        trading_enabled=False,
    )


def test_audit_broker_006_shared_adapter_capability_contract(adapter: Broker):
    assert isinstance(adapter.account_type, AccountType)
    assert isinstance(adapter.capabilities, BrokerCapabilities)
    assert isinstance(adapter.capabilities.supports_client_request_id, bool)
    assert isinstance(adapter.capabilities.supports_order_confirmation, bool)
    assert isinstance(adapter.capabilities.supports_batch_market_details, bool)
    assert isinstance(adapter.capabilities.supports_exact_risk_sizing, bool)
    assert isinstance(adapter.capabilities.supports_streaming, bool)
    assert isinstance(adapter.capabilities.supports_simulated_execution, bool)
