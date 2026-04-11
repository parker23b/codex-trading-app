from __future__ import annotations

from datetime import timedelta

from sqlmodel import select

from app.models.domain_event import DomainEvent
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position, ReconciliationEvent, Trade, TradeIntent
from app.services.history_reset_service import HistoryResetService


def test_clear_test_history_removes_persisted_history_but_keeps_active_state(session, fixed_now):
    session.add(
        Trade(
            strategy_name="mean_reversion",
            broker_reference="open-1",
            close_broker_reference="close-1",
            instrument="IX.D.FTSE.DAILY.IP",
            direction="BUY",
            size=1.0,
            open_price=100.0,
            close_price=110.0,
            open_time=fixed_now - timedelta(hours=2),
            close_time=fixed_now - timedelta(hours=1),
            pnl=10.0,
            account_type="DEMO",
        )
    )
    session.add(
        TradeIntent(
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            direction="BUY",
            state="CLOSED",
            signal_time=fixed_now - timedelta(hours=2),
        )
    )
    session.add(
        Execution(
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            phase="ENTRY",
            status="FILL_FULL",
            signal_time=fixed_now - timedelta(hours=2),
            last_transition_at=fixed_now - timedelta(hours=1),
        )
    )
    session.add(
        ReconciliationEvent(
            event_type="POSITION_SYNCED_FROM_BROKER",
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            broker_reference="ref-1",
            local_position_id=1,
            created_at=fixed_now - timedelta(minutes=30),
        )
    )
    session.add(
        DomainEvent(
            created_at=fixed_now - timedelta(minutes=20),
            event_type="execution.position_closed",
            category="execution",
            severity="info",
            source="tests",
            title="Position closed",
        )
    )
    session.add(
        GeneratedReviewRecord(
            review_type="operator_summary",
            generated_at=fixed_now - timedelta(minutes=10),
        )
    )
    session.add(
        Position(
            strategy_name="mean_reversion",
            broker_reference="closed-1",
            instrument="IX.D.FTSE.DAILY.IP",
            direction="BUY",
            size=1.0,
            open_price=100.0,
            close_price=110.0,
            open_time=fixed_now - timedelta(hours=2),
            close_time=fixed_now - timedelta(hours=1),
            account_type="DEMO",
            is_open=False,
        )
    )
    session.add(
        Position(
            strategy_name="carry_drift",
            broker_reference="open-2",
            instrument="IX.D.DAX.DAILY.IP",
            direction="SELL",
            size=0.5,
            open_price=200.0,
            open_time=fixed_now - timedelta(minutes=45),
            account_type="DEMO",
            is_open=True,
        )
    )
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-idle",
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            status="STOPPED",
        )
    )
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-running",
            strategy_name="carry_drift",
            instrument="IX.D.DAX.DAILY.IP",
            status="RUNNING",
        )
    )
    session.commit()

    summary = HistoryResetService(session).clear_test_history()

    assert summary.trades_deleted == 1
    assert summary.trade_intents_deleted == 1
    assert summary.executions_deleted == 1
    assert summary.reconciliation_events_deleted == 1
    assert summary.domain_events_deleted == 1
    assert summary.reviews_deleted == 1
    assert summary.closed_positions_deleted == 1
    assert summary.idle_runtimes_deleted == 1

    assert session.exec(select(Trade)).all() == []
    assert session.exec(select(TradeIntent)).all() == []
    assert session.exec(select(Execution)).all() == []
    assert session.exec(select(ReconciliationEvent)).all() == []
    assert session.exec(select(DomainEvent)).all() == []
    assert session.exec(select(GeneratedReviewRecord)).all() == []

    remaining_positions = session.exec(select(Position)).all()
    assert len(remaining_positions) == 1
    assert remaining_positions[0].broker_reference == "open-2"

    remaining_runtimes = session.exec(select(StrategyRuntimeState)).all()
    assert len(remaining_runtimes) == 1
    assert remaining_runtimes[0].runtime_id == "runtime-running"
