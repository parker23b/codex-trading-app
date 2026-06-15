from __future__ import annotations

import gzip
from hashlib import sha256
import io
import json
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
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


@dataclass(frozen=True, slots=True)
class StagedHistoricalPartition:
    staging_path: str
    storage_path: str
    checksum: str


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
        staged = self.stage_partition(
            dataset_id=dataset_id,
            instrument=instrument,
            timeframe=timeframe,
            candles=candles,
        )
        self.publish_partition(staged)
        return staged.storage_path, staged.checksum

    def stage_partition(
        self,
        *,
        dataset_id: str,
        instrument: str,
        timeframe: str,
        candles: Iterable[HistoricalCandle],
    ) -> StagedHistoricalPartition:
        rows = sorted(candles, key=lambda candle: candle.timestamp)
        checksum = candle_checksum(rows)
        filename = (
            f"{self._safe_name(instrument)}-{self._safe_name(timeframe)}-"
            f"{checksum[:16]}.jsonl.gz"
        )
        storage_path = Path(dataset_id) / filename
        staging_path = Path(".staging") / dataset_id / filename
        target = self._resolve(staging_path)
        published_target = self._resolve(storage_path)
        if target.exists() or published_target.exists():
            raise ValueError("Historical partition already exists.")
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
        return StagedHistoricalPartition(
            staging_path=staging_path.as_posix(),
            storage_path=storage_path.as_posix(),
            checksum=checksum,
        )

    def publish_partition(self, staged: StagedHistoricalPartition) -> None:
        source = self._resolve(Path(staged.staging_path))
        target = self._resolve(Path(staged.storage_path))
        if not source.is_file():
            raise ValueError("Staged historical partition is unavailable.")
        if target.exists():
            raise ValueError("Immutable historical partition already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    def cleanup_dataset(self, dataset_id: str) -> None:
        for relative in (Path(".staging") / dataset_id, Path(dataset_id)):
            target = self._resolve(relative)
            if target.exists():
                shutil.rmtree(target)

    def _resolve(self, relative_path: Path) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Historical storage path escaped the configured root.")
        return target

    def read_partition(self, storage_path: str) -> list[HistoricalCandle]:
        target = self._resolve(Path(storage_path))
        if not target.is_file():
            raise ValueError("Historical partition is unavailable.")
        rows: list[HistoricalCandle] = []
        with gzip.open(target, "rt", encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    rows.append(HistoricalCandle.from_dict(json.loads(line)))
        return rows

    def physical_checksum(self, storage_path: str) -> str:
        target = self._resolve(Path(storage_path))
        return sha256(target.read_bytes()).hexdigest()

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "partition"
