from __future__ import annotations

from app.services.dashboard_service import DashboardService
from app.services.trade_service import TradeService


class ChartService:
    """Read-only chart projections built from the same aggregated trade/position state."""

    def __init__(self, trade_service: TradeService):
        self.dashboard_service = DashboardService(trade_service)

    def get_equity_chart(self) -> list[dict[str, float | str]]:
        return self.dashboard_service.build_equity_curve()

    def get_drawdown_chart(self) -> list[dict[str, float | str]]:
        return self.dashboard_service.build_drawdown_series()

    def get_risk_allocation_chart(self) -> dict[str, object]:
        return self.dashboard_service.build_risk_allocation()
