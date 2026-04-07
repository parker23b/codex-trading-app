from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.ig_broker import IGBrokerError
from app.models.trade import Position, Trade
from app.services.dashboard_service import DashboardService
from app.services.trade_service import TradeService


def test_dashboard_uses_persisted_trades_and_positions_when_broker_summary_unavailable(
    session,
    fixed_now,
    broker,
    monkeypatch,
):
    trade_service = TradeService(session)
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
            open_time=fixed_now - timedelta(days=1, minutes=10),
            close_time=fixed_now - timedelta(days=1),
            pnl=10.0,
            account_type="DEMO",
        )
    )
    session.add(
        Trade(
            strategy_name="carry_drift",
            broker_reference="open-2",
            close_broker_reference="close-2",
            instrument="IX.D.DAX.DAILY.IP",
            direction="SELL",
            size=1.0,
            open_price=200.0,
            close_price=190.0,
            open_time=fixed_now - timedelta(hours=3),
            close_time=fixed_now - timedelta(hours=2),
            pnl=10.0,
            account_type="DEMO",
        )
    )
    session.add(
        Position(
            strategy_name="smoke_test_hold",
            broker_reference="pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            size=0.2,
            open_price=100.0,
            open_time=fixed_now - timedelta(hours=1),
            current_price=101.0,
            unrealized_pnl=0.2,
            risk_percent=0.3,
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()

    monkeypatch.setattr(
        "app.services.dashboard_service.get_broker",
        lambda: type(
            "FailingBroker",
            (),
            {"get_account_summary": lambda self: (_ for _ in ()).throw(IGBrokerError("unavailable"))},
        )(),
    )
    monkeypatch.setattr(DashboardService, "_running_strategies", staticmethod(lambda: []))
    monkeypatch.setattr("app.services.dashboard_service.datetime", type("FixedDatetime", (), {"now": staticmethod(lambda tz=None: fixed_now)}))

    dashboard = DashboardService(trade_service).get_dashboard()

    assert dashboard["accountValue"] == 100020.2
    assert dashboard["dailyPnl"] == 10.2
    assert dashboard["openRisk"] == 0.3
    assert dashboard["winRate"] == 100.0
    assert dashboard["riskReward"] == 10.0
    assert dashboard["runningStrategies"] == []
