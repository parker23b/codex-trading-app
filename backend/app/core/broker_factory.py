from functools import lru_cache

from app.core.broker import Broker
from app.core.config import get_settings
from app.core.ig_broker import IGBroker
from app.core.resilient_broker import ResilientBroker


@lru_cache(maxsize=1)
def get_broker() -> Broker:
    settings = get_settings()
    adapter = IGBroker(
        api_key=settings.ig_api_key,
        username=settings.ig_username,
        password=settings.ig_password,
        account_id=settings.ig_account_id,
        base_url=settings.ig_api_base_url,
        request_timeout_seconds=settings.ig_request_timeout_seconds,
        trading_enabled=settings.ig_trading_enabled,
        live_trading_acknowledged=settings.ig_live_trading_acknowledged,
        verify_ssl=settings.ig_verify_ssl,
        ca_bundle_path=settings.ig_ca_bundle_path,
    )
    return ResilientBroker(
        adapter,
        read_max_attempts=settings.broker_read_max_attempts,
        read_backoff_base_seconds=settings.broker_read_backoff_base_seconds,
        read_backoff_max_seconds=settings.broker_read_backoff_max_seconds,
        circuit_failure_threshold=settings.broker_read_circuit_failure_threshold,
        circuit_cooldown_seconds=settings.broker_read_circuit_cooldown_seconds,
    )
