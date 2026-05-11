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
    trade_intent_id: int | None
    strategy_name: str
    instrument: str
    phase: str
    status: str
    client_request_id: str | None
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
    intended_risk_amount: float | None
    submitted_risk_amount: float | None
    fill_derived_risk_amount: float | None
    risk_truth_confidence: str | None
    risk_reconciliation: dict[str, object] | None
    material_execution_drift: bool
    critical_execution_drift: bool
    reason: str | None
    error_code: str | None
    error_message: str | None
    requires_manual_review: bool
    details: dict[str, object]
    created_at: datetime
    updated_at: datetime


def _serialize_execution(execution: Execution) -> ExecutionResponse:
    risk_reconciliation = (execution.details or {}).get("risk_reconciliation")
    if not isinstance(risk_reconciliation, dict):
        risk_reconciliation = None
    drift_flags = (
        risk_reconciliation.get("flags")
        if isinstance(risk_reconciliation, dict)
        else None
    )
    if not isinstance(drift_flags, dict):
        drift_flags = {}
    return ExecutionResponse(
        id=execution.id or 0,
        trade_intent_id=execution.trade_intent_id,
        strategy_name=execution.strategy_name,
        instrument=execution.instrument,
        phase=execution.phase,
        status=execution.status,
        client_request_id=execution.client_request_id,
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
        intended_risk_amount=execution.intended_risk_amount,
        submitted_risk_amount=execution.submitted_risk_amount,
        fill_derived_risk_amount=execution.fill_derived_risk_amount,
        risk_truth_confidence=execution.risk_truth_confidence,
        risk_reconciliation=risk_reconciliation,
        material_execution_drift=bool(drift_flags.get("material_execution_drift")),
        critical_execution_drift=bool(drift_flags.get("critical_execution_drift")),
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
