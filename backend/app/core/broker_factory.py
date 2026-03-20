from app.core.broker import AccountType, Broker
from app.core.config import get_settings
from app.core.ig_broker import IGBroker


def get_broker() -> Broker:
    settings = get_settings()
    return IGBroker(account_type=AccountType(settings.broker_mode))

