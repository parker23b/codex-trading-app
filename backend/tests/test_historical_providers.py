from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import pytest
from sqlmodel import select

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.providers import (
    BinanceHistoricalMarketDataProvider,
    HistoricalMarketDataProvider,
    HistoricalProviderCapabilities,
    OandaHistoricalMarketDataProvider,
)
from app.backtesting.storage import JsonlHistoricalDataRepository
from app.models.backtest import HistoricalDataset, HistoricalDatasetPartition
from app.services.historical_data_service import (
    DatasetRecoveryError,
    HistoricalDataService,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def _candles(instrument: str, count: int) -> list[HistoricalCandle]:
    return [
        HistoricalCandle(
            timestamp=START + timedelta(minutes=index),
            instrument=instrument,
            timeframe="1m",
            trade=PriceBar(open=100.0, high=101.0, low=99.0, close=100.0),
            volume=1.0,
        )
        for index in range(count)
    ]


class _FakeProvider(HistoricalMarketDataProvider):
    def __init__(
        self,
        fetch: Callable[[str, str, datetime, datetime], list[HistoricalCandle]],
    ) -> None:
        self.fetch = fetch

    def list_supported_instruments(self) -> list[str]:
        return []

    def list_supported_timeframes(self) -> list[str]:
        return ["1m"]

    def describe_capabilities(self) -> HistoricalProviderCapabilities:
        return HistoricalProviderCapabilities(
            provider_id="TEST",
            venue="TEST_VENUE",
            supported_asset_classes=("CRYPTO",),
            supported_market_types=("SPOT",),
            available_timeframes=("1m",),
            midpoint_ohlc=False,
            bid_ohlc=False,
            ask_ohlc=False,
            trade_price_ohlc=True,
            volume=True,
            spread_must_be_simulated=True,
            maximum_records_per_request=1000,
            authentication="NONE",
        )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[HistoricalCandle]:
        return self.fetch(instrument, timeframe, start_at, end_at)


def _import(
    session,
    history: Path,
    provider: HistoricalMarketDataProvider,
    *,
    instruments: list[str],
) -> HistoricalDataset:
    return HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(history),
        providers={"TEST": provider},
    ).import_from_provider(
        provider_id="TEST",
        display_name="provider fixture",
        instruments=instruments,
        timeframe="1m",
        start_at=START,
        end_at=START + timedelta(hours=1),
        asset_class="CRYPTO",
        market_type="SPOT",
        venue="TEST_VENUE",
    )


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
                start_ms + (index + 1) * 60_000 - 1,
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


def test_binance_excludes_still_open_provider_candle(monkeypatch):
    now_ms = int(datetime.now(UTC).timestamp() * 1000)

    monkeypatch.setattr(
        "app.backtesting.providers._load_json",
        lambda *_args, **_kwargs: [
            [now_ms - 60_000, "100", "101", "99", "100", "5", now_ms + 60_000]
        ],
    )

    candles = BinanceHistoricalMarketDataProvider().fetch_candles(
        "BTCUSDT",
        "1m",
        datetime.fromtimestamp((now_ms - 60_000) / 1000, tz=UTC),
        datetime.fromtimestamp((now_ms + 120_000) / 1000, tz=UTC),
    )

    assert candles == []


def test_provider_import_rejects_false_venue_and_asset_metadata(session, tmp_path):
    provider = BinanceHistoricalMarketDataProvider()
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
        providers={"BINANCE": provider},
    )

    with pytest.raises(ValueError, match="does not support asset class"):
        service.import_from_provider(
            provider_id="BINANCE",
            display_name="invalid",
            instruments=["BTCUSDT"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(minutes=1),
            asset_class="FOREX",
            market_type="SPOT",
            venue="IG",
        )

    with pytest.raises(ValueError, match="must use venue 'BINANCE_SPOT'"):
        service.import_from_provider(
            provider_id="BINANCE",
            display_name="invalid",
            instruments=["BTCUSDT"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(minutes=1),
            asset_class="CRYPTO",
            market_type="SPOT",
            venue="IG",
        )


def test_one_requested_hour_returning_one_candle_is_partial_not_ready(
    session, tmp_path
):
    history = tmp_path / "history"

    with pytest.raises(ValueError, match="before required boundary"):
        _import(
            session,
            history,
            _FakeProvider(lambda instrument, *_args: _candles(instrument, 1)),
            instruments=["BTCUSDT"],
        )

    dataset = session.exec(select(HistoricalDataset)).one()
    assert dataset.status == "PARTIAL"
    assert dataset.completeness_status == "PARTIAL_COVERAGE"
    assert dataset.checksum is None
    assert dataset.failure_reason
    assert session.exec(select(HistoricalDatasetPartition)).all() == []
    assert list(history.rglob("*.gz")) == []


def test_second_instrument_failure_does_not_publish_first_instrument(session, tmp_path):
    history = tmp_path / "history"

    def fetch(instrument, *_args):
        if instrument == "ETHUSDT":
            raise RuntimeError("provider failed on second instrument")
        return _candles(instrument, 60)

    with pytest.raises(RuntimeError, match="second instrument"):
        _import(
            session,
            history,
            _FakeProvider(fetch),
            instruments=["BTCUSDT", "ETHUSDT"],
        )

    dataset = session.exec(select(HistoricalDataset)).one()
    assert dataset.status == "PARTIAL"
    assert "second instrument" in (dataset.failure_reason or "")
    assert session.exec(select(HistoricalDatasetPartition)).all() == []
    assert list(history.rglob("*.gz")) == []


def test_truncated_provider_response_is_detected(session, tmp_path):
    with pytest.raises(ValueError, match="provider response may be truncated"):
        _import(
            session,
            tmp_path / "history",
            _FakeProvider(lambda instrument, *_args: _candles(instrument, 30)),
            instruments=["BTCUSDT"],
        )

    dataset = session.exec(select(HistoricalDataset)).one()
    assert dataset.status == "PARTIAL"
    assert dataset.completeness_status == "PARTIAL_COVERAGE"


def test_provider_request_is_aligned_outward_without_losing_requested_range(
    session, tmp_path
):
    calls: list[tuple[datetime, datetime]] = []

    def fetch(instrument, _timeframe, start_at, end_at):
        calls.append((start_at, end_at))
        return _candles(instrument, 3)

    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
        providers={"TEST": _FakeProvider(fetch)},
    )
    requested_start = START + timedelta(seconds=30)
    requested_end = START + timedelta(minutes=2, seconds=15)

    dataset = service.import_from_provider(
        provider_id="TEST",
        display_name="aligned fixture",
        instruments=["BTCUSDT"],
        timeframe="1m",
        start_at=requested_start,
        end_at=requested_end,
        asset_class="CRYPTO",
        market_type="SPOT",
        venue="TEST_VENUE",
    )

    assert calls == [(START, START + timedelta(minutes=3))]
    assert dataset.status == "READY"
    assert dataset.import_parameters["start_at"] == requested_start.isoformat()
    assert dataset.import_parameters["end_at"] == requested_end.isoformat()


def test_database_failure_after_staged_write_cleans_files_and_stays_nonselectable(
    session, tmp_path, monkeypatch
):
    history = tmp_path / "history"
    original_commit = session.commit
    commit_count = 0

    def fail_publication_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("database publication failed")
        return original_commit()

    monkeypatch.setattr(session, "commit", fail_publication_commit)

    with pytest.raises(RuntimeError, match="database publication failed"):
        _import(
            session,
            history,
            _FakeProvider(lambda instrument, *_args: _candles(instrument, 60)),
            instruments=["BTCUSDT"],
        )

    dataset = session.exec(select(HistoricalDataset)).one()
    assert dataset.status == "PARTIAL"
    assert dataset.checksum is None
    assert session.exec(select(HistoricalDatasetPartition)).all() == []
    assert list(history.rglob("*.gz")) == []


def test_successful_commit_with_raised_acknowledgement_reconciles_ready_snapshot(
    session, tmp_path, monkeypatch
):
    history = tmp_path / "history"
    repository = JsonlHistoricalDataRepository(history)
    provider = _FakeProvider(lambda instrument, *_args: _candles(instrument, 60))
    service = HistoricalDataService(
        session,
        repository=repository,
        providers={"TEST": provider},
    )
    original_commit = session.commit
    commit_count = 0

    def commit_then_raise():
        nonlocal commit_count
        commit_count += 1
        original_commit()
        if commit_count == 2:
            raise RuntimeError("database commit acknowledgement was lost")

    monkeypatch.setattr(session, "commit", commit_then_raise)

    recovered = service.import_from_provider(
        provider_id="TEST",
        display_name="ambiguous commit",
        instruments=["BTCUSDT"],
        timeframe="1m",
        start_at=START,
        end_at=START + timedelta(hours=1),
        asset_class="CRYPTO",
        market_type="SPOT",
        venue="TEST_VENUE",
    )

    assert recovered.status == "READY"
    assert recovered.checksum
    assert service.verify_dataset_checksum(recovered.id).id == recovered.id
    partitions = session.exec(
        select(HistoricalDatasetPartition).where(
            HistoricalDatasetPartition.dataset_id == recovered.id
        )
    ).all()
    assert len(partitions) == 1
    assert len(list((history / recovered.id).glob("*.gz"))) == 1

    retry = service.import_from_provider(
        provider_id="TEST",
        display_name="safe retry",
        instruments=["BTCUSDT"],
        timeframe="1m",
        start_at=START,
        end_at=START + timedelta(hours=1),
        asset_class="CRYPTO",
        market_type="SPOT",
        venue="TEST_VENUE",
    )

    assert retry.status == "READY"
    assert retry.id != recovered.id
    assert service.verify_dataset_checksum(retry.id).id == retry.id
    ready_datasets = session.exec(
        select(HistoricalDataset).where(HistoricalDataset.status == "READY")
    ).all()
    assert {item.id for item in ready_datasets} == {recovered.id, retry.id}
    assert all(list((history / item.id).glob("*.gz")) for item in ready_datasets)


def test_ambiguous_commit_with_missing_file_marks_recovery_required_and_retries_safely(
    session, tmp_path, monkeypatch
):
    history = tmp_path / "history"
    repository = JsonlHistoricalDataRepository(history)
    provider = _FakeProvider(lambda instrument, *_args: _candles(instrument, 60))
    service = HistoricalDataService(
        session,
        repository=repository,
        providers={"TEST": provider},
    )
    original_commit = session.commit
    commit_count = 0
    deleted_path: Path | None = None

    def commit_then_delete_and_raise():
        nonlocal commit_count, deleted_path
        commit_count += 1
        original_commit()
        if commit_count == 2:
            deleted_path = next(history.rglob("*.gz"))
            deleted_path.unlink()
            raise RuntimeError("database commit acknowledgement was lost")

    monkeypatch.setattr(session, "commit", commit_then_delete_and_raise)

    with pytest.raises(DatasetRecoveryError, match="failed recovery verification"):
        service.import_from_provider(
            provider_id="TEST",
            display_name="missing file after ambiguous commit",
            instruments=["BTCUSDT"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(hours=1),
            asset_class="CRYPTO",
            market_type="SPOT",
            venue="TEST_VENUE",
        )

    session.expire_all()
    damaged = session.exec(select(HistoricalDataset)).one()
    damaged_partitions = session.exec(
        select(HistoricalDatasetPartition).where(
            HistoricalDatasetPartition.dataset_id == damaged.id
        )
    ).all()
    assert damaged.status == "READY"
    assert damaged.availability == "RECOVERY_REQUIRED"
    assert "failed recovery verification" in (damaged.availability_reason or "")
    assert len(damaged_partitions) == 1
    assert deleted_path is not None
    assert not deleted_path.exists()
    assert service.list_datasets(selectable_only=True) == []
    assert service.dataset_is_selectable(damaged.id) is False

    monkeypatch.setattr(session, "commit", original_commit)
    retry = service.import_from_provider(
        provider_id="TEST",
        display_name="clean retry",
        instruments=["BTCUSDT"],
        timeframe="1m",
        start_at=START,
        end_at=START + timedelta(hours=1),
        asset_class="CRYPTO",
        market_type="SPOT",
        venue="TEST_VENUE",
    )

    session.expire_all()
    damaged = session.get(HistoricalDataset, damaged.id)
    selectable = service.list_datasets(selectable_only=True)
    retry_partitions = service.list_partitions(retry.id)
    assert damaged is not None
    assert damaged.availability == "RECOVERY_REQUIRED"
    assert retry.id != damaged.id
    assert retry.availability == "AVAILABLE"
    assert [item.id for item in selectable] == [retry.id]
    assert retry_partitions[0].storage_path != damaged_partitions[0].storage_path
    assert (history / retry_partitions[0].storage_path).exists()


def test_ambiguous_commit_with_corrupt_file_marks_recovery_required_without_cleanup(
    session, tmp_path, monkeypatch
):
    history = tmp_path / "history"
    repository = JsonlHistoricalDataRepository(history)
    service = HistoricalDataService(
        session,
        repository=repository,
        providers={
            "TEST": _FakeProvider(lambda instrument, *_args: _candles(instrument, 60))
        },
    )
    original_commit = session.commit
    commit_count = 0
    corrupt_path: Path | None = None

    def commit_then_corrupt_and_raise():
        nonlocal commit_count, corrupt_path
        commit_count += 1
        original_commit()
        if commit_count == 2:
            corrupt_path = next(history.rglob("*.gz"))
            corrupt_path.write_bytes(b"corrupt published partition")
            raise RuntimeError("database commit acknowledgement was lost")

    monkeypatch.setattr(session, "commit", commit_then_corrupt_and_raise)

    with pytest.raises(DatasetRecoveryError, match="failed recovery verification"):
        service.import_from_provider(
            provider_id="TEST",
            display_name="corrupt file after ambiguous commit",
            instruments=["BTCUSDT"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(hours=1),
            asset_class="CRYPTO",
            market_type="SPOT",
            venue="TEST_VENUE",
        )

    session.expire_all()
    damaged = session.exec(select(HistoricalDataset)).one()
    assert damaged.status == "READY"
    assert damaged.availability == "RECOVERY_REQUIRED"
    assert service.dataset_is_selectable(damaged.id) is False
    assert corrupt_path is not None
    assert corrupt_path.read_bytes() == b"corrupt published partition"


def test_file_write_failure_after_import_metadata_begins_is_recorded(session, tmp_path):
    class FailingRepository(JsonlHistoricalDataRepository):
        def stage_partition(self, **_kwargs):
            raise OSError("staged file write failed")

    history = tmp_path / "history"
    service = HistoricalDataService(
        session,
        repository=FailingRepository(history),
        providers={
            "TEST": _FakeProvider(lambda instrument, *_args: _candles(instrument, 60))
        },
    )

    with pytest.raises(OSError, match="staged file write failed"):
        service.import_from_provider(
            provider_id="TEST",
            display_name="file failure",
            instruments=["BTCUSDT"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(hours=1),
            asset_class="CRYPTO",
            market_type="SPOT",
            venue="TEST_VENUE",
        )

    dataset = session.exec(select(HistoricalDataset)).one()
    assert dataset.status == "FAILED"
    assert "staged file write failed" in (dataset.failure_reason or "")
    assert session.exec(select(HistoricalDatasetPartition)).all() == []
    assert list(history.rglob("*.gz")) == []


def test_retry_creates_a_new_snapshot_without_reusing_partial_state(session, tmp_path):
    attempts = 0

    def fetch(instrument, *_args):
        nonlocal attempts
        attempts += 1
        return _candles(instrument, 1 if attempts == 1 else 60)

    provider = _FakeProvider(fetch)
    history = tmp_path / "history"
    with pytest.raises(ValueError):
        _import(session, history, provider, instruments=["BTCUSDT"])

    ready = _import(session, history, provider, instruments=["BTCUSDT"])
    datasets = session.exec(
        select(HistoricalDataset).order_by(HistoricalDataset.imported_at)
    ).all()

    assert len(datasets) == 2
    assert datasets[0].status == "PARTIAL"
    assert datasets[1].status == "READY"
    assert ready.id != datasets[0].id
    assert len(session.exec(select(HistoricalDatasetPartition)).all()) == 1
