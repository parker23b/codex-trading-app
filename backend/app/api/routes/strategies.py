from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.services.strategy_service import StrategyService

router = APIRouter()


class StartStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Registered strategy name.")
    instrument: str = Field(..., description="Broker instrument identifier, e.g. epic.")


class StopStrategyRequest(BaseModel):
    instrument: str = Field(..., description="Instrument currently being managed.")


@router.get("/strategies")
def list_strategies() -> list[dict[str, str]]:
    return StrategyService().list_strategies()


@router.post("/strategy/start")
def start_strategy(
    payload: StartStrategyRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    try:
        StrategyService(session).start_strategy(
            strategy_name=payload.strategy_name,
            instrument=payload.instrument,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "started"}


@router.post("/strategy/stop")
def stop_strategy(
    payload: StopStrategyRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    try:
        StrategyService(session).stop_strategy(instrument=payload.instrument)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return {"status": "stopped"}
