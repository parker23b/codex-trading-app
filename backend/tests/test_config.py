from __future__ import annotations

from app.core.config import BACKEND_ROOT, Settings


def test_settings_normalize_relative_sqlite_database_url_against_backend_root():
    settings = Settings(database_url="sqlite:///./trading_platform.db")

    assert settings.database_url == f"sqlite:///{(BACKEND_ROOT / 'trading_platform.db').resolve().as_posix()}"
