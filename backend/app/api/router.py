from fastapi import APIRouter

from app.api.routes import allocation, aimee, ai_reviewer, broker, charts, control_plane, coverage, dashboard, events, executions, health, market_status, markets, positions, strategies, system, testing, trades

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(system.router, tags=["system"])
api_router.include_router(broker.router, tags=["broker"])
api_router.include_router(control_plane.router, tags=["control-plane"])
api_router.include_router(coverage.router, tags=["coverage"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(allocation.router, tags=["allocation"])
api_router.include_router(market_status.router, tags=["market-status"])
api_router.include_router(markets.router, tags=["markets"])
api_router.include_router(charts.router, tags=["charts"])
api_router.include_router(positions.router, tags=["positions"])
api_router.include_router(executions.router, tags=["executions"])
api_router.include_router(trades.router, prefix="/trades", tags=["trades"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(aimee.router, tags=["aimee"])
api_router.include_router(ai_reviewer.router, tags=["ai-reviewer"])
api_router.include_router(testing.router, tags=["testing"])
