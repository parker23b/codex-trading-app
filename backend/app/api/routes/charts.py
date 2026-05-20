from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.contracts.charts import RiskAllocationChartResponse
from app.db.session import get_session
from app.services.chart_service import ChartService
from app.services.trade_service import TradeService

router = APIRouter(prefix="/charts")


@router.get("/equity")
def get_equity_chart(
    session: Session = Depends(get_session),
) -> list[dict[str, float | str]]:
    return ChartService(TradeService(session)).get_equity_chart()


@router.get("/drawdown")
def get_drawdown_chart(
    session: Session = Depends(get_session),
) -> list[dict[str, float | str]]:
    return ChartService(TradeService(session)).get_drawdown_chart()


@router.get("/risk-allocation", response_model=RiskAllocationChartResponse)
def get_risk_allocation_chart(
    session: Session = Depends(get_session),
) -> RiskAllocationChartResponse:
    return ChartService(TradeService(session)).get_risk_allocation_chart()
