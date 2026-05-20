from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.contracts.trading import (
    OpenPositionResponse,
    TradeResponse,
    serialize_open_position,
    serialize_trade,
)
from app.db.session import get_session
from app.services.trade_service import TradeService

router = APIRouter()

_serialize_trade = serialize_trade


@router.get("", response_model=list[TradeResponse])
def list_trades(
    strategy: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[TradeResponse]:
    trades = TradeService(session).list_trades(
        strategy_name=strategy, date_from=date_from, date_to=date_to
    )
    return [serialize_trade(trade) for trade in trades]


@router.get("/positions", response_model=list[OpenPositionResponse])
def list_positions_compat(
    session: Session = Depends(get_session),
) -> list[OpenPositionResponse]:
    positions = TradeService(session).list_positions()
    now = datetime.now(UTC)
    return [serialize_open_position(position, now=now) for position in positions]
