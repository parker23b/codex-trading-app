from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.errors import operator_error_detail
from app.core.broker import BrokerError
from app.services.broker_service import BrokerService

router = APIRouter(prefix="/broker")


class BrokerPositionResponse(BaseModel):
    broker_reference: str
    instrument: str
    direction: str
    size: float
    open_price: float
    opened_at: datetime


@router.get("/positions", response_model=list[BrokerPositionResponse])
def list_broker_positions() -> list[BrokerPositionResponse]:
    try:
        positions = BrokerService().list_remote_positions()
    except BrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=operator_error_detail(
                exc,
                default_detail="Unable to load broker positions.",
                prefix="Unable to load broker positions",
            ),
        ) from exc

    return [
        BrokerPositionResponse(
            broker_reference=position.broker_reference,
            instrument=position.instrument,
            direction=position.direction.value,
            size=position.size,
            open_price=position.open_price,
            opened_at=position.opened_at,
        )
        for position in positions
    ]
