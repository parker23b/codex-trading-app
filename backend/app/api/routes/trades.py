from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.models.trade import Position, Trade
from app.services.trade_service import TradeService

router = APIRouter()


@router.get("", response_model=list[Trade])
def list_trades(session: Session = Depends(get_session)) -> list[Trade]:
    return TradeService(session).list_trades()


@router.get("/positions", response_model=list[Position])
def list_positions(session: Session = Depends(get_session)) -> list[Position]:
    return TradeService(session).list_positions()

