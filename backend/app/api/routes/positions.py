from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.models.trade import Position
from app.services.trade_service import TradeService

router = APIRouter()


class PositionResponse(BaseModel):
    id: int
    strategy_name: str
    instrument: str
    direction: str
    size: float
    open_price: float
    close_price: float | None
    open_time: datetime
    close_time: datetime | None
    pnl: float | None
    account_type: str
    is_open: bool
    current_price: float | None
    unrealized_pnl: float | None
    risk_percent: float | None
    reason: str | None
    manual_override: bool
    time_in_trade_seconds: int


def _serialize_position(position: Position) -> PositionResponse:
    now = datetime.now(UTC)
    return PositionResponse(
        id=position.id or 0,
        strategy_name=position.strategy_name,
        instrument=position.instrument,
        direction=position.direction,
        size=position.size,
        open_price=position.open_price,
        close_price=position.close_price,
        open_time=position.open_time,
        close_time=position.close_time,
        pnl=position.pnl,
        account_type=position.account_type,
        is_open=position.is_open,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        risk_percent=position.risk_percent,
        reason=position.reason,
        manual_override=position.manual_override,
        time_in_trade_seconds=max(int((now - position.open_time.astimezone(UTC)).total_seconds()), 0),
    )


@router.get("/positions", response_model=list[PositionResponse])
def list_positions(session: Session = Depends(get_session)) -> list[PositionResponse]:
    return [_serialize_position(position) for position in TradeService(session).list_positions()]
