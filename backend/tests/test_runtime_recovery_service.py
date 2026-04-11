from __future__ import annotations

from datetime import timedelta

from app.core.broker import OrderDirection
from app.models.runtime import StrategyRuntimeState
from app.models.trade import TradeIntentState
from app.services.runtime_recovery_service import RuntimeRecoveryService
from app.services.trade_service import TradeService
from tests.fakes import make_broker_position


def test_runtime_recovery_creates_trade_intent_before_recreating_position(session, broker, fixed_now):
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-recover-1",
            strategy_name="smoke_test_hold",
            instrument="CS.D.EURUSD.MINI.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            current_position_broker_reference="recover-pos-1",
            last_price_seen=101.0,
            last_price_seen_at=fixed_now - timedelta(seconds=5),
        )
    )
    session.commit()
    broker.remote_positions = [
        make_broker_position(
            broker_reference="recover-pos-1",
            instrument="CS.D.EURUSD.MINI.IP",
            direction=OrderDirection.BUY,
            size=0.4,
            open_price=101.25,
            opened_at=fixed_now - timedelta(minutes=3),
        )
    ]

    RuntimeRecoveryService(session).recover()

    trade_service = TradeService(session)
    positions = trade_service.list_positions()
    intents = trade_service.list_trade_intents(limit=10)

    assert len(positions) == 1
    assert len(intents) == 1
    assert positions[0].trade_intent_id == intents[0].id
    assert intents[0].state == TradeIntentState.RECOVERED_POSITION_ATTACHED.value
    assert intents[0].position_id == positions[0].id
