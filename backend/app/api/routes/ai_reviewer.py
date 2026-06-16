from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.audit import persist_required_domain_event
from app.api.auth import build_operator_audit_context, resolve_request_settings
from app.api.errors import operator_error_detail
from app.db.session import get_session
from app.reviewer.models import (
    DailyReviewResponse,
    OperationalQuestionReviewResponse,
    OperatorSummaryReview,
    PersistedReviewRecord,
    ReviewRecordSummary,
    RuntimeHealthReviewResponse,
    StrategyReviewResponse,
    TradePostMortemReviewResponse,
)
from app.reviewer.service import AIReviewerService

router = APIRouter(prefix="/reviews")


class OperationalQuestionRequest(BaseModel):
    question: str = Field(..., min_length=3)
    strategy_name: str | None = None
    actor_id: str = Field(default="operator")


def _persist_review_audit_event(
    *,
    session: Session,
    response: (
        OperatorSummaryReview
        | DailyReviewResponse
        | StrategyReviewResponse
        | RuntimeHealthReviewResponse
        | TradePostMortemReviewResponse
        | OperationalQuestionReviewResponse
    ),
    event_type: str,
    source: str,
    title: str,
    failure_detail: str,
    actor_id: str,
    strategy_name: str | None = None,
    instrument: str | None = None,
    trade_id: int | None = None,
    question: str | None = None,
) -> None:
    review_id = response.metadata.review_id
    review_type = response.metadata.review_type
    facts = response.facts
    routed_review_type = getattr(facts, "routed_review_type", None)
    answer_type = getattr(facts, "answer_type", None)
    payload_json = {
        "review_id": review_id,
        "review_type": review_type,
        "scope": response.metadata.scope,
        "previous_state": "NOT_PERSISTED",
        "new_state": "PERSISTED",
        "generation_mode": response.metadata.generation_mode,
        "llm_attempted": response.provenance.llm_attempted
        if response.provenance is not None
        else False,
        "llm_provider": response.provenance.llm_provider
        if response.provenance is not None
        else None,
        "llm_model": response.provenance.llm_model
        if response.provenance is not None
        else None,
        "routed_review_type": routed_review_type,
        "answer_type": answer_type,
    }
    if question is not None:
        payload_json["question"] = question

    persist_required_domain_event(
        session=session,
        failure_detail=failure_detail,
        event_type=event_type,
        category="review",
        source=source,
        title=title,
        message=f"Persisted {review_type} review record {review_id}.",
        correlation_id=f"review:{review_type}:{review_id}",
        strategy_name=strategy_name,
        instrument=instrument,
        trade_id=trade_id,
        actor_type="operator",
        actor_id=actor_id,
        payload_json=payload_json,
    )


def _strategy_name_from_review(
    response: StrategyReviewResponse | OperationalQuestionReviewResponse,
) -> str | None:
    scope_strategy = response.metadata.scope.get("strategy_name")
    return scope_strategy if isinstance(scope_strategy, str) else None


@router.get("/operator-summary", response_model=OperatorSummaryReview)
def get_operator_summary(
    persist: bool = Query(default=False),
    actor_id: str = "operator",
    session: Session = Depends(get_session),
) -> OperatorSummaryReview:
    response = AIReviewerService(session).get_operator_summary(persist=persist)
    if persist:
        _persist_review_audit_event(
            session=session,
            response=response,
            event_type="operator.review_persisted",
            source="api.reviews.operator_summary.persist",
            title="Operator summary review persisted",
            failure_detail="Review was persisted, but durable audit persistence failed.",
            actor_id=actor_id,
        )
    return response


@router.get("/daily", response_model=DailyReviewResponse)
def get_daily_review(
    review_date: date | None = Query(default=None, alias="date"),
    persist: bool = Query(default=False),
    actor_id: str = "operator",
    session: Session = Depends(get_session),
) -> DailyReviewResponse:
    response = AIReviewerService(session).get_daily_review(
        review_date or datetime.now(UTC).date(), persist=persist
    )
    if persist:
        _persist_review_audit_event(
            session=session,
            response=response,
            event_type="operator.review_persisted",
            source="api.reviews.daily.persist",
            title="Daily review persisted",
            failure_detail="Review was persisted, but durable audit persistence failed.",
            actor_id=actor_id,
        )
    return response


@router.get("/strategies/{strategy_name}", response_model=StrategyReviewResponse)
def get_strategy_review(
    strategy_name: str,
    days: int = Query(default=7, ge=1, le=90),
    persist: bool = Query(default=False),
    actor_id: str = "operator",
    session: Session = Depends(get_session),
) -> StrategyReviewResponse:
    response = AIReviewerService(session).get_strategy_review(
        strategy_name, period_days=days, persist=persist
    )
    if persist:
        _persist_review_audit_event(
            session=session,
            response=response,
            event_type="operator.review_persisted",
            source="api.reviews.strategies.persist",
            title="Strategy review persisted",
            failure_detail="Review was persisted, but durable audit persistence failed.",
            actor_id=actor_id,
            strategy_name=strategy_name,
        )
    return response


@router.get("/runtime-health", response_model=RuntimeHealthReviewResponse)
def get_runtime_health_review(
    hours: int = Query(default=24, ge=1, le=168),
    persist: bool = Query(default=False),
    actor_id: str = "operator",
    session: Session = Depends(get_session),
) -> RuntimeHealthReviewResponse:
    response = AIReviewerService(session).get_runtime_health_review(
        period_hours=hours, persist=persist
    )
    if persist:
        _persist_review_audit_event(
            session=session,
            response=response,
            event_type="operator.review_persisted",
            source="api.reviews.runtime_health.persist",
            title="Runtime-health review persisted",
            failure_detail="Review was persisted, but durable audit persistence failed.",
            actor_id=actor_id,
        )
    return response


@router.get(
    "/trades/{trade_id}/postmortem", response_model=TradePostMortemReviewResponse
)
def get_trade_postmortem(
    trade_id: int,
    persist: bool = Query(default=False),
    actor_id: str = "operator",
    session: Session = Depends(get_session),
) -> TradePostMortemReviewResponse:
    try:
        response = AIReviewerService(session).get_trade_postmortem(
            trade_id, persist=persist
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail=f"Trade '{trade_id}' was not found.",
            ),
        ) from exc
    if persist:
        _persist_review_audit_event(
            session=session,
            response=response,
            event_type="operator.review_persisted",
            source="api.reviews.trades.postmortem.persist",
            title="Trade postmortem review persisted",
            failure_detail="Review was persisted, but durable audit persistence failed.",
            actor_id=actor_id,
            strategy_name=response.facts.strategy_name,
            instrument=response.facts.instrument,
            trade_id=trade_id,
        )
    return response


@router.post("/questions", response_model=OperationalQuestionReviewResponse)
def answer_operational_question(
    payload: OperationalQuestionRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> OperationalQuestionReviewResponse:
    operator_context = build_operator_audit_context(
        request, settings=resolve_request_settings(request)
    )
    response = AIReviewerService(session).answer_operational_question(
        payload.question, strategy_name=payload.strategy_name
    )
    _persist_review_audit_event(
        session=session,
        response=response,
        event_type="operator.review_advisory_persisted",
        source="api.reviews.questions",
        title="Advisory review persisted",
        failure_detail="Advisory review was persisted, but durable audit persistence failed.",
        actor_id=str(operator_context["actor_id"]),
        strategy_name=_strategy_name_from_review(response),
        question=payload.question,
    )
    return response


@router.get("/history", response_model=list[ReviewRecordSummary])
def list_review_history(
    review_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[ReviewRecordSummary]:
    return AIReviewerService(session).list_review_history(
        review_type=review_type, limit=limit
    )


@router.get("/history/{review_id}", response_model=PersistedReviewRecord)
def get_review_record(
    review_id: int,
    session: Session = Depends(get_session),
) -> PersistedReviewRecord:
    try:
        return AIReviewerService(session).get_review_record(review_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail=f"Review '{review_id}' was not found.",
            ),
        ) from exc
