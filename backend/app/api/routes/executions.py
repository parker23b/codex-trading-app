from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.models.trade import Execution
from app.services.trade_service import TradeService

router = APIRouter()


class ExecutionResponse(BaseModel):
    id: int
    strategy_name: str
    instrument: str
    phase: str
    status: str
    broker_reference: str | None
    local_position_id: int | None
    local_trade_id: int | None
    signal_time: datetime
    submitted_at: datetime | None
    acknowledged_at: datetime | None
    completed_at: datetime | None
    last_transition_at: datetime
    requested_size: float | None
    filled_size: float | None
    requested_price: float | None
    average_fill_price: float | None
    reason: str | None
    error_code: str | None
    error_message: str | None
    requires_manual_review: bool
    details: dict[str, object]
    created_at: datetime
    updated_at: datetime


def _serialize_execution(execution: Execution) -> ExecutionResponse:
    return ExecutionResponse(
        id=execution.id or 0,
        strategy_name=execution.strategy_name,
        instrument=execution.instrument,
        phase=execution.phase,
        status=execution.status,
        broker_reference=execution.broker_reference,
        local_position_id=execution.local_position_id,
        local_trade_id=execution.local_trade_id,
        signal_time=execution.signal_time,
        submitted_at=execution.submitted_at,
        acknowledged_at=execution.acknowledged_at,
        completed_at=execution.completed_at,
        last_transition_at=execution.last_transition_at,
        requested_size=execution.requested_size,
        filled_size=execution.filled_size,
        requested_price=execution.requested_price,
        average_fill_price=execution.average_fill_price,
        reason=execution.reason,
        error_code=execution.error_code,
        error_message=execution.error_message,
        requires_manual_review=execution.requires_manual_review,
        details=execution.details,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


@router.get("/executions", response_model=list[ExecutionResponse])
def list_executions(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[ExecutionResponse]:
    executions = TradeService(session).list_executions(limit=limit)
    return [_serialize_execution(execution) for execution in executions]
