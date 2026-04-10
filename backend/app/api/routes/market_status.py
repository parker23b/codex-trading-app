from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.market_status_service import MarketStatus, get_market_status_service

router = APIRouter()


class MarketStatusResponse(BaseModel):
    instrument: str
    is_ok: bool
    market_open: bool
    tradable: bool
    quote_fresh: bool
    spread_ok: bool
    session_valid: bool
    dealing_allowed: bool
    last_price_age_ms: float
    spread: float | None
    reason: str | None


@router.get("/market-status/{instrument}", response_model=MarketStatusResponse)
def get_market_status(instrument: str, at: datetime | None = Query(default=None)) -> MarketStatusResponse:
    status = get_market_status_service().get_status(instrument, now=at)
    return MarketStatusResponse(**status.model_dump())
