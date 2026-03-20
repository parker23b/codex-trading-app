from fastapi import APIRouter

from app.api.routes import broker, charts, dashboard, health, positions, strategies, trades

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(broker.router, tags=["broker"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(charts.router, tags=["charts"])
api_router.include_router(positions.router, tags=["positions"])
api_router.include_router(trades.router, prefix="/trades", tags=["trades"])
api_router.include_router(strategies.router, tags=["strategies"])
