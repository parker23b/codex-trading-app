from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.runtime import runtime_manager
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus, Position
from app.models.watchlist import WatchlistEntry, WatchlistStatus
from app.services.watchlist_service import WatchlistService


def test_streaming_plan_pins_open_positions_and_pending_executions(session):
    session.add(
        Position(
            strategy_name="mean_reversion",
            broker_reference="deal-1",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=1.0,
            open_price=1.1,
            open_time=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
            account_type="DEMO",
            is_open=True,
        )
    )
    session.add(
        Execution(
            strategy_name="carry_drift",
            instrument="IX.D.NASDAQ.DAILY.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.ORDER_SUBMITTED.value,
            signal_time=datetime(2026, 4, 9, 10, 1, tzinfo=UTC),
            last_transition_at=datetime(2026, 4, 9, 10, 1, tzinfo=UTC),
        )
    )
    session.commit()

    service = WatchlistService(session)
    plan = service.get_streaming_plan()

    assert "CS.D.EURUSD.CFD.IP" in plan.instruments
    assert "IX.D.NASDAQ.DAILY.IP" in plan.instruments
    assert set(plan.pinned_instruments) == {"CS.D.EURUSD.CFD.IP", "IX.D.NASDAQ.DAILY.IP"}


def test_streaming_plan_uses_runtime_instruments_with_budget_after_pins(session):
    settings = WatchlistService(session).settings
    settings.ig_streaming_max_instruments = 2
    runtime_manager.start("mean_reversion", "CS.D.GBPUSD.CFD.IP")
    runtime_manager.start("carry_drift", "IX.D.SP500.DAILY.IP")

    session.add(
        Position(
            strategy_name="fx_micro_pullback",
            broker_reference="deal-2",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=1.0,
            open_price=1.08,
            open_time=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()

    plan = WatchlistService(session).get_streaming_plan()

    assert "CS.D.EURUSD.CFD.IP" in plan.instruments
    assert len(plan.instruments) == 2
    assert len(plan.capped_instruments) == 1


def test_non_pinned_entry_enters_cooldown_after_min_residency(session):
    now = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    service = WatchlistService(session)
    service.settings.ig_streaming_min_tier1_residency_seconds = 30
    service.settings.ig_streaming_demotion_cooldown_seconds = 120
    runtime_manager.start("mean_reversion", "CS.D.GBPUSD.CFD.IP")
    service._sync_system_entries(session=session, now=now)

    runtime_manager.stop(strategy_name="mean_reversion", instrument="CS.D.GBPUSD.CFD.IP")
    service._sync_system_entries(session=session, now=now + timedelta(seconds=31))

    entry = session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == "CS.D.GBPUSD.CFD.IP")
    ).one()
    assert entry.status == WatchlistStatus.COOLDOWN.value
    assert entry.cooldown_until.replace(tzinfo=UTC) == now + timedelta(seconds=151)
