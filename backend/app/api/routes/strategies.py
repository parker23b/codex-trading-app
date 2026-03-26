from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.services.broker_service import BrokerService
from app.services.strategy_service import StrategyService

router = APIRouter()


class StartStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Registered strategy name.")
    instrument: str = Field(..., description="Broker instrument identifier, e.g. epic.")


class StopStrategyRequest(BaseModel):
    instrument: str | None = Field(default=None, description="Instrument currently being managed.")
    strategy_name: str | None = Field(default=None, description="Optional strategy name to target a specific runtime.")


class StrategyControlResponse(BaseModel):
    status: str
    strategy: str
    instrument: str


@router.get("/strategies")
def list_strategies(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    BrokerService().reconcile_positions(session)
    return StrategyService(session).list_strategies()


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
        StrategyService(session).stop_strategy(
            instrument=payload.instrument,
            strategy_name=payload.strategy_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return {"status": "stopped"}


@router.post("/strategies/{name}/start", response_model=StrategyControlResponse)
def start_strategy_by_name(
    name: str,
    session: Session = Depends(get_session),
) -> StrategyControlResponse:
    service = StrategyService(session)
    strategies = {strategy["name"]: strategy for strategy in service.list_strategies()}
    strategy = strategies.get(name)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy '{name}' not found.")

    instrument = str(strategy["instrument"])
    try:
        service.start_strategy(strategy_name=name, instrument=instrument)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return StrategyControlResponse(status="started", strategy=name, instrument=instrument)


@router.post("/strategies/{name}/stop", response_model=StrategyControlResponse)
def stop_strategy_by_name(
    name: str,
    session: Session = Depends(get_session),
) -> StrategyControlResponse:
    service = StrategyService(session)
    strategies = {strategy["name"]: strategy for strategy in service.list_strategies()}
    strategy = strategies.get(name)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy '{name}' not found.")

    instrument = str(strategy["instrument"])
    try:
        service.stop_strategy(strategy_name=name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return StrategyControlResponse(status="stopped", strategy=name, instrument=instrument)
