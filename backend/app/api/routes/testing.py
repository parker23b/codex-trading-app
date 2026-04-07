from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.services.history_reset_service import HistoryResetService

router = APIRouter(prefix="/testing")


class ResetHistoryResponse(BaseModel):
    status: str
    summary: dict[str, int]


@router.post("/reset-history", response_model=ResetHistoryResponse)
def reset_history(session: Session = Depends(get_session)) -> ResetHistoryResponse:
    summary = HistoryResetService(session).clear_test_history()
    return ResetHistoryResponse(status="ok", summary=summary.model_dump())
