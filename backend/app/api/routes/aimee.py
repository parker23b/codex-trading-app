from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.contracts.aimee import AimeeSnapshotResponse
from app.db.session import get_session
from app.services.aimee_read_service import AimeeReadService

router = APIRouter(prefix="/aimee")


@router.get("/snapshot", response_model=AimeeSnapshotResponse)
def get_snapshot(session: Session = Depends(get_session)) -> AimeeSnapshotResponse:
    """Return AIMEE's passive read snapshot without operational side effects."""

    return AimeeSnapshotResponse.model_validate(
        AimeeReadService(session).get_snapshot()
    )
