from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.backtesting.candles import (
    HistoricalCandle,
    PriceBar,
    candle_checksum,
    parse_csv_candles,
    resample_candles,
    validate_candle_series,
)


START = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def _candle(minute: int, price: float = 1.1) -> HistoricalCandle:
    return HistoricalCandle(
        timestamp=START + timedelta(minutes=minute),
        instrument="CS.D.EURUSD.CFD.IP",
        timeframe="1m",
        mid=PriceBar(price, price + 0.001, price - 0.001, price + 0.0005),
        volume=10,
    )


def test_checksum_is_stable_and_order_independent():
    candles = [_candle(0), _candle(1), _candle(2)]

    assert candle_checksum(candles) == candle_checksum(list(reversed(candles)))


def test_validation_sorts_records_and_reports_gaps():
    ordered, gaps = validate_candle_series([_candle(2), _candle(0)])

    assert [row.timestamp for row in ordered] == [START, START + timedelta(minutes=2)]
    assert gaps[0]["missing_count"] == 1


def test_csv_rejects_timezone_ambiguity_duplicates_and_invalid_ohlc():
    base = (
        "timestamp,instrument,timeframe,open,high,low,close\n"
        "2026-01-01T00:00:00,EUR_USD,1m,1.1,1.2,1.0,1.15\n"
    )
    with pytest.raises(ValueError, match="timezone-ambiguous"):
        parse_csv_candles(base)

    duplicate = (
        "timestamp,instrument,timeframe,open,high,low,close\n"
        "2026-01-01T00:00:00Z,EUR_USD,1m,1.1,1.2,1.0,1.15\n"
        "2026-01-01T00:00:00Z,EUR_USD,1m,1.1,1.2,1.0,1.15\n"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        parse_csv_candles(duplicate)

    invalid = (
        "timestamp,instrument,timeframe,open,high,low,close\n"
        "2026-01-01T00:00:00Z,EUR_USD,1m,1.1,1.0,1.2,1.15\n"
    )
    with pytest.raises(ValueError, match="OHLC"):
        parse_csv_candles(invalid)


def test_resampling_uses_utc_epoch_aligned_boundaries():
    result = resample_candles(
        [_candle(index, 1.1 + index * 0.001) for index in range(5)], "5m"
    )

    assert len(result) == 1
    assert result[0].timestamp == START
    assert result[0].mid is not None
    assert result[0].mid.open == pytest.approx(1.1)
    assert result[0].mid.close == pytest.approx(1.1045)
    assert result[0].volume == 50
