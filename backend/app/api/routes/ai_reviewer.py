from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

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


@router.get("/operator-summary", response_model=OperatorSummaryReview)
def get_operator_summary(
    persist: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> OperatorSummaryReview:
    return AIReviewerService(session).get_operator_summary(persist=persist)


@router.get("/daily", response_model=DailyReviewResponse)
def get_daily_review(
    review_date: date | None = Query(default=None, alias="date"),
    persist: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> DailyReviewResponse:
    return AIReviewerService(session).get_daily_review(
        review_date or datetime.now(UTC).date(), persist=persist
    )


@router.get("/strategies/{strategy_name}", response_model=StrategyReviewResponse)
def get_strategy_review(
    strategy_name: str,
    days: int = Query(default=7, ge=1, le=90),
    persist: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> StrategyReviewResponse:
    return AIReviewerService(session).get_strategy_review(
        strategy_name, period_days=days, persist=persist
    )


@router.get("/runtime-health", response_model=RuntimeHealthReviewResponse)
def get_runtime_health_review(
    hours: int = Query(default=24, ge=1, le=168),
    persist: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> RuntimeHealthReviewResponse:
    return AIReviewerService(session).get_runtime_health_review(
        period_hours=hours, persist=persist
    )


@router.get(
    "/trades/{trade_id}/postmortem", response_model=TradePostMortemReviewResponse
)
def get_trade_postmortem(
    trade_id: int,
    persist: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> TradePostMortemReviewResponse:
    try:
        return AIReviewerService(session).get_trade_postmortem(
            trade_id, persist=persist
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/questions", response_model=OperationalQuestionReviewResponse)
def answer_operational_question(
    payload: OperationalQuestionRequest,
    session: Session = Depends(get_session),
) -> OperationalQuestionReviewResponse:
    return AIReviewerService(session).answer_operational_question(
        payload.question, strategy_name=payload.strategy_name
    )


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
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
