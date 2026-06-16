from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.storage import JsonlHistoricalDataRepository
from app.models.backtest import (
    BacktestEquityPoint,
    BacktestMetric,
    BacktestRun,
    BacktestRunInstrument,
    BacktestRunStatus,
    BacktestTrade,
    BacktestWarning,
    DatasetAvailability,
    HistoricalDataset,
    HistoricalDatasetPartition,
)
from app.models.trade import Execution, Position, Trade, TradeIntent
from app.services.backtest_service import (
    BACKTEST_RESULT_PROJECTION_ONLY_FIELDS,
    BACKTEST_RESULT_STATUS_CONSTRAINED_FIELDS,
    BACKTEST_RESULT_VERIFICATION_ENVELOPE_FIELDS,
    BACKTEST_RESULT_MANIFEST_V1,
    BACKTEST_RESULT_MANIFEST_V2,
    CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA,
    CANONICAL_BACKTEST_RESULT_MANIFEST_V1_SCHEMA,
    BacktestService,
)
from app.services.historical_data_service import HistoricalDataService
from app.services.historical_data_service import (
    AUTHORITATIVE_DATASET_MANIFEST_FIELDS,
    AUTHORITATIVE_PARTITION_MANIFEST_FIELDS,
    CANONICAL_DATASET_MANIFEST_SCHEMA,
    MANIFEST_OPERATIONAL_FIELDS,
    MANIFEST_PROJECTION_ONLY_FIELDS,
    MANIFEST_VERIFICATION_ENVELOPE_FIELDS,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def _csv() -> str:
    rows = ["timestamp,instrument,timeframe,open,high,low,close,volume"]
    for index, price in enumerate([100, 101, 102, 103, 104, 105]):
        rows.append(
            f"{(START + timedelta(minutes=index)).isoformat()},TEST_FX,1m,"
            f"{price},{price + 1},{price - 1},{price},10"
        )
    return "\n".join(rows)


def _csv_prices(start_at: datetime, prices: list[float]) -> str:
    rows = ["timestamp,instrument,timeframe,open,high,low,close,volume"]
    for index, price in enumerate(prices):
        rows.append(
            f"{(start_at + timedelta(minutes=index)).isoformat()},TEST_FX,1m,"
            f"{price},{price + 1},{price - 1},{price},10"
        )
    return "\n".join(rows)


def _run_kwargs(dataset_id: str) -> dict[str, object]:
    return {
        "name": None,
        "notes": None,
        "strategy_identifier": "smoke_test_hold",
        "profile_name": "default",
        "strategy_parameters": {"warmup_ticks": 2, "hold_minutes": 0.5},
        "dataset_id": dataset_id,
        "shortlist": ["TEST_FX"],
        "timeframe": "1m",
        "start_at": START,
        "end_at": START + timedelta(minutes=6),
        "starting_capital": 1000,
        "position_sizing_mode": "FIXED_UNITS",
        "risk_configuration": {"fixed_size": 1, "max_open_positions": 1},
        "spread_model": "FIXED_BPS",
        "spread_assumption": {"value": 0},
        "slippage_model": "NONE",
        "slippage_assumption": {"value": 0},
        "fee_model": "NONE",
        "fee_assumption": {"value": 0},
        "open_position_treatment": "CLOSE_AT_END",
    }


def _multi_instrument_dataset(
    session,
    repository: JsonlHistoricalDataRepository,
    instruments: list[str],
):
    service = HistoricalDataService(session, repository=repository)
    dataset = service._start_dataset(
        display_name="multi-instrument fixture",
        provider="CSV",
        venue="TEST",
        market_type="SPOT_FX",
        asset_class="FOREX",
        timeframe="1m",
        import_parameters={
            "instruments": instruments,
            "start_at": START.isoformat(),
            "end_at": (START + timedelta(minutes=6)).isoformat(),
            "timeframe": "1m",
        },
    )
    prepared = []
    for instrument in instruments:
        candles = [
            HistoricalCandle(
                timestamp=START + timedelta(minutes=index),
                instrument=instrument,
                timeframe="1m",
                trade=PriceBar(
                    open=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                ),
                volume=10.0,
            )
            for index, price in enumerate([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        ]
        prepared.append(
            service._prepare_partition(
                dataset=dataset,
                instrument=instrument,
                provider_instrument=instrument,
                candles=candles,
                requested_start=START,
                requested_end=START + timedelta(minutes=6),
                requested_timeframe="1m",
                source_metadata={
                    "provider": "CSV",
                    "venue": "TEST",
                    "provider_instrument": instrument,
                },
            )
        )
    return service._publish_dataset(
        dataset=dataset,
        prepared=prepared,
        requested_instruments=instruments,
    )


def _completed_run(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    service = BacktestService(session, repository=repository)
    run = service.create_and_run(**_run_kwargs(dataset.id))
    assert run.status == BacktestRunStatus.COMPLETED.value
    assert run.result_checksum
    return service, run


def test_backtest_persists_results_without_mutating_live_trading_tables(
    session, tmp_path: Path, monkeypatch
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    monkeypatch.setattr(
        "app.backtesting.providers._load_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Replay must not call an external provider.")
        ),
    )

    run = BacktestService(session, repository=repository).create_and_run(
        name="deterministic fixture",
        notes=None,
        strategy_identifier="smoke_test_hold",
        profile_name="default",
        strategy_parameters={"warmup_ticks": 2, "hold_minutes": 0.5},
        dataset_id=dataset.id,
        shortlist=["TEST_FX"],
        timeframe="1m",
        start_at=START,
        end_at=START + timedelta(minutes=6),
        starting_capital=1000,
        position_sizing_mode="FIXED_UNITS",
        risk_configuration={"fixed_size": 1, "max_open_positions": 1},
        spread_model="FIXED_BPS",
        spread_assumption={"value": 0},
        slippage_model="NONE",
        slippage_assumption={"value": 0},
        fee_model="NONE",
        fee_assumption={"value": 0},
        open_position_treatment="CLOSE_AT_END",
    )

    assert run.status == BacktestRunStatus.COMPLETED.value
    assert session.exec(select(BacktestTrade)).all()
    assert session.exec(select(TradeIntent)).all() == []
    assert session.exec(select(Execution)).all() == []
    assert session.exec(select(Position)).all() == []
    assert session.exec(select(Trade)).all() == []


def test_identical_runs_produce_identical_metrics(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    service = BacktestService(session, repository=repository)
    kwargs = _run_kwargs(dataset.id)

    first = service.create_and_run(**kwargs)
    second = service.create_and_run(**kwargs)

    assert first.result_summary == second.result_summary
    assert first.result_summary["ending_equity"] == 1002
    assert first.result_summary["total_pnl"] == 2
    assert first.result_checksum == second.result_checksum
    service.verify_backtest_result_checksum(first.id)
    service.verify_backtest_result_checksum(second.id)


def test_strict_warmup_requires_dataset_coverage_before_trading_start(
    session, tmp_path: Path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    kwargs = _run_kwargs(dataset.id)
    kwargs.update(warmup_mode="CANDLE_COUNT", warmup_candle_count=2)
    service = BacktestService(session, repository=repository)

    run = service.create_and_run(**kwargs)

    assert run.status == BacktestRunStatus.FAILED.value
    assert "supplied 0 of 2 required warm-up candles" in str(run.failure_reason)
    assert run.warmup_sufficient is False
    assert run.warmup_degraded is False
    assert run.warmup_warnings[0]["code"] == "INSUFFICIENT_WARMUP"
    assert run.warmup_warnings[0]["severity"] == "ERROR"
    assert run.warmup_warnings[0]["instrument_id"] == "TEST_FX"
    assert run.warmup_warnings[0]["requested_warmup_candles"] == 2
    assert run.warmup_warnings[0]["available_warmup_candles"] == 0
    assert run.result_checksum is None
    assert service.metrics(run.id) == {"run": {}, "by_instrument": {}}
    assert service.trades(run.id) == []
    assert service.equity(run.id) == []


def test_strict_warmup_persists_diagnostics_for_every_requested_instrument(
    session, tmp_path: Path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = _multi_instrument_dataset(
        session,
        repository,
        ["ALPHA_FX", "BETA_FX"],
    )
    kwargs = _run_kwargs(dataset.id)
    kwargs.update(
        shortlist=["ALPHA_FX", "BETA_FX"],
        warmup_mode="CANDLE_COUNT",
        warmup_candle_count=2,
    )
    service = BacktestService(session, repository=repository)

    run = service.create_and_run(**kwargs)

    assert run.status == BacktestRunStatus.FAILED.value
    assert {warning["instrument_id"] for warning in run.warmup_warnings} == {
        "ALPHA_FX",
        "BETA_FX",
    }
    assert all(warning["severity"] == "ERROR" for warning in run.warmup_warnings)
    instruments = service.instruments(run.id)
    assert [item.instrument for item in instruments] == ["ALPHA_FX", "BETA_FX"]
    assert all(item.warmup_candles_consumed == 0 for item in instruments)
    assert all(item.first_tradable_at == START for item in instruments)
    assert all(item.metrics == {} for item in instruments)
    assert {warning.instrument for warning in service.warnings(run.id)} == {
        "ALPHA_FX",
        "BETA_FX",
    }
    assert (
        session.exec(
            select(BacktestMetric).where(BacktestMetric.run_id == run.id)
        ).all()
        == []
    )
    assert (
        session.exec(select(BacktestTrade).where(BacktestTrade.run_id == run.id)).all()
        == []
    )
    assert (
        session.exec(
            select(BacktestEquityPoint).where(BacktestEquityPoint.run_id == run.id)
        ).all()
        == []
    )


def test_allowed_insufficient_warmup_is_persisted_as_degraded(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    kwargs = _run_kwargs(dataset.id)
    kwargs.update(
        warmup_mode="CANDLE_COUNT",
        warmup_candle_count=2,
        allow_insufficient_warmup=True,
    )
    service = BacktestService(session, repository=repository)

    run = service.create_and_run(**kwargs)
    assert run.status == BacktestRunStatus.COMPLETED.value, run.failure_reason
    instrument = service.instruments(run.id)[0]

    assert run.warmup_sufficient is False
    assert run.warmup_degraded is True
    assert run.warmup_warnings[0]["code"] == "INSUFFICIENT_WARMUP"
    assert run.warmup_warnings[0]["severity"] == "WARNING"
    assert run.warmup_warnings[0]["instrument_id"] == "TEST_FX"
    assert instrument.warmup_candles_consumed == 0
    assert instrument.first_tradable_at == START
    assert any(
        warning.code == "INSUFFICIENT_WARMUP" for warning in service.warnings(run.id)
    )


def test_equivalent_selected_preroll_produces_same_trading_results(
    session, tmp_path: Path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    historical = HistoricalDataService(session, repository=repository)
    short_dataset = historical.import_csv(
        display_name="short pre-roll",
        csv_text=_csv_prices(
            START - timedelta(minutes=2),
            [98, 99, 100, 101, 102, 103, 104, 105],
        ),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    long_dataset = historical.import_csv(
        display_name="long pre-roll",
        csv_text=_csv_prices(
            START - timedelta(minutes=4),
            [10, 20, 98, 99, 100, 101, 102, 103, 104, 105],
        ),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    service = BacktestService(session, repository=repository)
    runs = []
    for dataset in (short_dataset, long_dataset):
        kwargs = _run_kwargs(dataset.id)
        kwargs.update(warmup_mode="CANDLE_COUNT", warmup_candle_count=2)
        runs.append(service.create_and_run(**kwargs))

    first_trades = [
        (
            trade.instrument,
            trade.direction,
            trade.open_time,
            trade.close_time,
            trade.open_price,
            trade.close_price,
            trade.net_pnl,
        )
        for trade in service.trades(runs[0].id)
    ]
    second_trades = [
        (
            trade.instrument,
            trade.direction,
            trade.open_time,
            trade.close_time,
            trade.open_price,
            trade.close_price,
            trade.net_pnl,
        )
        for trade in service.trades(runs[1].id)
    ]
    assert runs[0].result_summary == runs[1].result_summary
    assert first_trades == second_trades
    assert all(run.warmup_start_at == START - timedelta(minutes=2) for run in runs)


def test_result_checksum_changes_when_warmup_settings_change(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv_prices(
            START - timedelta(minutes=2),
            [98, 99, 100, 101, 102, 103, 104, 105],
        ),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    service = BacktestService(session, repository=repository)
    without_warmup = service.create_and_run(**_run_kwargs(dataset.id))
    kwargs = _run_kwargs(dataset.id)
    kwargs.update(warmup_mode="CANDLE_COUNT", warmup_candle_count=2)
    with_warmup = service.create_and_run(**kwargs)

    assert without_warmup.result_checksum != with_warmup.result_checksum
    service.verify_backtest_result_checksum(without_warmup.id)
    service.verify_backtest_result_checksum(with_warmup.id)


def test_result_manifest_schema_and_exclusions_are_explicit(session, tmp_path):
    service, run = _completed_run(session, tmp_path)
    manifest = service.canonical_result_manifest(run)

    assert (
        manifest["manifest_version"]
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["manifest_version"])
    )
    assert (
        manifest["accounting_model"]
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["accounting_model"])
    )
    assert tuple(manifest["run"]) == CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["run"]
    assert (
        tuple(manifest["trades"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["trade"])
    )
    assert (
        tuple(manifest["equity"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["equity"])
    )
    assert (
        tuple(manifest["metrics"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["metric"])
    )
    assert (
        tuple(manifest["warnings"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["warning"])
    )
    assert (
        tuple(manifest["instruments"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["instrument"])
    )
    assert BACKTEST_RESULT_PROJECTION_ONLY_FIELDS == {
        "run": (
            "id",
            "name",
            "notes",
            "created_at",
            "started_at",
            "completed_at",
        ),
        "trade": ("id", "run_id"),
        "equity": ("id", "run_id"),
        "metric": ("id", "run_id"),
        "warning": ("id", "run_id", "created_at"),
        "instrument": ("id", "run_id", "dataset_partition_id"),
    }
    assert BACKTEST_RESULT_STATUS_CONSTRAINED_FIELDS == {"run": ("failure_reason",)}
    assert BACKTEST_RESULT_VERIFICATION_ENVELOPE_FIELDS == {
        "run": ("result_manifest_version", "result_checksum")
    }
    service.verify_backtest_result_checksum(run.id)


def test_manifest_v1_and_v2_completed_results_both_verify(session, tmp_path):
    service, run = _completed_run(session, tmp_path)

    assert run.result_manifest_version == BACKTEST_RESULT_MANIFEST_V2
    service.verify_backtest_result_checksum(run.id)

    v1_manifest = service.canonical_result_manifest(
        run,
        manifest_version=BACKTEST_RESULT_MANIFEST_V1,
    )
    assert (
        tuple(v1_manifest["run"])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_V1_SCHEMA["run"])
    )
    assert (
        tuple(v1_manifest["instruments"][0])
        == (CANONICAL_BACKTEST_RESULT_MANIFEST_V1_SCHEMA["instrument"])
    )
    run.result_manifest_version = BACKTEST_RESULT_MANIFEST_V1
    run.result_checksum = service.result_checksum(
        run,
        manifest_version=BACKTEST_RESULT_MANIFEST_V1,
    )
    session.add(run)
    session.commit()

    service.verify_backtest_result_checksum(run.id)


def test_result_verifier_rejects_unknown_or_corrupted_manifest_version(
    session, tmp_path
):
    service, run = _completed_run(session, tmp_path)
    run.result_manifest_version = "BACKTEST_RESULT_MANIFEST_V999"
    session.add(run)
    session.commit()

    with pytest.raises(ValueError, match="manifest version is unsupported"):
        service.verify_backtest_result_checksum(run.id)

    run.result_manifest_version = BACKTEST_RESULT_MANIFEST_V1
    run.result_checksum = "0" * 64
    session.add(run)
    session.commit()

    with pytest.raises(ValueError, match="checksum mismatch"):
        service.verify_backtest_result_checksum(run.id)


def _mutated_value(field: str, value):
    if field == "status":
        return BacktestRunStatus.FAILED.value
    if field == "result_summary":
        return {**value, "total_pnl": float(value["total_pnl"]) + 1}
    if field in {
        "strategy_configuration",
        "risk_configuration",
        "spread_assumption",
        "slippage_assumption",
        "fee_assumption",
        "details",
        "metrics",
    }:
        return {**value, "mutation": True}
    if field == "shortlist":
        return [*value, "MUTATED"]
    if field in {
        "requested_start_at",
        "requested_end_at",
        "effective_start_at",
        "effective_end_at",
        "warmup_start_at",
        "trading_start_at",
        "first_tradable_at",
        "open_time",
        "close_time",
        "timestamp",
    }:
        return (value or START) + timedelta(seconds=1)
    if field == "conservative_ambiguity":
        return not value
    if field in {"stop_loss_price", "take_profit_price"}:
        return 99.0 if value is None else value + 1
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value + 1
    if value is None:
        return "MUTATED"
    return f"{value}-MUTATED"


RESULT_ENTITY_FIELDS = [
    ("run", field) for field in CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA["run"]
] + [
    (entity, field)
    for entity in ("trade", "equity", "metric", "warning", "instrument")
    for field in CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA[entity]
]


@pytest.mark.parametrize(("entity", "manifest_field"), RESULT_ENTITY_FIELDS)
def test_public_result_verifier_rejects_every_authoritative_field_mutation(
    session, tmp_path, entity: str, manifest_field: str
):
    service, run = _completed_run(session, tmp_path)
    model_and_query = {
        "run": (BacktestRun, run),
        "trade": (BacktestTrade, service.trades(run.id)[0]),
        "equity": (BacktestEquityPoint, service.equity(run.id)[0]),
        "metric": (BacktestMetric, service._metric_rows(run.id)[0]),
        "warning": (BacktestWarning, service.warnings(run.id)[0]),
        "instrument": (BacktestRunInstrument, service.instruments(run.id)[0]),
    }
    _model, row = model_and_query[entity]
    source_field = (
        "unrealized_pnl"
        if entity == "equity" and manifest_field == "unrealised_pnl"
        else manifest_field
    )
    setattr(row, source_field, _mutated_value(source_field, getattr(row, source_field)))
    session.add(row)
    session.commit()
    session.expire_all()

    with pytest.raises(ValueError):
        service.verify_backtest_result_checksum(run.id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "display-only name"),
        ("notes", "display-only notes"),
        ("completed_at", START + timedelta(days=1)),
    ],
)
def test_projection_only_run_fields_do_not_change_result_verification(
    session, tmp_path, field: str, value
):
    service, run = _completed_run(session, tmp_path)
    setattr(run, field, value)
    session.add(run)
    session.commit()
    session.expire_all()

    service.verify_backtest_result_checksum(run.id)


def test_completed_run_failure_reason_mutation_fails_verification(session, tmp_path):
    service, run = _completed_run(session, tmp_path)
    run.failure_reason = "false operator-visible failure"
    session.add(run)
    session.commit()

    with pytest.raises(
        ValueError,
        match="Completed backtest result cannot have a failure reason",
    ):
        service.verify_backtest_result_checksum(run.id)


def test_failed_run_has_explicit_failure_truth_without_completed_manifest(
    session, tmp_path, monkeypatch
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    monkeypatch.setattr(
        "app.services.backtest_service.BacktestReplayEngine.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("deterministic replay failure")
        ),
    )
    service = BacktestService(session, repository=repository)

    run = service.create_and_run(**_run_kwargs(dataset.id))

    assert run.status == BacktestRunStatus.FAILED.value
    assert run.failure_reason == "deterministic replay failure"
    assert run.result_manifest_version is None
    assert run.result_checksum is None
    assert run.result_summary == {}
    with pytest.raises(ValueError, match="Only completed"):
        service.verify_backtest_result_checksum(run.id)


def test_same_result_in_independent_databases_has_same_checksum(
    tmp_path, migrated_sqlite_template: str
):
    seed_path = tmp_path / "seed.sqlite"
    shutil.copyfile(migrated_sqlite_template, seed_path)
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    seed_engine = create_engine(f"sqlite:///{seed_path}")
    with Session(seed_engine) as seed_session:
        dataset = HistoricalDataService(seed_session, repository=repository).import_csv(
            display_name="fixture",
            csv_text=_csv(),
            asset_class="FOREX",
            venue="TEST",
            market_type="SPOT_FX",
        )
        dataset_id = dataset.id
    seed_engine.dispose()

    checksums = []
    run_ids = []
    for database_name in ("first.sqlite", "second.sqlite"):
        database_path = tmp_path / database_name
        shutil.copyfile(seed_path, database_path)
        engine = create_engine(f"sqlite:///{database_path}")
        with Session(engine) as independent_session:
            service = BacktestService(independent_session, repository=repository)
            run = service.create_and_run(**_run_kwargs(dataset_id))
            service.verify_backtest_result_checksum(run.id)
            checksums.append(run.result_checksum)
            run_ids.append(run.id)
        engine.dispose()

    assert run_ids[0] != run_ids[1]
    assert checksums[0] == checksums[1]


def test_ready_dataset_orm_update_is_blocked(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    dataset.venue = "MUTATED"
    session.add(dataset)

    with pytest.raises(IntegrityError, match="historical datasets are immutable"):
        session.commit()
    session.rollback()


def test_ready_dataset_operational_availability_update_is_allowed(
    session, tmp_path: Path
):
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    )
    dataset = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    original_checksum = dataset.checksum
    dataset.availability = DatasetAvailability.RECOVERY_REQUIRED.value
    dataset.availability_reason = "partition verification failed"
    dataset.availability_updated_at = datetime.now(UTC)
    session.add(dataset)
    session.commit()
    session.expire_all()

    reloaded = service.get_dataset(dataset.id)
    assert reloaded.status == "READY"
    assert reloaded.checksum == original_checksum
    assert reloaded.availability == "RECOVERY_REQUIRED"
    assert service.dataset_is_selectable(dataset.id) is False


def test_backtest_creation_rejects_recovery_required_dataset_before_run_persistence(
    session, tmp_path: Path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    dataset.availability = DatasetAvailability.RECOVERY_REQUIRED.value
    dataset.availability_reason = "ambiguous publication requires operator recovery"
    dataset.availability_updated_at = datetime.now(UTC)
    session.add(dataset)
    session.commit()

    with pytest.raises(ValueError, match="is not available"):
        BacktestService(session, repository=repository).create_and_run(
            name=None,
            notes=None,
            strategy_identifier="smoke_test_hold",
            profile_name="default",
            strategy_parameters={"warmup_ticks": 2, "hold_minutes": 0.5},
            dataset_id=dataset.id,
            shortlist=["TEST_FX"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(minutes=6),
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 1},
            spread_model="FIXED_BPS",
            spread_assumption={"value": 0},
            slippage_model="NONE",
            slippage_assumption={"value": 0},
            fee_model="NONE",
            fee_assumption={"value": 0},
            open_position_treatment="CLOSE_AT_END",
        )

    assert session.exec(select(BacktestRun)).all() == []


def test_ready_dataset_orm_delete_is_blocked(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    service = HistoricalDataService(session, repository=repository)
    dataset = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )

    with pytest.raises(ValueError, match="append-only"):
        service.delete_dataset(dataset.id)

    session.delete(dataset)
    with pytest.raises(IntegrityError, match="historical datasets are immutable"):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE historical_dataset SET venue = 'MUTATED' WHERE id = :dataset_id",
        "DELETE FROM historical_dataset WHERE id = :dataset_id",
        (
            "UPDATE historical_dataset_partition SET candle_count = 1 "
            "WHERE dataset_id = :dataset_id"
        ),
        "DELETE FROM historical_dataset_partition WHERE dataset_id = :dataset_id",
    ],
)
def test_ready_dataset_direct_sql_mutation_and_deletion_are_blocked(
    session, tmp_path: Path, statement: str
):
    dataset = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    ).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )

    with pytest.raises(IntegrityError, match="immutable"):
        session.execute(text(statement), {"dataset_id": dataset.id})
        session.commit()
    session.rollback()


def _mutable_dataset_and_partition(session, ready_partition):
    mutable_dataset = HistoricalDataset(
        id="mutable-dataset",
        display_name="mutable",
        provider="CSV",
        venue="TEST",
        market_type="SPOT_FX",
        asset_class="FOREX",
        base_timeframe="1m",
        status="IMPORTING",
        immutable=False,
    )
    mutable_partition = HistoricalDatasetPartition(
        **{
            **ready_partition.model_dump(exclude={"id", "dataset_id"}),
            "dataset_id": mutable_dataset.id,
        }
    )
    session.add(mutable_dataset)
    session.add(mutable_partition)
    session.commit()
    session.refresh(mutable_partition)
    return mutable_dataset, mutable_partition


@pytest.mark.parametrize("direction", ["INTO_READY", "OUT_OF_READY"])
def test_ready_partition_direct_sql_reparenting_is_blocked(
    session, tmp_path: Path, direction: str
):
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    )
    ready = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    ready_partition = service.list_partitions(ready.id)[0]
    mutable, mutable_partition = _mutable_dataset_and_partition(
        session, ready_partition
    )
    partition_id, target_dataset_id = (
        (mutable_partition.id, ready.id)
        if direction == "INTO_READY"
        else (ready_partition.id, mutable.id)
    )

    with pytest.raises(IntegrityError, match="partitions are immutable"):
        session.execute(
            text(
                "UPDATE historical_dataset_partition "
                "SET dataset_id = :target_dataset_id WHERE id = :partition_id"
            ),
            {
                "target_dataset_id": target_dataset_id,
                "partition_id": partition_id,
            },
        )
        session.commit()
    session.rollback()


@pytest.mark.parametrize("direction", ["INTO_READY", "OUT_OF_READY"])
def test_ready_partition_orm_reparenting_is_blocked(
    session, tmp_path: Path, direction: str
):
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    )
    ready = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    ready_partition = service.list_partitions(ready.id)[0]
    mutable, mutable_partition = _mutable_dataset_and_partition(
        session, ready_partition
    )
    partition = mutable_partition if direction == "INTO_READY" else ready_partition
    partition.dataset_id = ready.id if direction == "INTO_READY" else mutable.id
    session.add(partition)

    with pytest.raises(IntegrityError, match="partitions are immutable"):
        session.commit()
    session.rollback()


def _manifest_fixture(session, tmp_path: Path):
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    )
    dataset = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
        source_identifier="fixture.csv",
        source_metadata={"source": "test"},
    )
    partitions = service.list_partitions(dataset.id)
    assert dataset.checksum
    return service, dataset, partitions


def _dataset_manifest_mutations(dataset):
    start_parameters = dict(dataset.import_parameters)
    start_parameters["start_at"] = (
        datetime.fromisoformat(str(start_parameters["start_at"])) + timedelta(minutes=1)
    ).isoformat()
    end_parameters = dict(dataset.import_parameters)
    end_parameters["end_at"] = (
        datetime.fromisoformat(str(end_parameters["end_at"])) + timedelta(minutes=1)
    ).isoformat()
    import_parameters = dict(dataset.import_parameters)
    import_parameters["row_count"] = int(import_parameters["row_count"]) + 1
    return {
        "id": ("id", "mutated-dataset-id"),
        "display_name": ("display_name", "mutated"),
        "provider": ("provider", "MUTATED"),
        "source_identifier": ("source_identifier", "mutated.csv"),
        "venue": ("venue", "MUTATED"),
        "market_type": ("market_type", "MUTATED"),
        "asset_class": ("asset_class", "MUTATED"),
        "base_timeframe": ("base_timeframe", "5m"),
        "status": ("status", "PARTIAL"),
        "requested_start_at": ("import_parameters", start_parameters),
        "requested_end_at": ("import_parameters", end_parameters),
        "actual_earliest_at": (
            "earliest_at",
            dataset.earliest_at + timedelta(minutes=1),
        ),
        "actual_latest_at": (
            "latest_at",
            dataset.latest_at + timedelta(minutes=1),
        ),
        "candle_count": ("candle_count", dataset.candle_count + 1),
        "price_components": ("price_components", ["bid"]),
        "volume_available": ("volume_available", not dataset.volume_available),
        "imported_at": ("imported_at", dataset.imported_at + timedelta(minutes=1)),
        "timezone_rule": ("timezone_rule", "LOCAL"),
        "completeness_status": ("completeness_status", "UNKNOWN"),
        "detected_gaps": ("detected_gaps", [{"code": "MUTATED"}]),
        "warnings": ("warnings", [{"code": "MUTATED"}]),
        "source_metadata": ("source_metadata", {"source": "mutated"}),
        "import_parameters": ("import_parameters", import_parameters),
        "failure_reason": ("failure_reason", "mutated"),
        "storage_format": ("storage_format", "MUTATED"),
        "immutable": ("immutable", False),
    }


def _partition_manifest_mutations(partition):
    return {
        "id": ("id", (partition.id or 0) + 100),
        "dataset_id": ("dataset_id", "mutated-dataset-id"),
        "instrument": ("instrument", "MUTATED"),
        "provider_instrument": ("provider_instrument", "MUTATED"),
        "timeframe": ("timeframe", "5m"),
        "earliest_at": (
            "earliest_at",
            partition.earliest_at + timedelta(minutes=1),
        ),
        "latest_at": ("latest_at", partition.latest_at + timedelta(minutes=1)),
        "candle_count": ("candle_count", partition.candle_count + 1),
        "price_components": ("price_components", ["bid"]),
        "volume_available": ("volume_available", not partition.volume_available),
        "partition_hash": ("checksum", "0" * 64),
        "storage_path": ("storage_path", "mutated/path.jsonl.gz"),
        "detected_gaps": ("detected_gaps", [{"code": "MUTATED"}]),
        "warnings": ("warnings", [{"code": "MUTATED"}]),
        "source_metadata": ("source_metadata", {"provider": "MUTATED"}),
    }


def test_canonical_manifest_schema_is_explicit_and_deterministic(session, tmp_path):
    service, dataset, partitions = _manifest_fixture(session, tmp_path)
    manifest = service.canonical_dataset_manifest(dataset, partitions)

    assert tuple(manifest["dataset"]) == CANONICAL_DATASET_MANIFEST_SCHEMA["dataset"]
    assert (
        tuple(manifest["partitions"][0])
        == (CANONICAL_DATASET_MANIFEST_SCHEMA["partition"])
    )
    assert (
        manifest["manifest_version"]
        == (CANONICAL_DATASET_MANIFEST_SCHEMA["manifest_version"])
    )
    assert service.dataset_checksum(dataset, partitions) == dataset.checksum
    assert service.dataset_checksum(dataset, list(reversed(partitions))) == (
        dataset.checksum
    )
    assert MANIFEST_PROJECTION_ONLY_FIELDS == {
        "dataset": ("partitions",),
        "partition": (),
    }
    assert MANIFEST_VERIFICATION_ENVELOPE_FIELDS == {
        "dataset": ("checksum",),
        "partition": (),
    }
    assert MANIFEST_OPERATIONAL_FIELDS == {
        "dataset": (
            "availability",
            "availability_reason",
            "availability_updated_at",
        ),
        "partition": (),
    }


@pytest.mark.parametrize(
    "manifest_field",
    AUTHORITATIVE_DATASET_MANIFEST_FIELDS,
)
def test_public_verifier_rejects_authoritative_dataset_field_mutation(
    session, tmp_path, monkeypatch, manifest_field
):
    service, dataset, partitions = _manifest_fixture(session, tmp_path)
    mutations = _dataset_manifest_mutations(dataset)
    assert set(mutations) == set(AUTHORITATIVE_DATASET_MANIFEST_FIELDS)

    mutated = HistoricalDataset(**dataset.model_dump())
    source_field, value = mutations[manifest_field]
    setattr(mutated, source_field, value)
    with monkeypatch.context() as patch:
        patch.setattr(service, "get_dataset", lambda _dataset_id: mutated)
        patch.setattr(
            service,
            "list_partitions",
            lambda _dataset_id: partitions,
        )
        with pytest.raises(ValueError):
            service.verify_dataset_checksum(dataset.id)


@pytest.mark.parametrize(
    "manifest_field",
    AUTHORITATIVE_PARTITION_MANIFEST_FIELDS,
)
def test_public_verifier_rejects_authoritative_partition_field_mutation(
    session, tmp_path, monkeypatch, manifest_field
):
    service, dataset, partitions = _manifest_fixture(session, tmp_path)
    mutations = _partition_manifest_mutations(partitions[0])
    assert set(mutations) == set(AUTHORITATIVE_PARTITION_MANIFEST_FIELDS)

    mutated = HistoricalDatasetPartition(**partitions[0].model_dump())
    source_field, value = mutations[manifest_field]
    setattr(mutated, source_field, value)
    with monkeypatch.context() as patch:
        patch.setattr(
            service,
            "list_partitions",
            lambda _dataset_id: [mutated],
        )
        with pytest.raises(ValueError):
            service.verify_dataset_checksum(dataset.id)


def test_manifest_excludes_checksum_envelope_but_public_verifier_checks_it(
    session, tmp_path, monkeypatch
):
    service, dataset, partitions = _manifest_fixture(session, tmp_path)
    mutated = HistoricalDataset(**dataset.model_dump())
    mutated.checksum = "0" * 64

    assert service.dataset_checksum(mutated, partitions) == dataset.checksum
    with monkeypatch.context() as patch:
        patch.setattr(service, "get_dataset", lambda _dataset_id: mutated)
        with pytest.raises(ValueError, match="checksum mismatch"):
            service.verify_dataset_checksum(dataset.id)


def test_dataset_timestamps_round_trip_as_utc_aware(session, tmp_path: Path):
    service = HistoricalDataService(
        session,
        repository=JsonlHistoricalDataRepository(tmp_path / "history"),
    )
    dataset = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    session.expire_all()

    reloaded = service.get_dataset(dataset.id)
    partition = session.exec(
        select(HistoricalDatasetPartition).where(
            HistoricalDatasetPartition.dataset_id == dataset.id
        )
    ).one()

    for value in (
        reloaded.imported_at,
        reloaded.availability_updated_at,
        reloaded.earliest_at,
        reloaded.latest_at,
        partition.earliest_at,
        partition.latest_at,
    ):
        assert value is not None
        assert value.utcoffset() == timedelta(0)


def test_unknown_strategy_parameters_are_rejected_not_silently_ignored(
    session, tmp_path: Path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = HistoricalDataService(session, repository=repository).import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )

    with pytest.raises(ValueError, match="Unknown strategy parameters"):
        BacktestService(session, repository=repository).create_and_run(
            name=None,
            notes=None,
            strategy_identifier="smoke_test_hold",
            profile_name="default",
            strategy_parameters={"not_a_real_parameter": 1},
            dataset_id=dataset.id,
            shortlist=["TEST_FX"],
            timeframe="1m",
            start_at=START,
            end_at=START + timedelta(minutes=6),
            starting_capital=1000,
            position_sizing_mode="FIXED_UNITS",
            risk_configuration={"fixed_size": 1, "max_open_positions": 1},
            spread_model="FIXED_BPS",
            spread_assumption={"value": 0},
            slippage_model="NONE",
            slippage_assumption={"value": 0},
            fee_model="NONE",
            fee_assumption={"value": 0},
            open_position_treatment="CLOSE_AT_END",
        )
