from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.services.aimee_read_service import AimeeReadService

router = APIRouter(prefix="/aimee")


@router.get("/snapshot")
def get_snapshot(session: Session = Depends(get_session)) -> dict[str, object]:
    """Return AIMEE's passive read snapshot without operational side effects."""

    return AimeeReadService(session).get_snapshot()
