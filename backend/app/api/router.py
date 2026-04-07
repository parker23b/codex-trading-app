from fastapi import APIRouter

from app.api.routes import ai_reviewer, broker, charts, dashboard, executions, health, markets, positions, strategies, trades

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(broker.router, tags=["broker"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(markets.router, tags=["markets"])
api_router.include_router(charts.router, tags=["charts"])
api_router.include_router(positions.router, tags=["positions"])
api_router.include_router(executions.router, tags=["executions"])
api_router.include_router(trades.router, prefix="/trades", tags=["trades"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(ai_reviewer.router, tags=["ai-reviewer"])
