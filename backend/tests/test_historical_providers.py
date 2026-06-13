from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.backtesting.providers import (
    BinanceHistoricalMarketDataProvider,
    OandaHistoricalMarketDataProvider,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def test_oanda_capabilities_and_chunking_are_deterministic(monkeypatch):
    calls: list[str] = []

    def fake_load(request, *, timeout):
        calls.append(request.full_url)
        return {"candles": []}

    monkeypatch.setattr("app.backtesting.providers._load_json", fake_load)
    provider = OandaHistoricalMarketDataProvider(token="practice-token")
    capabilities = provider.describe_capabilities()

    candles = provider.fetch_candles(
        "CS.D.EURUSD.CFD.IP",
        "M1",
        START,
        START + timedelta(minutes=10_001),
    )

    assert candles == []
    assert capabilities.maximum_records_per_request == 5000
    assert capabilities.bid_ohlc is True
    assert provider.map_instrument("CS.D.EURUSD.CFD.IP") == "EUR_USD"
    assert len(calls) == 3
    assert all("granularity=M1" in call for call in calls)


def test_binance_public_pagination_and_venue_metadata(monkeypatch):
    calls = 0

    def fake_load(request, *, timeout):
        nonlocal calls
        calls += 1
        start_ms = int(request.full_url.split("startTime=")[1].split("&")[0])
        row_count = 1000 if calls == 1 else 1
        return [
            [
                start_ms + index * 60_000,
                "100",
                "101",
                "99",
                "100",
                "5",
            ]
            for index in range(row_count)
        ]

    monkeypatch.setattr("app.backtesting.providers._load_json", fake_load)
    provider = BinanceHistoricalMarketDataProvider()
    capabilities = provider.describe_capabilities()

    candles = provider.fetch_candles(
        "BINANCE_SPOT:BTCUSDT",
        "1m",
        START,
        START + timedelta(minutes=1001),
    )

    assert len(candles) == 1001
    assert calls == 2
    assert capabilities.venue == "BINANCE_SPOT"
    assert capabilities.authentication == "NONE"
    assert capabilities.spread_must_be_simulated is True
