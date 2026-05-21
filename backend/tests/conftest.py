from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.core.config import Settings, get_settings
from app.core.runtime import runtime_manager
from app.db.migrations import ensure_database_schema_current
from app.db.session import get_session
from app.main import create_app
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.market_status_service import get_market_status_service
from app.services.watchlist_service import get_watchlist_service
from tests.fakes import FakeBroker


@pytest.fixture(autouse=True)
def reset_runtime_manager() -> Iterator[None]:
    runtime_manager.engines.clear()
    runtime_manager.last_prices.clear()
    runtime_manager.last_price_updated_at.clear()
    runtime_manager.last_price_errors.clear()
    get_health_service().reset()
    get_market_status_service().reset()
    watchlist_service = get_watchlist_service()
    watchlist_service.session = None
    yield
    runtime_manager.engines.clear()
    runtime_manager.last_prices.clear()
    runtime_manager.last_price_updated_at.clear()
    runtime_manager.last_price_errors.clear()
    get_health_service().reset()
    get_market_status_service().reset()
    watchlist_service = get_watchlist_service()
    watchlist_service.session = None


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
def patch_external_boundaries(
    monkeypatch: pytest.MonkeyPatch, broker: FakeBroker
) -> None:
    monkeypatch.setattr("app.core.runtime.get_broker", lambda: broker)
    monkeypatch.setattr("app.core.broker_factory.get_broker", lambda: broker)
    monkeypatch.setattr(
        "app.services.market_overview_service.get_broker", lambda: broker
    )
    monkeypatch.setattr("app.services.market_status_service.get_broker", lambda: broker)
    monkeypatch.setattr(
        "app.services.reconciliation_service.get_broker", lambda: broker
    )
    monkeypatch.setattr(
        "app.services.runtime_recovery_service.get_broker", lambda: broker
    )
    monkeypatch.setattr(domain_event_service, "record_event", lambda **_: None)


@pytest.fixture(scope="session")
def migrated_sqlite_template(tmp_path_factory) -> str:
    template_dir = tmp_path_factory.mktemp("sqlite-template")
    template_path = template_dir / "template.sqlite"
    engine = create_engine(
        f"sqlite:///{template_path}",
        connect_args={"check_same_thread": False},
    )
    ensure_database_schema_current(engine)
    engine.dispose()
    return str(template_path)


@pytest.fixture
def session(tmp_path, migrated_sqlite_template: str) -> Iterator[Session]:
    db_path = tmp_path / "test.sqlite"
    shutil.copyfile(migrated_sqlite_template, db_path)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def app_factory(session: Session):
    def _build_app(**setting_overrides):
        settings = Settings(**{**get_settings().model_dump(), **setting_overrides})
        app = create_app(active_settings=settings, enable_lifespan=False)

        def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session
        return app

    return _build_app


@pytest.fixture
def client_factory(app_factory):
    @contextmanager
    def _build_client(**setting_overrides):
        app = app_factory(**setting_overrides)
        with TestClient(app) as client:
            yield client

    return _build_client
