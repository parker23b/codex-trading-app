from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.backtesting.candles import HistoricalCandle, PriceBar, parse_timestamp
from app.core.ig_broker import IGBroker


@dataclass(frozen=True, slots=True)
class HistoricalProviderCapabilities:
    provider_id: str
    venue: str
    supported_asset_classes: tuple[str, ...]
    supported_market_types: tuple[str, ...]
    available_timeframes: tuple[str, ...]
    midpoint_ohlc: bool
    bid_ohlc: bool
    ask_ohlc: bool
    trade_price_ohlc: bool
    volume: bool
    spread_must_be_simulated: bool
    maximum_records_per_request: int | None
    authentication: str
    instrument_mapping_examples: dict[str, str] = field(default_factory=dict)
    quota_warnings: tuple[str, ...] = ()


class HistoricalMarketDataProvider(ABC):
    @abstractmethod
    def list_supported_instruments(self) -> list[str]: ...

    @abstractmethod
    def list_supported_timeframes(self) -> list[str]: ...

    @abstractmethod
    def describe_capabilities(self) -> HistoricalProviderCapabilities: ...

    @abstractmethod
    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]: ...

    def map_instrument(self, instrument: str) -> str:
        return instrument


class OandaHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    MAX_RECORDS = 5000
    TIMEFRAME_SECONDS = {"S5": 5, "M1": 60, "M5": 300, "M15": 900, "H1": 3600}

    def __init__(
        self,
        *,
        token: str | None,
        base_url: str = "https://api-fxpractice.oanda.com",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def list_supported_instruments(self) -> list[str]:
        return []

    def list_supported_timeframes(self) -> list[str]:
        return list(self.TIMEFRAME_SECONDS)

    def describe_capabilities(self) -> HistoricalProviderCapabilities:
        return HistoricalProviderCapabilities(
            provider_id="OANDA",
            venue="OANDA_FX",
            supported_asset_classes=("FOREX",),
            supported_market_types=("SPOT_FX",),
            available_timeframes=tuple(self.TIMEFRAME_SECONDS),
            midpoint_ohlc=True,
            bid_ohlc=True,
            ask_ohlc=True,
            trade_price_ohlc=False,
            volume=True,
            spread_must_be_simulated=False,
            maximum_records_per_request=self.MAX_RECORDS,
            authentication="OPTIONAL_PRACTICE_TOKEN_REQUIRED_FOR_IMPORT",
            instrument_mapping_examples={"CS.D.EURUSD.CFD.IP": "EUR_USD"},
            quota_warnings=(
                "Free practice account registration and token are required.",
                "Requests are deterministically chunked to at most 5,000 candles.",
            ),
        )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]:
        if not self.token:
            raise ValueError("OANDA practice token is not configured.")
        if timeframe not in self.TIMEFRAME_SECONDS:
            raise ValueError(f"OANDA timeframe '{timeframe}' is unsupported.")
        provider_instrument = self.map_instrument(instrument)
        step = timedelta(seconds=self.TIMEFRAME_SECONDS[timeframe] * self.MAX_RECORDS)
        cursor = start_at.astimezone(UTC)
        end = end_at.astimezone(UTC)
        candles: list[HistoricalCandle] = []
        while cursor < end:
            window_end = min(cursor + step, end)
            query = urlencode(
                {
                    "price": "MBA",
                    "granularity": timeframe,
                    "from": cursor.isoformat().replace("+00:00", "Z"),
                    "to": window_end.isoformat().replace("+00:00", "Z"),
                    "smooth": "false",
                    "includeFirst": "true",
                }
            )
            request = Request(
                f"{self.base_url}/v3/instruments/{provider_instrument}/candles?{query}",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            payload = _load_json(request, timeout=self.timeout_seconds)
            for item in payload.get("candles", []):
                if not item.get("complete", False):
                    continue
                candles.append(
                    HistoricalCandle(
                        timestamp=parse_timestamp(item["time"]),
                        instrument=instrument,
                        timeframe=timeframe,
                        bid=_provider_bar(item.get("bid")),
                        ask=_provider_bar(item.get("ask")),
                        mid=_provider_bar(item.get("mid")),
                        volume=float(item["volume"])
                        if item.get("volume") is not None
                        else None,
                    )
                )
            cursor = window_end
        return _deduplicate(candles)

    def map_instrument(self, instrument: str) -> str:
        if "_" in instrument and "." not in instrument:
            return instrument
        symbol = _symbol_from_internal(instrument)
        if len(symbol) != 6:
            raise ValueError(f"Cannot map '{instrument}' to an OANDA FX pair.")
        return f"{symbol[:3]}_{symbol[3:]}"


class BinanceHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    MAX_RECORDS = 1000
    TIMEFRAME_MILLISECONDS = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
    }

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def list_supported_instruments(self) -> list[str]:
        return []

    def list_supported_timeframes(self) -> list[str]:
        return list(self.TIMEFRAME_MILLISECONDS)

    def describe_capabilities(self) -> HistoricalProviderCapabilities:
        return HistoricalProviderCapabilities(
            provider_id="BINANCE",
            venue="BINANCE_SPOT",
            supported_asset_classes=("CRYPTO",),
            supported_market_types=("SPOT",),
            available_timeframes=tuple(self.TIMEFRAME_MILLISECONDS),
            midpoint_ohlc=False,
            bid_ohlc=False,
            ask_ohlc=False,
            trade_price_ohlc=True,
            volume=True,
            spread_must_be_simulated=True,
            maximum_records_per_request=self.MAX_RECORDS,
            authentication="NONE",
            instrument_mapping_examples={
                "BINANCE_SPOT:BTCUSDT": "BTCUSDT",
                "BTCUSDT": "BTCUSDT",
            },
            quota_warnings=(
                "Spot klines are venue-specific trade-price candles, not IG CFD prices.",
                "Large imports should prefer Binance public daily/monthly archives.",
            ),
        )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]:
        if timeframe not in self.TIMEFRAME_MILLISECONDS:
            raise ValueError(f"Binance timeframe '{timeframe}' is unsupported.")
        provider_instrument = self.map_instrument(instrument)
        cursor_ms = int(start_at.astimezone(UTC).timestamp() * 1000)
        end_ms = int(end_at.astimezone(UTC).timestamp() * 1000)
        interval_ms = self.TIMEFRAME_MILLISECONDS[timeframe]
        candles: list[HistoricalCandle] = []
        while cursor_ms < end_ms:
            query = urlencode(
                {
                    "symbol": provider_instrument,
                    "interval": timeframe,
                    "startTime": cursor_ms,
                    "endTime": end_ms - 1,
                    "limit": self.MAX_RECORDS,
                }
            )
            payload = _load_json(
                Request(f"{self.base_url}/api/v3/klines?{query}"),
                timeout=self.timeout_seconds,
            )
            if not payload:
                break
            for row in payload:
                opened_at = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
                if opened_at >= end_at.astimezone(UTC):
                    continue
                candles.append(
                    HistoricalCandle(
                        timestamp=opened_at,
                        instrument=instrument,
                        timeframe=timeframe,
                        trade=PriceBar(
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                        ),
                        volume=float(row[5]),
                    )
                )
            next_cursor = int(payload[-1][0]) + interval_ms
            if next_cursor <= cursor_ms:
                raise RuntimeError("Binance pagination did not advance.")
            cursor_ms = next_cursor
            if len(payload) < self.MAX_RECORDS:
                break
        return _deduplicate(candles)

    def map_instrument(self, instrument: str) -> str:
        return instrument.rsplit(":", 1)[-1].replace("/", "").upper()


class IGHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    def __init__(self, broker: IGBroker) -> None:
        self.broker = broker

    def list_supported_instruments(self) -> list[str]:
        return []

    def list_supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h"]

    def describe_capabilities(self) -> HistoricalProviderCapabilities:
        return HistoricalProviderCapabilities(
            provider_id="IG",
            venue="IG",
            supported_asset_classes=("FOREX",),
            supported_market_types=("CFD",),
            available_timeframes=tuple(self.list_supported_timeframes()),
            midpoint_ohlc=True,
            bid_ohlc=False,
            ask_ohlc=False,
            trade_price_ohlc=False,
            volume=True,
            spread_must_be_simulated=True,
            maximum_records_per_request=500,
            authentication="EXISTING_IG_CREDENTIALS",
            instrument_mapping_examples={"CS.D.EURUSD.CFD.IP": "CS.D.EURUSD.CFD.IP"},
            quota_warnings=(
                "IG default quota is 10,000 historical price points per week.",
                "Use for broker-aligned validation, not large intraday backfills.",
            ),
        )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]:
        raw = self.broker.get_historical_candles(
            instrument,
            timeframe=timeframe,
            num_points=500,
        )
        candles = [
            HistoricalCandle(
                timestamp=datetime.fromtimestamp(int(row["time"]), tz=UTC),
                instrument=instrument,
                timeframe=timeframe,
                mid=PriceBar(
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                ),
                volume=float(row["volume"]) if row.get("volume") is not None else None,
            )
            for row in raw
            if start_at.astimezone(UTC)
            <= datetime.fromtimestamp(int(row["time"]), tz=UTC)
            < end_at.astimezone(UTC)
        ]
        return _deduplicate(candles)


class CsvHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    def list_supported_instruments(self) -> list[str]:
        return []

    def list_supported_timeframes(self) -> list[str]:
        return ["S5", "1m", "5m", "15m", "30m", "1h"]

    def describe_capabilities(self) -> HistoricalProviderCapabilities:
        return HistoricalProviderCapabilities(
            provider_id="CSV",
            venue="USER_SUPPLIED",
            supported_asset_classes=("FOREX", "CRYPTO", "INDICES", "COMMODITIES"),
            supported_market_types=("USER_DEFINED",),
            available_timeframes=tuple(self.list_supported_timeframes()),
            midpoint_ohlc=True,
            bid_ohlc=True,
            ask_ohlc=True,
            trade_price_ohlc=True,
            volume=True,
            spread_must_be_simulated=False,
            maximum_records_per_request=None,
            authentication="NONE",
            quota_warnings=("Source licensing and provenance remain operator-owned.",),
        )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]:
        raise ValueError("CSV candles are supplied through the import payload.")


def _provider_bar(raw: dict[str, Any] | None) -> PriceBar | None:
    if not raw:
        return None
    return PriceBar(
        open=float(raw["o"]),
        high=float(raw["h"]),
        low=float(raw["l"]),
        close=float(raw["c"]),
    )


def _load_json(request: Request, *, timeout: float) -> Any:
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _deduplicate(candles: list[HistoricalCandle]) -> list[HistoricalCandle]:
    by_timestamp = {candle.timestamp.astimezone(UTC): candle for candle in candles}
    return [by_timestamp[key] for key in sorted(by_timestamp)]


def _symbol_from_internal(instrument: str) -> str:
    parts = instrument.split(".")
    if len(parts) >= 3:
        return parts[2].replace("MINI", "")
    return instrument.replace("/", "").replace("_", "").upper()
