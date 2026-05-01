from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.runtime import runtime_manager
from app.services.chart_service import ChartService
from app.services.ig_streaming_service import StreamHealthState
from app.services.trade_service import TradeService
from app.services.watchlist_service import WatchlistService


EURUSD = "CS.D.EURUSD.CFD.IP"
GBPUSD = "CS.D.GBPUSD.CFD.IP"
USDJPY = "CS.D.USDJPY.CFD.IP"
AUDUSD = "CS.D.AUDUSD.CFD.IP"
UNKNOWN = "CS.D.UNKNOWN.CFD.IP"


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


def test_bulk_strategy_watchlist_add_enforces_cap_and_returns_structured_reasons(session):
    service = WatchlistService(session)
    service.settings.ig_streaming_max_instruments = 2

    result = service.add_to_strategy_watchlist([EURUSD, GBPUSD, USDJPY])

    assert [item["instrument"] for item in result["added"]] == [EURUSD, GBPUSD]
    assert result["skipped"] == [
        {
            "instrument": USDJPY,
            "reason": "Strategy watchlist limit reached",
            "reason_detail": {
                "code": "strategy_watchlist_limit_reached",
                "label": "Strategy watchlist limit reached",
                "operator_action": "Remove another operator-added instrument first. The current phase cap is 2 instruments.",
            },
        }
    ]


def test_partial_bulk_add_reports_existing_and_skipped_reasons(session):
    service = WatchlistService(session)
    service.settings.ig_streaming_max_instruments = 1
    service.add_to_strategy_watchlist([EURUSD])

    result = service.add_to_strategy_watchlist([EURUSD, GBPUSD])

    assert result["added"][0]["reason_detail"]["code"] == "already_in_strategy_watchlist"
    assert result["skipped"][0]["reason_detail"]["code"] == "strategy_watchlist_limit_reached"


class _StubStreamingService:
    def __init__(self, health: StreamHealthState):
        self.health = health

    def get_health(self) -> StreamHealthState:
        return self.health


def test_feed_state_projection_covers_desired_streaming_capped_stale_and_no_runtime(session, monkeypatch, fixed_now):
    desired = EURUSD
    streaming = GBPUSD
    capped = USDJPY
    stale = AUDUSD
    no_runtime = "CS.D.USDCHF.CFD.IP"
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
    assert no_runtime_state["entry_eligibility_reason"]["code"] == "no_active_strategy_runtime"
    assert no_runtime_state["strategies_may_evaluate"] is False


def test_live_chart_returns_explicit_unsupported_response(session):
    chart = ChartService(TradeService(session)).get_live_instrument_chart(UNKNOWN)

    assert chart["candles"] == []
    assert chart["data_state"] == "UNSUPPORTED"
    assert chart["source"] == "UNAVAILABLE"
    assert chart["reason_detail"]["code"] == "unsupported_chart_instrument"


def test_live_chart_handles_empty_candles_no_markers_and_broker_neutral_sources(session, monkeypatch, broker):
    def empty_candles(_instrument: str, *, timeframe: str = "1m", num_points: int = 180):
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
