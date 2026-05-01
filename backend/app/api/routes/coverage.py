from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.services.coverage_service import CoverageService

router = APIRouter()


class CoverageSummaryResponse(BaseModel):
    streaming: dict[str, object]
    tier2: dict[str, object]
    promotions: dict[str, object]
    trade_allocator: dict[str, object]


@router.get("/coverage/summary", response_model=CoverageSummaryResponse)
def get_coverage_summary(
    session: Session = Depends(get_session),
) -> CoverageSummaryResponse:
    return CoverageSummaryResponse(**CoverageService(session).get_summary())
