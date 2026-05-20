from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.contracts.dashboard import DashboardSnapshotResponse
from app.db.session import get_session
from app.services.dashboard_service import DashboardService
from app.services.trade_service import TradeService

router = APIRouter()


@router.get("/dashboard", response_model=DashboardSnapshotResponse)
def get_dashboard(session: Session = Depends(get_session)) -> DashboardSnapshotResponse:
    """Return dashboard KPIs from persisted/runtime state only.

    Passive reads must not force live broker reconciliation because the UI may
    poll this route continuously on an operator screen.
    """
    return DashboardSnapshotResponse(
        **DashboardService(TradeService(session)).get_dashboard()
    )
