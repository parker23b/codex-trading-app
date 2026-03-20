from fastapi import APIRouter

from app.api.routes import health, strategies, trades

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(trades.router, prefix="/trades", tags=["trades"])
api_router.include_router(strategies.router, tags=["strategies"])
