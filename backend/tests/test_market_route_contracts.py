from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.runtime import runtime_manager
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry
from app.services.ig_streaming_service import StreamHealthState


EURUSD = "CS.D.EURUSD.CFD.IP"
GBPUSD = "CS.D.GBPUSD.CFD.IP"
UNKNOWN = "CS.D.UNKNOWN.CFD.IP"


class _StubStreamingService:
    def __init__(self, health: StreamHealthState):
        self._health = health

    def get_health(self) -> StreamHealthState:
        return self._health

    def get_last_tick_at(self, instrument: str):
        return (self._health.last_tick_at_by_instrument or {}).get(instrument)


def _seed_market_contract_state(session) -> WatchlistEntry:
    shortlist = OperatorShortlistEntry(
        instrument=EURUSD,
        actor_id="operator",
        created_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    )
    entry = WatchlistEntry(
        instrument=EURUSD,
        tier="TIER1",
        status="ACTIVE",
        asset_class="forex",
        pinned=False,
        reason="operator_strategy_watchlist",
        priority_score=60.0,
        requested_frequency="SECOND",
        assigned_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        last_streamed_at=datetime(2026, 5, 20, 9, 5, tzinfo=UTC),
        last_refreshed_at=datetime(2026, 5, 20, 9, 6, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 9, 10, tzinfo=UTC),
    )
    session.add(shortlist)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def _watchlist_row_state(
    session, instrument: str
) -> tuple[str, datetime | None, datetime]:
    entry = session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == instrument)
    ).one()
    return entry.status, entry.last_streamed_at, entry.updated_at


def test_market_family_openapi_contracts_are_explicit(client_factory):
    with client_factory() as client:
        schema = client.app.openapi()

    route_expectations = {
        "/markets/overview": "MarketCategoryOverviewResponse",
        "/markets/catalogue": "MarketCatalogueResponse",
        "/watchlist/shortlist": "ShortlistResponse",
        "/strategy-watchlist": "StrategyWatchlistResponse",
        "/market-data/feed-state": "FeedStateResponse",
        "/market-data/feed-state/{instrument_id}": "FeedStateInstrumentResponse",
        "/live/instruments/{instrument_id}/chart": "LiveChartResponse",
    }
    for path, component_name in route_expectations.items():
        response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{component_name}"}

    assert set(
        schema["components"]["schemas"]["FeedStateInstrumentResponse"]["properties"]
    ) >= {
        "instrument",
        "stream_status",
        "stream_reason",
        "price_source",
        "market_status",
        "market_error",
        "entry_eligibility",
        "entry_eligibility_reason",
        "last_tick_at",
        "last_tick_age_ms",
        "watchlist_entry",
    }
    assert set(
        schema["components"]["schemas"]["StrategyWatchlistResponse"]["properties"]
    ) >= {
        "generated_at",
        "limit",
        "active_count",
        "normal_count",
        "streaming_count",
        "protective_count",
        "cap_exceeded_by_protective_coverage",
        "instruments",
    }


def test_market_catalogue_and_shortlist_routes_preserve_passive_state_and_shape(
    session, client_factory
):
    entry = _seed_market_contract_state(session)
    before = _watchlist_row_state(session, entry.instrument)

    with client_factory() as client:
        catalogue_response = client.get("/markets/catalogue")
        shortlist_response = client.get("/watchlist/shortlist")

    assert catalogue_response.status_code == 200, catalogue_response.text
    assert shortlist_response.status_code == 200, shortlist_response.text

    catalogue = catalogue_response.json()
    shortlist = shortlist_response.json()
    catalogue_row = next(
        row for row in catalogue["instruments"] if row["instrument"] == entry.instrument
    )

    assert set(catalogue) == {"generated_at", "instruments", "summary"}
    assert set(shortlist) == {"generated_at", "instruments", "count"}
    assert catalogue_row["shortlisted"] is True
    assert catalogue_row["in_strategy_watchlist"] is True
    assert isinstance(catalogue_row["streaming_now"], bool)
    assert shortlist["count"] == 1
    assert shortlist["instruments"][0]["instrument"] == entry.instrument
    assert shortlist["instruments"][0]["shortlisted_at"] is not None
    assert shortlist["instruments"][0]["streaming_now"] is False
    assert _watchlist_row_state(session, entry.instrument) == before


def test_strategy_watchlist_and_feed_state_routes_preserve_passive_state_and_freshness_fields(
    session, client_factory, monkeypatch, fixed_now
):
    entry = _seed_market_contract_state(session)
    runtime_manager.start("smoke_test_hold", entry.instrument)
    runtime_manager.last_price_updated_at[entry.instrument] = fixed_now
    before = _watchlist_row_state(session, entry.instrument)

    health = StreamHealthState(
        enabled=True,
        connected=True,
        subscribed_instruments=(entry.instrument,),
        desired_instruments=(entry.instrument, GBPUSD),
        capped_instruments=(GBPUSD,),
        last_tick_at_by_instrument={
            entry.instrument: fixed_now - timedelta(seconds=120),
        },
        dependency_ready=True,
    )
    monkeypatch.setattr(
        "app.services.ig_streaming_service.get_ig_streaming_service",
        lambda: _StubStreamingService(health),
    )

    with client_factory() as client:
        watchlist_response = client.get("/strategy-watchlist")
        feed_state_response = client.get("/market-data/feed-state")
        instrument_response = client.get(f"/market-data/feed-state/{entry.instrument}")

    assert watchlist_response.status_code == 200, watchlist_response.text
    assert feed_state_response.status_code == 200, feed_state_response.text
    assert instrument_response.status_code == 200, instrument_response.text

    watchlist = watchlist_response.json()
    feed_state = feed_state_response.json()
    instrument = instrument_response.json()

    assert watchlist["active_count"] == 1
    assert watchlist["normal_count"] == 1
    assert watchlist["streaming_count"] == 0
    assert (
        watchlist["instruments"][0]["reason_detail"]["code"]
        == "operator_strategy_watchlist"
    )

    assert feed_state["instruments"][0]["instrument"] == entry.instrument
    assert (
        feed_state["instruments"][0]["watchlist_entry"]["instrument"]
        == entry.instrument
    )
    assert instrument["instrument"] == entry.instrument
    assert instrument["stream_status"] == "stale"
    assert instrument["price_source"] == "STALE"
    assert instrument["stream_reason"]["code"] == "stale_stream"
    assert instrument["entry_eligibility_reason"]["code"] == "stale_stream"
    assert instrument["active_strategy_runtime_count"] == 1
    assert instrument["last_tick_at"] is not None
    assert instrument["last_tick_age_ms"] is not None
    assert instrument["market_status"]["last_price_age_ms"] >= 0
    assert instrument["watchlist_entry"] is None
    assert _watchlist_row_state(session, entry.instrument) == before


def test_feed_state_and_chart_routes_surface_unavailable_or_degraded_truth(
    session, client_factory, monkeypatch
):
    monkeypatch.setattr(
        "app.services.market_status_service.get_market_status_service",
        lambda: type(
            "BrokenMarketStatusService",
            (),
            {
                "get_status": staticmethod(
                    lambda instrument: (_ for _ in ()).throw(
                        RuntimeError(f"market-status unavailable for {instrument}")
                    )
                )
            },
        )(),
    )

    with client_factory() as client:
        feed_state_response = client.get(f"/market-data/feed-state/{EURUSD}")
        chart_response = client.get(f"/live/instruments/{UNKNOWN}/chart")

    assert feed_state_response.status_code == 200, feed_state_response.text
    assert chart_response.status_code == 200, chart_response.text

    feed_state = feed_state_response.json()
    chart = chart_response.json()

    assert feed_state["market_status"] is None
    assert feed_state["market_error"] == f"market-status unavailable for {EURUSD}"
    assert feed_state["price_source"] == "UNAVAILABLE"
    assert feed_state["stream_status"] == "inactive"
    assert feed_state["entry_eligibility_reason"]["code"] in {
        "market_readiness_blocked",
        "no_active_strategy_runtime",
    }

    assert chart["source"] == "UNAVAILABLE"
    assert chart["data_state"] == "UNSUPPORTED"
    assert chart["reason_detail"]["code"] == "unsupported_chart_instrument"
    assert chart["feed_state"]["market_status"] is None
    assert (
        chart["feed_state"]["market_error"]
        == f"market-status unavailable for {UNKNOWN}"
    )
    assert chart["feed_state"]["price_source"] == "UNAVAILABLE"
    assert chart["feed_state"]["stream_status"] == "inactive"
