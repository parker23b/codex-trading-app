from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.models.trade import Trade
from app.services.broker_service import BrokerService
from app.services.simulation_service import simulation_service
from app.services.trade_service import TradeService

router = APIRouter()


class TradeResponse(BaseModel):
    id: int
    strategy_name: str
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    pnl: float
    account_type: str
    r_multiple: float | None
    reason: str | None
    outcome: str


def _serialize_trade(trade: Trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id or 0,
        strategy_name=trade.strategy_name,
        instrument=trade.instrument,
        direction=trade.direction,
        size=trade.size,
        open_price=trade.open_price,
        close_price=trade.close_price,
        open_time=trade.open_time,
        close_time=trade.close_time,
        pnl=trade.pnl,
        account_type=trade.account_type,
        r_multiple=trade.r_multiple,
        reason=trade.reason,
        outcome=trade.outcome or ("win" if trade.pnl > 0 else "loss"),
    )


@router.get("", response_model=list[TradeResponse])
def list_trades(
    strategy: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[TradeResponse]:
    simulation_service.advance_market(session, ticks=1)
    trades = TradeService(session).list_trades(strategy_name=strategy, date_from=date_from, date_to=date_to)
    return [_serialize_trade(trade) for trade in trades]


@router.get("/positions")
def list_positions_compat(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    if simulation_service.enabled:
        simulation_service.advance_market(session, ticks=1)
    else:
        BrokerService().reconcile_positions(session)
    positions = TradeService(session).list_positions()
    now = datetime.now(UTC)
    return [
        {
            "id": position.id or 0,
            "strategy_name": position.strategy_name,
            "instrument": position.instrument,
            "direction": position.direction,
            "size": position.size,
            "open_price": position.open_price,
            "close_price": position.close_price,
            "open_time": position.open_time,
            "close_time": position.close_time,
            "pnl": position.pnl,
            "account_type": position.account_type,
            "is_open": position.is_open,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "risk_percent": position.risk_percent,
            "reason": position.reason,
            "manual_override": position.manual_override,
            "time_in_trade_seconds": max(int((now - position.open_time.astimezone(UTC)).total_seconds()), 0),
        }
        for position in positions
    ]
