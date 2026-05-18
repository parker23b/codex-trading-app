from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.core.broker import BrokerError
from app.services.market_overview_service import MarketOverviewService
from app.services.chart_service import ChartService
from app.services.trade_service import TradeService
from app.services.watchlist_service import WatchlistService

router = APIRouter()


class BulkStrategyWatchlistRequest(BaseModel):
    instrument_ids: list[str] = Field(default_factory=list)


@router.get("/markets/overview")
def get_market_overview(
    category: str = Query(default="forex"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    service = MarketOverviewService(session)
    try:
        return service.get_category_overview(category)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except BrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to load market overview from broker: {exc}",
        ) from exc


@router.get("/markets/catalogue")
def get_market_catalogue(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).catalogue_response()


@router.get("/watchlist/shortlist")
def get_shortlist(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).shortlist_response()


@router.post("/watchlist/shortlist/{instrument_id}")
def add_shortlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    try:
        instrument = WatchlistService(session).set_shortlisted(instrument_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return {"status": "shortlisted", "instrument": instrument}


@router.delete("/watchlist/shortlist/{instrument_id}")
def remove_shortlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    WatchlistService(session).remove_shortlisted(instrument_id)
    return {"status": "removed", "instrument": instrument_id}


@router.post("/strategy-watchlist/bulk")
def add_strategy_watchlist_items(
    payload: BulkStrategyWatchlistRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return WatchlistService(session).add_to_strategy_watchlist(payload.instrument_ids)


@router.get("/strategy-watchlist")
def get_strategy_watchlist(
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return WatchlistService(session).strategy_watchlist_response(sync=False)


@router.delete("/strategy-watchlist/{instrument_id}")
def remove_strategy_watchlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    WatchlistService(session).remove_from_strategy_watchlist(instrument_id)
    return {"status": "removed", "instrument": instrument_id}


@router.get("/market-data/feed-state")
def get_feed_state(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).feed_state_response(sync=False)


@router.get("/market-data/feed-state/{instrument_id}")
def get_instrument_feed_state(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    return WatchlistService(session).feed_state_for_instrument(instrument_id)


@router.get("/live/instruments/{instrument_id}/chart")
def get_live_instrument_chart(
    instrument_id: str,
    timeframe: str = Query(default="1m"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return ChartService(TradeService(session)).get_live_instrument_chart(
        instrument_id, timeframe=timeframe
    )
