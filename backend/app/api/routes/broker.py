from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.ig_broker import IGBrokerError
from app.services.broker_service import BrokerService

router = APIRouter(prefix="/broker")


class BrokerPositionResponse(BaseModel):
    instrument: str
    direction: str
    size: float
    open_price: float
    opened_at: datetime


@router.get("/positions", response_model=list[BrokerPositionResponse])
def list_broker_positions() -> list[BrokerPositionResponse]:
    try:
        positions = BrokerService().list_remote_positions()
    except IGBrokerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return [
        BrokerPositionResponse(
            instrument=position.instrument,
            direction=position.direction.value,
            size=position.size,
            open_price=position.open_price,
            opened_at=position.opened_at,
        )
        for position in positions
    ]
