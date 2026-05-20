from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.contracts.trading import OpenPositionResponse, serialize_open_position
from app.db.session import get_session
from app.services.trade_service import TradeService

router = APIRouter()


@router.get("/positions", response_model=list[OpenPositionResponse])
def list_positions(
    session: Session = Depends(get_session),
) -> list[OpenPositionResponse]:
    now = datetime.now(UTC)
    return [
        serialize_open_position(position, now=now)
        for position in TradeService(session).list_positions()
    ]
