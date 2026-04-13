from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.services.broker_service import BrokerService
from app.services.dashboard_service import DashboardService
from app.services.trade_service import TradeService

router = APIRouter()


@router.get("/dashboard")
def get_dashboard(session: Session = Depends(get_session)) -> dict[str, object]:
    """Return dashboard KPIs.

    This route reconciles broker positions before computing the response and is
    therefore not safe for passive AIMEE snapshot reads.
    """
    BrokerService().reconcile_positions(session)
    return DashboardService(TradeService(session)).get_dashboard()
