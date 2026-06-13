from fastapi import APIRouter

from app.api.routes import (
    allocation,
    aimee,
    ai_reviewer,
    backtesting,
    broker,
    charts,
    control_plane,
    coverage,
    dashboard,
    events,
    executions,
    health,
    market_status,
    markets,
    positions,
    strategies,
    system,
    testing,
    trades,
)
from app.core.config import Settings, get_settings


def build_api_router(settings: Settings | None = None) -> APIRouter:
    active_settings = settings or get_settings()
    router = APIRouter()
    router.include_router(health.router, tags=["health"])
    router.include_router(system.router, tags=["system"])
    router.include_router(broker.router, tags=["broker"])
    router.include_router(control_plane.router, tags=["control-plane"])
    router.include_router(coverage.router, tags=["coverage"])
    router.include_router(dashboard.router, tags=["dashboard"])
    router.include_router(events.router, tags=["events"])
    router.include_router(allocation.router, tags=["allocation"])
    router.include_router(backtesting.router, tags=["backtesting"])
    router.include_router(market_status.router, tags=["market-status"])
    router.include_router(markets.router, tags=["markets"])
    router.include_router(charts.router, tags=["charts"])
    router.include_router(positions.router, tags=["positions"])
    router.include_router(executions.router, tags=["executions"])
    router.include_router(trades.router, prefix="/trades", tags=["trades"])
    router.include_router(strategies.router, tags=["strategies"])
    router.include_router(aimee.router, tags=["aimee"])
    router.include_router(ai_reviewer.router, tags=["ai-reviewer"])
    if active_settings.testing_routes_can_register:
        router.include_router(testing.router, tags=["testing"])
    return router


api_router = build_api_router()
