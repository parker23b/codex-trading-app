from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.api.routes.markets import get_market_catalogue
from app.core.runtime import runtime_manager
from app.models.trade import Position
from app.models.watchlist import WatchlistEntry, WatchlistStatus
from app.services.chart_service import ChartService
from app.services.ig_streaming_service import StreamHealthState
from app.services.trade_service import TradeService
from app.services.watchlist_service import WatchlistService


EURUSD = "CS.D.EURUSD.CFD.IP"
GBPUSD = "CS.D.GBPUSD.CFD.IP"
USDJPY = "CS.D.USDJPY.CFD.IP"
AUDUSD = "CS.D.AUDUSD.CFD.IP"
USDCHF = "CS.D.USDCHF.CFD.IP"
USDCAD = "CS.D.USDCAD.CFD.IP"
EURGBP = "CS.D.EURGBP.CFD.IP"
EURJPY = "CS.D.EURJPY.CFD.IP"
GBPJPY = "CS.D.GBPJPY.CFD.IP"
EURAUD = "CS.D.EURAUD.CFD.IP"
UNKNOWN = "CS.D.UNKNOWN.CFD.IP"
SUPPORTED_NINE = [
    EURUSD,
    GBPUSD,
    USDJPY,
    AUDUSD,
    USDCHF,
    USDCAD,
    EURGBP,
    EURJPY,
    GBPJPY,
]


def test_catalogue_endpoint_returns_supported_instruments(session):
    payload = get_market_catalogue(session)
    instruments = {row["instrument"] for row in payload["instruments"]}
    assert EURUSD in instruments
    assert payload["summary"]["total_count"] >= len(SUPPORTED_NINE)


def test_shortlist_add_remove_duplicate_and_unknown_instrument(session):
    service = WatchlistService(session)

    first = service.set_shortlisted(EURUSD)
    second = service.set_shortlisted(EURUSD)

    assert first["shortlisted"] is True
    assert second["shortlisted"] is True
    assert service.shortlist_response()["count"] == 1

    service.remove_shortlisted(EURUSD)
    assert service.shortlist_response()["count"] == 0

    try:
        service.set_shortlisted(UNKNOWN)
    except ValueError as exc:
        assert "Unknown instrument" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Unknown instruments must be rejected.")


def test_shortlist_does_not_imply_streaming_or_trading(session):
    service = WatchlistService(session)
    service.set_shortlisted(EURUSD)

    row = service.shortlist_response()["instruments"][0]
    assert row["shortlisted"] is True
    assert row["in_strategy_watchlist"] is False
    assert row["streaming_now"] is False
    assert service.strategy_watchlist_response()["active_count"] == 0


def test_strategy_watchlist_add_remove_and_evaluation_eligibility(session):
    service = WatchlistService(session)

    result = service.add_to_strategy_watchlist([EURUSD])
    assert result["limit"] == 8
    assert result["added"][0]["reason_detail"]["code"] == "added_to_strategy_watchlist"

    watchlist = service.strategy_watchlist_response()
    assert watchlist["limit"] == 8
    assert watchlist["normal_count"] == 1
    assert watchlist["instruments"][0]["instrument"] == EURUSD
    assert watchlist["instruments"][0]["protective"] is False

    runtime_manager.start("smoke_test_hold", EURUSD)
    runtime_manager.last_price_updated_at[EURUSD] = datetime.now(UTC)
    feed_state = service.feed_state_for_instrument(EURUSD)
    assert feed_state["watchlist_entry"] is None
    assert feed_state["active_strategy_runtime_count"] == 1

    service.remove_from_strategy_watchlist(EURUSD)
    entry = session.exec(
        select(WatchlistEntry).where(WatchlistEntry.instrument == EURUSD)
    ).one()
    assert entry.status == WatchlistStatus.COOLDOWN.value


def test_bulk_strategy_watchlist_add_enforces_cap_at_eight_and_returns_structured_reasons(
    session,
):
    service = WatchlistService(session)

    result = service.add_to_strategy_watchlist([*SUPPORTED_NINE])

    assert [item["instrument"] for item in result["added"]] == SUPPORTED_NINE[:8]
    assert result["skipped"] == [
        {
            "instrument": GBPJPY,
            "reason": "Strategy watchlist limit reached",
            "reason_detail": {
                "code": "strategy_watchlist_limit_reached",
                "label": "Strategy watchlist limit reached",
                "operator_action": "Remove another operator-added instrument first. The current phase cap is 8 instruments.",
            },
        }
    ]
    response = service.strategy_watchlist_response()
    assert response["limit"] == 8
    assert response["normal_count"] == 8


def test_partial_bulk_add_reports_existing_and_skipped_reasons(session):
    service = WatchlistService(session)
    service.add_to_strategy_watchlist(SUPPORTED_NINE[:8])

    result = service.add_to_strategy_watchlist([EURUSD, EURAUD])

    assert (
        result["added"][0]["reason_detail"]["code"] == "already_in_strategy_watchlist"
    )
    assert (
        result["skipped"][0]["reason_detail"]["code"]
        == "strategy_watchlist_limit_reached"
    )


def test_protective_open_position_coverage_can_exceed_normal_cap(session, fixed_now):
    service = WatchlistService(session)
    service.add_to_strategy_watchlist(SUPPORTED_NINE[:8])
    session.add(
        Position(
            strategy_name="smoke_test_hold",
            broker_reference="protective-open-1",
            instrument=EURAUD,
            direction="BUY",
            size=0.2,
            open_price=1.64,
            open_time=fixed_now,
            current_price=1.65,
            risk_percent=0.2,
            account_type="DEMO",
            is_open=True,
        )
    )
    session.commit()

    watchlist = service.strategy_watchlist_response()
    protective = next(
        row for row in watchlist["instruments"] if row["instrument"] == EURAUD
    )

    assert watchlist["limit"] == 8
    assert watchlist["normal_count"] == 8
    assert watchlist["active_count"] == 9
    assert watchlist["protective_count"] == 1
    assert watchlist["cap_exceeded_by_protective_coverage"] is True
    assert protective["protective"] is True

    plan = service.get_streaming_plan()
    assert len([item for item in plan.instruments if item != EURAUD]) == 8
    assert EURAUD in plan.pinned_instruments


class _StubStreamingService:
    def __init__(self, health: StreamHealthState):
        self.health = health

    def get_health(self) -> StreamHealthState:
        return self.health


def test_feed_state_projection_covers_desired_streaming_capped_stale_no_runtime_and_unavailable(
    session, monkeypatch, fixed_now
):
    desired = EURUSD
    streaming = GBPUSD
    capped = USDJPY
    stale = AUDUSD
    no_runtime = USDCHF
    unavailable = UNKNOWN
    for instrument in [desired, streaming, capped, stale]:
        runtime_manager.start("smoke_test_hold", instrument)
        runtime_manager.last_price_updated_at[instrument] = fixed_now
    runtime_manager.last_price_updated_at[no_runtime] = fixed_now
    health = StreamHealthState(
        enabled=True,
        connected=True,
        subscribed_instruments=(streaming, stale),
        desired_instruments=(desired, streaming, stale),
        capped_instruments=(capped,),
        last_tick_at_by_instrument={
            streaming: datetime.now(UTC),
            stale: datetime.now(UTC) - timedelta(seconds=120),
        },
        dependency_ready=True,
    )
    monkeypatch.setattr(
        "app.services.ig_streaming_service.get_ig_streaming_service",
        lambda: _StubStreamingService(health),
    )
    service = WatchlistService(session)
    service.settings.ig_streaming_stale_after_seconds = 20

    assert service.feed_state_for_instrument(desired)["stream_status"] == "desired"
    streamed = service.feed_state_for_instrument(streaming)
    assert streamed["stream_status"] == "streaming"
    assert streamed["price_source"] == "STREAM"
    assert service.feed_state_for_instrument(capped)["stream_status"] == "capped"
    stale_state = service.feed_state_for_instrument(stale)
    assert stale_state["stream_status"] == "stale"
    assert stale_state["price_source"] == "STALE"
    assert stale_state["entry_eligibility_reason"]["code"] == "stale_stream"
    no_runtime_state = service.feed_state_for_instrument(no_runtime)
    assert (
        no_runtime_state["entry_eligibility_reason"]["code"]
        == "no_active_strategy_runtime"
    )
    assert no_runtime_state["strategies_may_evaluate"] is False
    unavailable_state = service.feed_state_for_instrument(unavailable)
    assert unavailable_state["stream_status"] == "inactive"
    assert unavailable_state["price_source"] == "UNAVAILABLE"


def test_live_chart_returns_explicit_unsupported_response(session):
    chart = ChartService(TradeService(session)).get_live_instrument_chart(UNKNOWN)

    assert chart["candles"] == []
    assert chart["data_state"] == "UNSUPPORTED"
    assert chart["source"] == "UNAVAILABLE"
    assert chart["reason_detail"]["code"] == "unsupported_chart_instrument"


def test_live_chart_handles_empty_candles_no_markers_and_broker_neutral_sources(
    session, monkeypatch, broker
):
    def empty_candles(
        _instrument: str, *, timeframe: str = "1m", num_points: int = 180
    ):
        return []

    broker.get_historical_candles = empty_candles  # type: ignore[attr-defined]
    monkeypatch.setattr("app.services.chart_service.get_broker", lambda: broker)

    chart = ChartService(TradeService(session)).get_live_instrument_chart(EURUSD)

    assert chart["candles"] == []
    assert chart["markers"] == []
    assert chart["position_overlays"] == []
    assert chart["intent_markers"] == []
    assert chart["execution_markers"] == []
    assert chart["source"] == "UNAVAILABLE"
    assert chart["data_state"] == "EMPTY"
    assert chart["reason_detail"]["code"] == "empty_candles"
    assert chart["feed_state"]["price_source"] in {
        "STREAM",
        "SNAPSHOT",
        "STALE",
        "UNAVAILABLE",
    }


def test_live_chart_normalizes_candle_sources(session, monkeypatch, broker):
    def candles(_instrument: str, *, timeframe: str = "1m", num_points: int = 180):
        return [
            {
                "time": 1,
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 0,
                "source": "IG_REST_PRICES",
            }
        ]

    broker.get_historical_candles = candles  # type: ignore[attr-defined]
    monkeypatch.setattr("app.services.chart_service.get_broker", lambda: broker)

    chart = ChartService(TradeService(session)).get_live_instrument_chart(EURUSD)

    assert chart["source"] == "REST_CANDLES"
    assert chart["data_state"] == "READY"
    assert chart["candles"][0]["source"] == "REST_CANDLES"
    assert chart["candles"] != []


def test_live_chart_stale_feed_uses_broker_neutral_feed_source(
    session, monkeypatch, broker
):
    def candles(_instrument: str, *, timeframe: str = "1m", num_points: int = 180):
        return [
            {
                "time": 1,
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 0,
                "source": "REST_CANDLES",
            }
        ]

    broker.get_historical_candles = candles  # type: ignore[attr-defined]
    monkeypatch.setattr("app.services.chart_service.get_broker", lambda: broker)
    stale_tick = datetime.now(UTC) - timedelta(seconds=120)
    health = StreamHealthState(
        enabled=True,
        connected=True,
        subscribed_instruments=(EURUSD,),
        desired_instruments=(EURUSD,),
        capped_instruments=(),
        last_tick_at_by_instrument={EURUSD: stale_tick},
        dependency_ready=True,
    )
    monkeypatch.setattr(
        "app.services.ig_streaming_service.get_ig_streaming_service",
        lambda: _StubStreamingService(health),
    )

    chart = ChartService(TradeService(session)).get_live_instrument_chart(EURUSD)

    assert chart["source"] == "REST_CANDLES"
    assert chart["feed_state"]["price_source"] == "STALE"
    assert chart["feed_state"]["stream_status"] == "stale"
