from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import select

from app.backtesting.storage import JsonlHistoricalDataRepository
from app.models.backtest import BacktestRunStatus, BacktestTrade
from app.models.trade import Execution, Position, Trade, TradeIntent
from app.services.backtest_service import BacktestService
from app.services.historical_data_service import HistoricalDataService


START = datetime(2026, 1, 1, tzinfo=UTC)


def _csv() -> str:
    rows = ["timestamp,instrument,timeframe,open,high,low,close,volume"]
    for index, price in enumerate([100, 101, 102, 103, 104, 105]):
        rows.append(
            f"{(START + timedelta(minutes=index)).isoformat()},TEST_FX,1m,"
            f"{price},{price + 1},{price - 1},{price},10"
        )
    return "\n".join(rows)


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
    kwargs = {
        "name": None,
        "notes": None,
        "strategy_identifier": "smoke_test_hold",
        "profile_name": "default",
        "strategy_parameters": {"warmup_ticks": 2, "hold_minutes": 0.5},
        "dataset_id": dataset.id,
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

    first = service.create_and_run(**kwargs)
    second = service.create_and_run(**kwargs)

    assert first.result_summary == second.result_summary
    assert first.result_summary["ending_capital"] == 1002


def test_dataset_provenance_mutation_is_detected_before_replay(session, tmp_path: Path):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    service = HistoricalDataService(session, repository=repository)
    dataset = service.import_csv(
        display_name="fixture",
        csv_text=_csv(),
        asset_class="FOREX",
        venue="TEST",
        market_type="SPOT_FX",
    )
    dataset.venue = "MUTATED"
    session.add(dataset)
    session.commit()

    with pytest.raises(ValueError, match="dataset checksum mismatch"):
        service.verify_dataset_checksum(dataset.id)


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
