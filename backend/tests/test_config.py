from __future__ import annotations

import pytest

from app.core.broker_environment import (
    BrokerEndpointClassification,
    BrokerEnvironment,
    IG_DEMO_BASE_URL,
    IG_LIVE_BASE_URL,
)
from app.core.config import BACKEND_ROOT, Settings


def test_settings_normalize_relative_sqlite_database_url_against_backend_root():
    settings = Settings(database_url="sqlite:///./trading_platform.db")

    assert (
        settings.database_url
        == f"sqlite:///{(BACKEND_ROOT / 'trading_platform.db').resolve().as_posix()}"
    )


def test_settings_parse_streaming_budgets_and_seed_instruments():
    settings = Settings(
        ig_streaming_asset_class_slot_budgets="FOREX=4,INDICES=2",
        ig_streaming_seed_instruments="CS.D.EURUSD.CFD.IP,IX.D.SP500.DAILY.IP",
        tier2_seed_instruments="COM.D.XAUUSD.CFD.IP,IX.D.NASDAQ.DAILY.IP",
    )

    assert settings.ig_streaming_asset_class_slot_budgets == {"FOREX": 4, "INDICES": 2}
    assert settings.ig_streaming_seed_instruments == [
        "CS.D.EURUSD.CFD.IP",
        "IX.D.SP500.DAILY.IP",
    ]
    assert settings.tier2_seed_instruments == [
        "COM.D.XAUUSD.CFD.IP",
        "IX.D.NASDAQ.DAILY.IP",
    ]


def test_settings_reject_non_positive_requested_frequency():
    with pytest.raises(ValueError):
        Settings(ig_streaming_requested_frequency="0")


def test_settings_default_ig_url_resolves_demo_environment():
    settings = Settings()

    assert settings.ig_api_base_url == IG_DEMO_BASE_URL
    assert settings.broker_environment is BrokerEnvironment.DEMO
    assert (
        settings.broker_endpoint_classification
        is BrokerEndpointClassification.IG_DEMO_GATEWAY
    )


def test_settings_accept_canonical_ig_demo_url():
    settings = Settings(ig_api_base_url=IG_DEMO_BASE_URL)

    assert settings.ig_api_base_url == IG_DEMO_BASE_URL
    assert settings.broker_environment is BrokerEnvironment.DEMO


def test_settings_accept_canonical_ig_live_url():
    settings = Settings(ig_api_base_url=IG_LIVE_BASE_URL, ig_trading_enabled=False)

    assert settings.ig_api_base_url == IG_LIVE_BASE_URL
    assert settings.broker_environment is BrokerEnvironment.LIVE
    assert (
        settings.broker_endpoint_classification
        is BrokerEndpointClassification.IG_LIVE_GATEWAY
    )


def test_settings_normalize_harmless_trailing_slash_on_ig_url():
    settings = Settings(ig_api_base_url=f"{IG_DEMO_BASE_URL}/")

    assert settings.ig_api_base_url == IG_DEMO_BASE_URL


@pytest.mark.parametrize(
    "raw_url",
    [
        "not-a-url",
        "http://demo-api.ig.com/gateway/deal",
        "https://unknown.example/gateway/deal",
        "https://demo-api.ig.com.evil.example/gateway/deal",
        "https://evil.example/demo-api.ig.com/gateway/deal",
        "https://demo-api.ig.com/gateway/not-deal",
    ],
)
def test_settings_reject_invalid_ig_gateway_urls(raw_url: str):
    with pytest.raises(ValueError):
        Settings(ig_api_base_url=raw_url)


def test_settings_live_dealing_requires_explicit_acknowledgement():
    with pytest.raises(ValueError):
        Settings(
            ig_api_base_url=IG_LIVE_BASE_URL,
            ig_trading_enabled=True,
            ig_live_trading_acknowledged=False,
        )


def test_settings_live_url_with_dealing_disabled_remains_valid():
    settings = Settings(
        ig_api_base_url=IG_LIVE_BASE_URL,
        ig_trading_enabled=False,
    )

    assert settings.broker_environment is BrokerEnvironment.LIVE
    assert settings.ig_trading_enabled is False


def test_settings_demo_url_with_dealing_enabled_remains_valid():
    settings = Settings(
        ig_api_base_url=IG_DEMO_BASE_URL,
        ig_trading_enabled=True,
    )

    assert settings.broker_environment is BrokerEnvironment.DEMO
    assert settings.ig_trading_enabled is True
