from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.audit import persist_required_domain_event
from app.api.contracts.markets import (
    FeedStateInstrumentResponse,
    FeedStateResponse,
    LiveChartResponse,
    MarketCategoryOverviewResponse,
    MarketCatalogueResponse,
    ShortlistMutationResponse,
    ShortlistResponse,
    StrategyWatchlistBulkResponse,
    StrategyWatchlistMutationResponse,
    StrategyWatchlistResponse,
)
from app.api.errors import operator_error_detail
from app.db.session import get_session
from app.core.broker import BrokerError
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry
from app.services.market_overview_service import MarketOverviewService
from app.services.chart_service import ChartService
from app.services.trade_service import TradeService
from app.services.watchlist_service import WatchlistService

router = APIRouter()


class BulkStrategyWatchlistRequest(BaseModel):
    instrument_ids: list[str] = Field(default_factory=list)


def _shortlist_entry(
    session: Session, instrument_id: str
) -> OperatorShortlistEntry | None:
    return session.exec(
        select(OperatorShortlistEntry).where(
            OperatorShortlistEntry.instrument == instrument_id
        )
    ).first()


def _watchlist_entry(session: Session, instrument_id: str) -> WatchlistEntry | None:
    return session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == instrument_id)
    ).first()


def _strategy_watchlist_state(entry: WatchlistEntry | None) -> str:
    if entry is None:
        return "NOT_IN_STRATEGY_WATCHLIST"
    return str(entry.status)


@router.get("/markets/overview", response_model=MarketCategoryOverviewResponse)
def get_market_overview(
    category: str = Query(default="forex"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    service = MarketOverviewService(session)
    try:
        return service.get_category_overview(category)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=operator_error_detail(
                exc,
                default_detail="Invalid market category.",
            ),
        ) from exc
    except BrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=operator_error_detail(
                exc,
                default_detail="Unable to load market overview from broker.",
                prefix="Unable to load market overview from broker",
            ),
        ) from exc


@router.get("/markets/catalogue", response_model=MarketCatalogueResponse)
def get_market_catalogue(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).catalogue_response()


@router.get("/watchlist/shortlist", response_model=ShortlistResponse)
def get_shortlist(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).shortlist_response()


@router.post(
    "/watchlist/shortlist/{instrument_id}", response_model=ShortlistMutationResponse
)
def add_shortlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    previous_entry = _shortlist_entry(session, instrument_id)
    previous_state = "SHORTLISTED" if previous_entry is not None else "NOT_SHORTLISTED"
    try:
        instrument = WatchlistService(session).set_shortlisted(instrument_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=operator_error_detail(
                exc,
                default_detail=f"Instrument '{instrument_id}' was not found.",
            ),
        ) from exc
    entry = _shortlist_entry(session, instrument_id)
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Shortlist item was added, but durable audit persistence failed."
        ),
        event_type="operator.shortlist_item_added",
        category="watchlist",
        source="api.markets.shortlist.add",
        title="Shortlist item added",
        message=f"{instrument_id} was added to the operator shortlist.",
        instrument=instrument_id,
        actor_type="operator",
        actor_id="api",
        payload_json={
            "instrument": instrument_id,
            "previous_state": previous_state,
            "new_state": "SHORTLISTED",
            "shortlist_entry_id": entry.id if entry is not None else None,
        },
    )
    return {"status": "shortlisted", "instrument": instrument}


@router.delete(
    "/watchlist/shortlist/{instrument_id}",
    response_model=ShortlistMutationResponse,
)
def remove_shortlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    previous_entry = _shortlist_entry(session, instrument_id)
    previous_state = "SHORTLISTED" if previous_entry is not None else "NOT_SHORTLISTED"
    previous_entry_id = previous_entry.id if previous_entry is not None else None
    WatchlistService(session).remove_shortlisted(instrument_id)
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Shortlist item was removed, but durable audit persistence failed."
        ),
        event_type="operator.shortlist_item_removed",
        category="watchlist",
        source="api.markets.shortlist.remove",
        title="Shortlist item removed",
        message=f"{instrument_id} was removed from the operator shortlist.",
        instrument=instrument_id,
        actor_type="operator",
        actor_id="api",
        payload_json={
            "instrument": instrument_id,
            "previous_state": previous_state,
            "new_state": "NOT_SHORTLISTED",
            "shortlist_entry_id": previous_entry_id,
        },
    )
    return {"status": "removed", "instrument": instrument_id}


@router.post("/strategy-watchlist/bulk", response_model=StrategyWatchlistBulkResponse)
def add_strategy_watchlist_items(
    payload: BulkStrategyWatchlistRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    unique_instruments = list(dict.fromkeys(payload.instrument_ids))
    previous_entries = {
        instrument_id: _watchlist_entry(session, instrument_id)
        for instrument_id in unique_instruments
    }
    previous_states = {
        instrument_id: _strategy_watchlist_state(entry)
        for instrument_id, entry in previous_entries.items()
    }
    response = WatchlistService(session).add_to_strategy_watchlist(
        payload.instrument_ids
    )
    new_entries = {
        instrument_id: _watchlist_entry(session, instrument_id)
        for instrument_id in unique_instruments
    }
    new_states = {
        instrument_id: _strategy_watchlist_state(entry)
        for instrument_id, entry in new_entries.items()
    }
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy watchlist bulk add completed, but durable audit persistence failed."
        ),
        event_type="operator.strategy_watchlist_bulk_added",
        category="watchlist",
        source="api.markets.strategy_watchlist.bulk_add",
        title="Strategy watchlist bulk add completed",
        message="Operator strategy-watchlist bulk add request completed.",
        actor_type="operator",
        actor_id="api",
        payload_json={
            "requested_instrument_ids": unique_instruments,
            "previous_states": previous_states,
            "new_states": new_states,
            "watchlist_entry_ids": {
                instrument_id: entry.id if entry is not None else None
                for instrument_id, entry in new_entries.items()
            },
            "added": response.get("added", []),
            "skipped": response.get("skipped", []),
            "added_count": len(response.get("added", [])),
            "skipped_count": len(response.get("skipped", [])),
            "limit": response.get("limit"),
        },
    )
    return response


@router.get("/strategy-watchlist", response_model=StrategyWatchlistResponse)
def get_strategy_watchlist(
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return WatchlistService(session).strategy_watchlist_response(sync=False)


@router.delete(
    "/strategy-watchlist/{instrument_id}",
    response_model=StrategyWatchlistMutationResponse,
)
def remove_strategy_watchlist_item(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    previous_entry = _watchlist_entry(session, instrument_id)
    previous_state = _strategy_watchlist_state(previous_entry)
    previous_entry_id = previous_entry.id if previous_entry is not None else None
    WatchlistService(session).remove_from_strategy_watchlist(instrument_id)
    new_entry = _watchlist_entry(session, instrument_id)
    persist_required_domain_event(
        session=session,
        failure_detail=(
            "Strategy watchlist item was removed, but durable audit persistence failed."
        ),
        event_type="operator.strategy_watchlist_item_removed",
        category="watchlist",
        source="api.markets.strategy_watchlist.remove",
        title="Strategy watchlist item removed",
        message=f"{instrument_id} was removed from the strategy watchlist.",
        instrument=instrument_id,
        actor_type="operator",
        actor_id="api",
        payload_json={
            "instrument": instrument_id,
            "previous_state": previous_state,
            "new_state": _strategy_watchlist_state(new_entry),
            "watchlist_entry_id": previous_entry_id
            or (new_entry.id if new_entry is not None else None),
        },
    )
    return {"status": "removed", "instrument": instrument_id}


@router.get("/market-data/feed-state", response_model=FeedStateResponse)
def get_feed_state(session: Session = Depends(get_session)) -> dict[str, object]:
    return WatchlistService(session).feed_state_response(sync=False)


@router.get(
    "/market-data/feed-state/{instrument_id}",
    response_model=FeedStateInstrumentResponse,
)
def get_instrument_feed_state(
    instrument_id: str, session: Session = Depends(get_session)
) -> dict[str, object]:
    return WatchlistService(session).feed_state_for_instrument(instrument_id)


@router.get("/live/instruments/{instrument_id}/chart", response_model=LiveChartResponse)
def get_live_instrument_chart(
    instrument_id: str,
    timeframe: str = Query(default="1m"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return ChartService(TradeService(session)).get_live_instrument_chart(
        instrument_id, timeframe=timeframe
    )
