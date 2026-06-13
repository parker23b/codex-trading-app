from __future__ import annotations

import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from typing import Iterable

from app.backtesting.candles import HistoricalCandle, candle_checksum


class HistoricalDataRepository:
    def write_partition(
        self,
        *,
        dataset_id: str,
        instrument: str,
        timeframe: str,
        candles: Iterable[HistoricalCandle],
    ) -> tuple[str, str]:
        raise NotImplementedError

    def read_partition(self, storage_path: str) -> list[HistoricalCandle]:
        raise NotImplementedError


class JsonlHistoricalDataRepository(HistoricalDataRepository):
    """Immutable deterministic gzip JSONL storage behind a replaceable boundary."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_partition(
        self,
        *,
        dataset_id: str,
        instrument: str,
        timeframe: str,
        candles: Iterable[HistoricalCandle],
    ) -> tuple[str, str]:
        rows = sorted(candles, key=lambda candle: candle.timestamp)
        checksum = candle_checksum(rows)
        relative_path = Path(dataset_id) / (
            f"{self._safe_name(instrument)}-{self._safe_name(timeframe)}-{checksum[:16]}.jsonl.gz"
        )
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents:
            raise ValueError("Historical storage path escaped the configured root.")
        if target.exists():
            raise ValueError("Immutable historical partition already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)

        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
            for candle in rows:
                payload = json.dumps(
                    candle.canonical_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                compressed.write(payload.encode("utf-8") + b"\n")
        target.write_bytes(buffer.getvalue())
        return relative_path.as_posix(), checksum

    def read_partition(self, storage_path: str) -> list[HistoricalCandle]:
        target = (self.root / storage_path).resolve()
        if self.root not in target.parents or not target.is_file():
            raise ValueError("Historical partition is unavailable.")
        rows: list[HistoricalCandle] = []
        with gzip.open(target, "rt", encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    rows.append(HistoricalCandle.from_dict(json.loads(line)))
        return rows

    def physical_checksum(self, storage_path: str) -> str:
        target = (self.root / storage_path).resolve()
        return sha256(target.read_bytes()).hexdigest()

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "partition"
