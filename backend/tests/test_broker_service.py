from __future__ import annotations

from datetime import timedelta

from app.core.ig_broker import IGBrokerError
from app.models.trade import Position
from app.services.broker_service import BrokerService
from app.services.trade_service import TradeService


def test_reconcile_positions_falls_back_to_local_positions_when_broker_unavailable(
    session, broker, fixed_now
):
    trade_service = TradeService(session)
    local_position = trade_service.record_broker_position(
        Position(
            strategy_name="smoke_test_hold",
            broker_reference="broker-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction="BUY",
            size=0.2,
            open_price=100.0,
            open_time=fixed_now - timedelta(minutes=10),
            current_price=100.1,
            unrealized_pnl=0.02,
            account_type="DEMO",
            is_open=True,
        )
    )

    broker.remote_positions = []
    broker.get_positions = lambda: (_ for _ in ()).throw(
        IGBrokerError("Unable to reach IG API: timeout")
    )

    positions = BrokerService().reconcile_positions(session)

    assert len(positions) == 1
    assert positions[0].id == local_position.id
    assert positions[0].broker_reference == "broker-pos-1"
    assert trade_service.list_reconciliation_events(limit=10) == []
