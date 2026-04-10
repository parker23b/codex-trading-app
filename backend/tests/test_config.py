from __future__ import annotations

import pytest

from app.core.config import BACKEND_ROOT, Settings


def test_settings_normalize_relative_sqlite_database_url_against_backend_root():
    settings = Settings(database_url="sqlite:///./trading_platform.db")

    assert settings.database_url == f"sqlite:///{(BACKEND_ROOT / 'trading_platform.db').resolve().as_posix()}"


def test_settings_parse_streaming_budgets_and_seed_instruments():
    settings = Settings(
        ig_streaming_asset_class_slot_budgets="FOREX=4,INDICES=2",
        ig_streaming_seed_instruments="CS.D.EURUSD.CFD.IP,IX.D.SP500.DAILY.IP",
        tier2_seed_instruments="COM.D.XAUUSD.CFD.IP,IX.D.NASDAQ.DAILY.IP",
    )

    assert settings.ig_streaming_asset_class_slot_budgets == {"FOREX": 4, "INDICES": 2}
    assert settings.ig_streaming_seed_instruments == ["CS.D.EURUSD.CFD.IP", "IX.D.SP500.DAILY.IP"]
    assert settings.tier2_seed_instruments == ["COM.D.XAUUSD.CFD.IP", "IX.D.NASDAQ.DAILY.IP"]


def test_settings_reject_non_positive_requested_frequency():
    with pytest.raises(ValueError):
        Settings(ig_streaming_requested_frequency="0")
