from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.audit import persist_required_domain_event
from app.api.contracts.control_plane import StrategyMutationStatusResponse
from app.api.contracts.strategies import StrategySummaryResponse
from app.core.runtime import runtime_manager
from app.db.session import get_session
from app.services.strategy_service import StrategyService

router = APIRouter()


class StartStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Registered strategy name.")
    instrument: str = Field(..., description="Broker instrument identifier, e.g. epic.")


class StopStrategyRequest(BaseModel):
    instrument: str | None = Field(
        default=None, description="Instrument currently being managed."
    )
    strategy_name: str | None = Field(
        default=None, description="Optional strategy name to target a specific runtime."
    )


@router.get("/strategies", response_model=list[StrategySummaryResponse])
def list_strategies(
    session: Session = Depends(get_session),
) -> list[StrategySummaryResponse]:
    """Return operator strategy state from persisted/runtime truth only."""
    return [
        StrategySummaryResponse(**strategy)
        for strategy in StrategyService(session).list_strategies()
    ]


@router.post("/strategy/start", response_model=StrategyMutationStatusResponse)
def start_strategy(
    payload: StartStrategyRequest,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
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
    engine = runtime_manager.get_engine(payload.strategy_name, payload.instrument)
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy runtime was started, but durable audit persistence failed."
        ),
        event_type="operator.runtime_started",
        category="operator",
        severity="info",
        source="api.strategy.start",
        title="Operator started strategy runtime",
        message=f"Operator started {payload.strategy_name} on {payload.instrument}.",
        runtime_id=engine.runtime_id if engine is not None else None,
        strategy_name=payload.strategy_name,
        instrument=payload.instrument,
        actor_type="operator",
        actor_id="api",
    )

    return StrategyMutationStatusResponse(
        status="started",
        strategy=payload.strategy_name,
        instrument=payload.instrument,
    )


@router.post("/strategy/stop", response_model=StrategyMutationStatusResponse)
def stop_strategy(
    payload: StopStrategyRequest,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
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
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy runtime was stopped, but durable audit persistence failed."
        ),
        event_type="operator.runtime_stopped",
        category="operator",
        severity="info",
        source="api.strategy.stop",
        title="Operator stopped strategy runtime",
        message="Operator stopped one or more strategy runtimes.",
        strategy_name=payload.strategy_name,
        instrument=payload.instrument,
        actor_type="operator",
        actor_id="api",
        payload_json={
            "strategy_name": payload.strategy_name,
            "instrument": payload.instrument,
        },
    )

    return StrategyMutationStatusResponse(
        status="stopped",
        strategy=payload.strategy_name,
        instrument=payload.instrument,
    )


@router.post("/strategies/{name}/start", response_model=StrategyMutationStatusResponse)
def start_strategy_by_name(
    name: str,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    service = StrategyService(session)
    strategies = {strategy["name"]: strategy for strategy in service.list_strategies()}
    strategy = strategies.get(name)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy '{name}' not found.",
        )

    instrument = str(strategy["instrument"])
    try:
        service.start_strategy(strategy_name=name, instrument=instrument)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    engine = runtime_manager.get_engine(name, instrument)
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy runtime was started, but durable audit persistence failed."
        ),
        event_type="operator.runtime_started",
        category="operator",
        severity="info",
        source="api.strategies.start_by_name",
        title="Operator started strategy runtime",
        message=f"Operator started {name} on {instrument}.",
        runtime_id=engine.runtime_id if engine is not None else None,
        strategy_name=name,
        instrument=instrument,
        actor_type="operator",
        actor_id="api",
    )
    return StrategyMutationStatusResponse(
        status="started", strategy=name, instrument=instrument
    )


@router.post("/strategies/{name}/stop", response_model=StrategyMutationStatusResponse)
def stop_strategy_by_name(
    name: str,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    service = StrategyService(session)
    strategies = {strategy["name"]: strategy for strategy in service.list_strategies()}
    strategy = strategies.get(name)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy '{name}' not found.",
        )

    instrument = str(strategy["instrument"])
    try:
        service.stop_strategy(strategy_name=name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy runtime was stopped, but durable audit persistence failed."
        ),
        event_type="operator.runtime_stopped",
        category="operator",
        severity="info",
        source="api.strategies.stop_by_name",
        title="Operator stopped strategy runtime",
        message=f"Operator stopped {name} on {instrument}.",
        strategy_name=name,
        instrument=instrument,
        actor_type="operator",
        actor_id="api",
    )
    return StrategyMutationStatusResponse(
        status="stopped", strategy=name, instrument=instrument
    )
