from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.audit import persist_required_domain_event
from app.api.auth import build_operator_audit_context, resolve_request_settings
from app.api.contracts.control_plane import StrategyMutationStatusResponse
from app.api.contracts.strategies import StrategySummaryResponse
from app.api.errors import operator_error_detail
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
    request: Request,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    try:
        StrategyService(session).start_strategy(
            strategy_name=payload.strategy_name,
            instrument=payload.instrument,
            startup_context={
                "authority_kind": "http_route",
                "route_source": "api.strategy.start",
                "route_path": request.url.path,
                "actor_type": operator_context["actor_type"],
                "actor_id": operator_context["actor_id"],
                "correlation_id": operator_context["correlation_id"],
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=operator_error_detail(
                exc,
                default_detail="Unable to start strategy runtime.",
            ),
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
        correlation_id=operator_context["correlation_id"],
        runtime_id=engine.runtime_id if engine is not None else None,
        strategy_name=payload.strategy_name,
        instrument=payload.instrument,
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "runtime_id": engine.runtime_id if engine is not None else None,
            "startup_context": getattr(engine, "startup_context", {}) if engine else {},
        },
    )

    return StrategyMutationStatusResponse(
        status="started",
        strategy=payload.strategy_name,
        instrument=payload.instrument,
    )


@router.post("/strategy/stop", response_model=StrategyMutationStatusResponse)
def stop_strategy(
    payload: StopStrategyRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    try:
        stopped_runtimes = StrategyService(session).stop_strategy(
            instrument=payload.instrument,
            strategy_name=payload.strategy_name,
            stop_context={
                "authority_kind": "http_route",
                "route_source": "api.strategy.stop",
                "route_path": request.url.path,
                "actor_type": operator_context["actor_type"],
                "actor_id": operator_context["actor_id"],
                "correlation_id": operator_context["correlation_id"],
            },
            stop_reason="Operator requested runtime stop.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail="Strategy runtime was not found.",
            ),
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
        correlation_id=operator_context["correlation_id"],
        strategy_name=payload.strategy_name,
        instrument=payload.instrument,
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "strategy_name": payload.strategy_name,
            "instrument": payload.instrument,
            "previous_state": "RUNNING",
            "new_state": "STOPPED",
            "stopped_runtime_ids": [
                runtime["runtime_id"] for runtime in stopped_runtimes
            ],
            "stopped_runtime_count": len(stopped_runtimes),
            "stopped_instruments": [
                str(runtime["instrument"]) for runtime in stopped_runtimes
            ],
            "stop_reason": "Operator requested runtime stop.",
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
    request: Request,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
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
        service.start_strategy(
            strategy_name=name,
            instrument=instrument,
            startup_context={
                "authority_kind": "http_route",
                "route_source": "api.strategies.start_by_name",
                "route_path": request.url.path,
                "actor_type": operator_context["actor_type"],
                "actor_id": operator_context["actor_id"],
                "correlation_id": operator_context["correlation_id"],
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=operator_error_detail(
                exc,
                default_detail="Unable to start strategy runtime.",
            ),
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
        correlation_id=operator_context["correlation_id"],
        runtime_id=engine.runtime_id if engine is not None else None,
        strategy_name=name,
        instrument=instrument,
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "runtime_id": engine.runtime_id if engine is not None else None,
            "startup_context": getattr(engine, "startup_context", {}) if engine else {},
        },
    )
    return StrategyMutationStatusResponse(
        status="started", strategy=name, instrument=instrument
    )


@router.post("/strategies/{name}/stop", response_model=StrategyMutationStatusResponse)
def stop_strategy_by_name(
    name: str,
    request: Request,
    session: Session = Depends(get_session),
) -> StrategyMutationStatusResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
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
        stopped_runtimes = service.stop_strategy(
            strategy_name=name,
            stop_context={
                "authority_kind": "http_route",
                "route_source": "api.strategies.stop_by_name",
                "route_path": request.url.path,
                "actor_type": operator_context["actor_type"],
                "actor_id": operator_context["actor_id"],
                "correlation_id": operator_context["correlation_id"],
            },
            stop_reason="Operator requested runtime stop.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail="Strategy runtime was not found.",
            ),
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
        correlation_id=operator_context["correlation_id"],
        strategy_name=name,
        instrument=instrument,
        actor_type=str(operator_context["actor_type"]),
        actor_id=str(operator_context["actor_id"]),
        payload_json={
            "previous_state": "RUNNING",
            "new_state": "STOPPED",
            "stopped_runtime_ids": [
                runtime["runtime_id"] for runtime in stopped_runtimes
            ],
            "stopped_runtime_count": len(stopped_runtimes),
            "stopped_instruments": [
                str(runtime["instrument"]) for runtime in stopped_runtimes
            ],
            "stop_reason": "Operator requested runtime stop.",
        },
    )
    return StrategyMutationStatusResponse(
        status="stopped", strategy=name, instrument=instrument
    )
