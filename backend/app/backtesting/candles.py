from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from typing import Iterable


PRICE_COMPONENTS = ("bid", "ask", "mid", "trade")
TIMEFRAME_SECONDS = {
    "S5": 5,
    "1m": 60,
    "M1": 60,
    "5m": 300,
    "M5": 300,
    "15m": 900,
    "M15": 900,
    "30m": 1800,
    "1h": 3600,
    "H1": 3600,
}


@dataclass(frozen=True, slots=True)
class PriceBar:
    open: float
    high: float
    low: float
    close: float

    def validate(self, component: str) -> None:
        values = (self.open, self.high, self.low, self.close)
        if not all(isfinite(value) for value in values):
            raise ValueError(f"{component} OHLC contains a non-finite value.")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError(f"{component} OHLC relationship is invalid.")
        if self.high < self.low:
            raise ValueError(f"{component} high is below low.")


@dataclass(frozen=True, slots=True)
class HistoricalCandle:
    timestamp: datetime
    instrument: str
    timeframe: str
    bid: PriceBar | None = None
    ask: PriceBar | None = None
    mid: PriceBar | None = None
    trade: PriceBar | None = None
    volume: float | None = None

    def validate(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Candle timestamp must be timezone-aware.")
        if not self.instrument.strip():
            raise ValueError("Candle instrument is required.")
        if self.timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported candle timeframe '{self.timeframe}'.")
        components = self.available_components
        if not components:
            raise ValueError("Candle requires at least one price component.")
        for component in components:
            getattr(self, component).validate(component)
        if self.volume is not None and (not isfinite(self.volume) or self.volume < 0):
            raise ValueError("Candle volume must be finite and non-negative.")

    @property
    def available_components(self) -> tuple[str, ...]:
        return tuple(
            component
            for component in PRICE_COMPONENTS
            if getattr(self, component) is not None
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "bid": asdict(self.bid) if self.bid else None,
            "ask": asdict(self.ask) if self.ask else None,
            "mid": asdict(self.mid) if self.mid else None,
            "trade": asdict(self.trade) if self.trade else None,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "HistoricalCandle":
        def bar(name: str) -> PriceBar | None:
            raw = value.get(name)
            if not isinstance(raw, dict):
                return None
            return PriceBar(
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
            )

        candle = cls(
            timestamp=parse_timestamp(str(value["timestamp"])),
            instrument=str(value["instrument"]),
            timeframe=str(value["timeframe"]),
            bid=bar("bid"),
            ask=bar("ask"),
            mid=bar("mid"),
            trade=bar("trade"),
            volume=float(value["volume"]) if value.get("volume") is not None else None,
        )
        candle.validate()
        return candle


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(
            f"Timestamp '{value}' is timezone-ambiguous; include an offset or Z."
        )
    return parsed.astimezone(UTC)


def validate_candle_series(
    candles: Iterable[HistoricalCandle],
) -> tuple[list[HistoricalCandle], list[dict[str, object]]]:
    ordered = sorted(candles, key=lambda item: item.timestamp)
    if not ordered:
        raise ValueError("Historical import contains no candles.")
    instruments = {candle.instrument for candle in ordered}
    timeframes = {candle.timeframe for candle in ordered}
    if len(instruments) != 1:
        raise ValueError("Historical partition contains mixed instruments.")
    if len(timeframes) != 1:
        raise ValueError("Historical partition contains mixed timeframes.")
    seen: set[datetime] = set()
    for candle in ordered:
        candle.validate()
        timestamp = candle.timestamp.astimezone(UTC)
        if timestamp in seen:
            raise ValueError(f"Duplicate candle timestamp: {timestamp.isoformat()}.")
        seen.add(timestamp)

    gap_warnings: list[dict[str, object]] = []
    expected_seconds = TIMEFRAME_SECONDS[ordered[0].timeframe]
    for previous, current in zip(ordered, ordered[1:]):
        actual_seconds = int((current.timestamp - previous.timestamp).total_seconds())
        if actual_seconds > expected_seconds:
            missing = max((actual_seconds // expected_seconds) - 1, 1)
            gap_warnings.append(
                {
                    "code": "MISSING_CANDLES",
                    "after": previous.timestamp.astimezone(UTC).isoformat(),
                    "before": current.timestamp.astimezone(UTC).isoformat(),
                    "expected_seconds": expected_seconds,
                    "missing_count": missing,
                }
            )
    return ordered, gap_warnings


def candle_checksum(candles: Iterable[HistoricalCandle]) -> str:
    digest = sha256()
    for candle in sorted(candles, key=lambda item: item.timestamp):
        payload = json.dumps(
            candle.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def resample_candles(
    candles: Iterable[HistoricalCandle], target_timeframe: str
) -> list[HistoricalCandle]:
    source, _ = validate_candle_series(candles)
    if target_timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported target timeframe '{target_timeframe}'.")
    source_seconds = TIMEFRAME_SECONDS[source[0].timeframe]
    target_seconds = TIMEFRAME_SECONDS[target_timeframe]
    if target_seconds < source_seconds or target_seconds % source_seconds:
        raise ValueError("Target timeframe must be a whole multiple of the source.")
    if target_seconds == source_seconds:
        return source

    buckets: dict[datetime, list[HistoricalCandle]] = {}
    for candle in source:
        epoch = int(candle.timestamp.timestamp())
        boundary = epoch - (epoch % target_seconds)
        bucket_at = datetime.fromtimestamp(boundary, tz=UTC)
        buckets.setdefault(bucket_at, []).append(candle)

    result: list[HistoricalCandle] = []
    for bucket_at in sorted(buckets):
        rows = buckets[bucket_at]

        def aggregate(component: str) -> PriceBar | None:
            bars = [getattr(row, component) for row in rows]
            available = [bar for bar in bars if bar is not None]
            if not available:
                return None
            if len(available) != len(rows):
                raise ValueError(
                    f"Price component '{component}' is missing inside a resample bucket."
                )
            return PriceBar(
                open=available[0].open,
                high=max(bar.high for bar in available),
                low=min(bar.low for bar in available),
                close=available[-1].close,
            )

        result.append(
            HistoricalCandle(
                timestamp=bucket_at,
                instrument=rows[0].instrument,
                timeframe=target_timeframe,
                bid=aggregate("bid"),
                ask=aggregate("ask"),
                mid=aggregate("mid"),
                trade=aggregate("trade"),
                volume=(
                    sum(row.volume or 0.0 for row in rows)
                    if any(row.volume is not None for row in rows)
                    else None
                ),
            )
        )
    return result


def parse_csv_candles(csv_text: str) -> list[HistoricalCandle]:
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"timestamp", "instrument", "timeframe"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("CSV requires timestamp, instrument, and timeframe columns.")

    candles: list[HistoricalCandle] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            candles.append(
                HistoricalCandle(
                    timestamp=parse_timestamp(row["timestamp"]),
                    instrument=row["instrument"].strip(),
                    timeframe=row["timeframe"].strip(),
                    bid=_csv_bar(row, "bid"),
                    ask=_csv_bar(row, "ask"),
                    mid=_csv_bar(row, "mid"),
                    trade=_csv_bar(row, "trade") or _csv_bar(row, ""),
                    volume=_optional_float(row.get("volume")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"CSV row {row_number}: {exc}") from exc
    ordered, _ = validate_candle_series(candles)
    return ordered


def _csv_bar(row: dict[str, str], prefix: str) -> PriceBar | None:
    names = {
        key: f"{prefix}_{key}" if prefix else key
        for key in ("open", "high", "low", "close")
    }
    values = {key: row.get(column) for key, column in names.items()}
    present = [value not in (None, "") for value in values.values()]
    if not any(present):
        return None
    if not all(present):
        label = prefix or "trade"
        raise ValueError(f"Incomplete {label} OHLC columns.")
    return PriceBar(**{key: float(value) for key, value in values.items()})


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
