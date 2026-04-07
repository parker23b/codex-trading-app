from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.models.domain_event import DomainEvent
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position, ReconciliationEvent, Trade
from app.services.domain_event_service import domain_event_service
from tests.fakes import FakeBroker


@pytest.fixture(autouse=True)
def reset_runtime_manager() -> Iterator[None]:
    runtime_manager.engines.clear()
    runtime_manager.last_prices.clear()
    runtime_manager.last_price_updated_at.clear()
    runtime_manager.last_price_errors.clear()
    yield
    runtime_manager.engines.clear()
    runtime_manager.last_prices.clear()
    runtime_manager.last_price_updated_at.clear()
    runtime_manager.last_price_errors.clear()


@pytest.fixture(autouse=True)
def restore_settings() -> Iterator[None]:
    settings = get_settings()
    original_values = settings.model_dump()
    yield
    for field_name, value in original_values.items():
        setattr(settings, field_name, value)


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture(autouse=True)
def patch_external_boundaries(monkeypatch: pytest.MonkeyPatch, broker: FakeBroker) -> None:
    monkeypatch.setattr("app.core.runtime.get_broker", lambda: broker)
    monkeypatch.setattr("app.services.reconciliation_service.get_broker", lambda: broker)
    monkeypatch.setattr(domain_event_service, "record_event", lambda **_: None)


@pytest.fixture
def session() -> Iterator[Session]:
    _ = (Trade, Position, StrategyRuntimeState, ReconciliationEvent, Execution, DomainEvent)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
