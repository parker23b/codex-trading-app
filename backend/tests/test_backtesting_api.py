from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlmodel import select

from app.api.contracts.backtesting import UtcDateTime
from app.backtesting.candles import HistoricalCandle, PriceBar
from app.backtesting.storage import JsonlHistoricalDataRepository
from app.models.backtest import (
    BacktestEquityPoint,
    BacktestMetric,
    BacktestRun,
    BacktestTrade,
    DatasetAvailability,
    HistoricalDataset,
)
from app.services.backtest_service import BacktestService
from app.services.historical_data_service import HistoricalDataService


AUTH = {"Authorization": "Bearer expected-token"}
START = datetime(2026, 1, 1, tzinfo=UTC)


def _csv() -> str:
    rows = ["timestamp,instrument,timeframe,open,high,low,close,volume"]
    for index, price in enumerate([100, 101, 102, 103, 104, 105]):
        rows.append(
            f"{(START + timedelta(minutes=index)).isoformat()},TEST_FX,1m,"
            f"{price},{price + 1},{price - 1},{price},10"
        )
    return "\n".join(rows)


def _backtest_payload(
    dataset_id: str,
    *,
    shortlist: list[str] | None = None,
    warmup_mode: str = "NONE",
    warmup_candle_count: int = 0,
    allow_insufficient_warmup: bool = False,
) -> dict[str, object]:
    return {
        "strategy_identifier": "smoke_test_hold",
        "profile_name": "default",
        "strategy_parameters": {
            "warmup_ticks": 2,
            "hold_minutes": 0.5,
        },
        "dataset_id": dataset_id,
        "shortlist": shortlist or ["TEST_FX"],
        "timeframe": "1m",
        "start_at": START.isoformat(),
        "end_at": (START + timedelta(minutes=6)).isoformat(),
        "warmup_mode": warmup_mode,
        "warmup_candle_count": warmup_candle_count,
        "allow_insufficient_warmup": allow_insufficient_warmup,
        "starting_capital": 1000,
        "position_sizing_mode": "FIXED_UNITS",
        "risk_configuration": {
            "fixed_size": 1,
            "max_open_positions": 1,
        },
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
        display_name="multi-instrument API fixture",
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


def test_backtesting_response_timestamp_contract_rejects_naive_values():
    adapter = TypeAdapter(UtcDateTime)

    with pytest.raises(ValidationError, match="timezone-aware"):
        adapter.validate_python("2026-01-01T00:00:00")

    serialized = adapter.dump_json(
        adapter.validate_python("2026-01-01T00:00:00+00:00")
    ).decode()
    assert serialized.endswith('Z"') or serialized.endswith('+00:00"')


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/historical-data/imports",
            {
                "display_name": "naive provider range",
                "provider_id": "UNKNOWN",
                "instruments": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": "2026-01-01T00:00:00",
                "end_at": "2026-01-01T00:01:00",
                "asset_class": "FOREX",
                "market_type": "SPOT_FX",
            },
        ),
        (
            "/backtests",
            {
                "strategy_identifier": "smoke_test_hold",
                "dataset_id": "missing",
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": "2026-01-01T00:00:00",
                "end_at": "2026-01-01T00:01:00",
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {"fixed_size": 1},
                "spread_model": "FIXED_BPS",
                "spread_assumption": {"value": 0},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
        ),
    ],
)
def test_mutation_routes_reject_naive_request_timestamps(
    client_factory, tmp_path, path, payload
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        response = client.post(path, headers=AUTH, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "payload", "expected_detail"),
    [
        (
            "/historical-data/imports",
            {
                "display_name": "offset provider range",
                "provider_id": "UNKNOWN",
                "instruments": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": "2026-01-01T00:00:00+01:00",
                "end_at": "2026-01-01T00:01:00+01:00",
                "asset_class": "FOREX",
                "market_type": "SPOT_FX",
            },
            "not configured",
        ),
        (
            "/backtests",
            {
                "strategy_identifier": "smoke_test_hold",
                "dataset_id": "missing",
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": "2026-01-01T00:00:00+01:00",
                "end_at": "2026-01-01T00:01:00+01:00",
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {"fixed_size": 1},
                "spread_model": "FIXED_BPS",
                "spread_assumption": {"value": 0},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
            "was not found",
        ),
    ],
)
def test_mutation_routes_accept_offset_bearing_request_timestamps(
    client_factory, tmp_path, path, payload, expected_detail
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        response = client.post(path, headers=AUTH, json=payload)

    assert response.status_code == 400
    assert expected_detail in str(response.json())


def test_typed_dataset_and_backtest_route_flow(client_factory, session, tmp_path):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        providers = client.get("/historical-data/providers")
        assert providers.status_code == 200
        assert {item["provider_id"] for item in providers.json()} == {
            "BINANCE",
            "CSV",
            "IG",
            "OANDA",
        }

        imported = client.post(
            "/historical-data/imports/csv",
            headers=AUTH,
            json={
                "display_name": "API fixture",
                "csv_text": _csv(),
                "asset_class": "FOREX",
                "venue": "TEST",
                "market_type": "SPOT_FX",
            },
        )
        assert imported.status_code == 201
        dataset = imported.json()
        assert dataset["immutable"] is True
        assert dataset["availability"] == "AVAILABLE"
        assert dataset["selectable"] is True
        assert dataset["checksum"]
        assert dataset["partitions"][0]["instrument"] == "TEST_FX"
        for timestamp in (
            dataset["earliest_at"],
            dataset["latest_at"],
            dataset["imported_at"],
            dataset["availability_updated_at"],
            dataset["partitions"][0]["earliest_at"],
            dataset["partitions"][0]["latest_at"],
        ):
            assert re.search(r"(?:Z|[+-]00:00)$", timestamp)

        created = client.post(
            "/backtests",
            headers=AUTH,
            json={
                "strategy_identifier": "smoke_test_hold",
                "profile_name": "default",
                "strategy_parameters": {
                    "warmup_ticks": 2,
                    "hold_minutes": 0.5,
                },
                "dataset_id": dataset["id"],
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": START.isoformat(),
                "end_at": (START + timedelta(minutes=6)).isoformat(),
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {
                    "fixed_size": 1,
                    "max_open_positions": 1,
                },
                "spread_model": "FIXED_BPS",
                "spread_assumption": {"value": 0},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
        )
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "COMPLETED"
        assert run["evaluation_boundary"] == "CANDLE_CLOSE_NEXT_OPEN"
        assert run["result_manifest_version"] == "BACKTEST_RESULT_MANIFEST_V2"
        assert run["result_checksum"]
        assert run["warmup_mode"] == "NONE"
        assert run["warmup_candle_count"] == 0
        assert run["warmup_start_at"] == run["trading_start_at"]
        assert run["warmup_sufficient"] is True
        assert run["warmup_degraded"] is False
        assert run["warmup_warnings"] == []
        for field_name in (
            "requested_start_at",
            "requested_end_at",
            "warmup_start_at",
            "trading_start_at",
            "effective_start_at",
            "effective_end_at",
            "created_at",
            "started_at",
            "completed_at",
        ):
            assert re.search(r"(?:Z|[+-]00:00)$", run[field_name])

        metrics = client.get(f"/backtests/{run['id']}/metrics")
        trades = client.get(f"/backtests/{run['id']}/trades")
        equity = client.get(f"/backtests/{run['id']}/equity")
        warnings = client.get(f"/backtests/{run['id']}/warnings")
        instruments = client.get(f"/backtests/{run['id']}/instruments")

        assert metrics.status_code == 200
        run_metrics = metrics.json()["run"]
        assert run_metrics["closed_trade_count"] == 2
        assert run_metrics["realised_pnl"] == 2
        assert run_metrics["unrealised_pnl"] == 0
        assert run_metrics["total_pnl"] == 2
        assert run_metrics["ending_equity"] == 1002
        assert run_metrics["account_currency"] is None
        assert run_metrics["monetary_unit_label"] == "account units"
        assert run_metrics["profit_factor_null_reason"] == "NO_LOSING_TRADES"
        assert "closed_trade_net_winning_pnl" in run_metrics
        assert "closed_trade_net_losing_pnl" in run_metrics
        assert "closed_trade_gross_profit" not in run_metrics
        assert "closed_trade_gross_loss" not in run_metrics
        assert "ending_capital" not in run_metrics
        assert "net_pnl" not in run_metrics
        assert trades.status_code == 200
        assert [row["deterministic_sequence"] for row in trades.json()] == [1, 2]
        assert equity.status_code == 200
        assert len(equity.json()) == 6
        assert [row["timestamp"] for row in equity.json()] == sorted(
            row["timestamp"] for row in equity.json()
        )
        assert all(
            re.search(r"(?:Z|[+-]00:00)$", row["timestamp"]) for row in equity.json()
        )
        assert all("unrealised_pnl" in row for row in equity.json())
        assert all("unrealized_pnl" not in row for row in equity.json())
        assert warnings.status_code == 200
        assert [row["deterministic_sequence"] for row in warnings.json()] == list(
            range(1, len(warnings.json()) + 1)
        )
        assert instruments.status_code == 200
        assert [row["instrument"] for row in instruments.json()] == sorted(
            row["instrument"] for row in instruments.json()
        )
        assert instruments.json()[0]["warmup_candles_consumed"] == 0
        assert instruments.json()[0]["first_tradable_at"] == run["trading_start_at"]

        persisted_run = session.get(BacktestRun, run["id"])
        assert persisted_run is not None
        manifest = BacktestService(
            session,
            repository=JsonlHistoricalDataRepository(tmp_path / "history"),
        ).canonical_result_manifest(persisted_run)
        assert [row["deterministic_sequence"] for row in trades.json()] == [
            row["deterministic_sequence"] for row in manifest["trades"]
        ]
        assert [row["timestamp"] for row in equity.json()] == [
            row["timestamp"] for row in manifest["equity"]
        ]
        assert [row["deterministic_sequence"] for row in warnings.json()] == [
            row["deterministic_sequence"] for row in manifest["warnings"]
        ]
        assert [row["instrument"] for row in instruments.json()] == [
            row["instrument"] for row in manifest["instruments"]
        ]


def test_degraded_candle_count_warmup_api_exposes_typed_warning(
    client_factory, tmp_path
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        imported = client.post(
            "/historical-data/imports/csv",
            headers=AUTH,
            json={
                "display_name": "Degraded warm-up fixture",
                "csv_text": _csv(),
                "asset_class": "FOREX",
                "venue": "TEST",
                "market_type": "SPOT_FX",
            },
        )
        created = client.post(
            "/backtests",
            headers=AUTH,
            json=_backtest_payload(
                imported.json()["id"],
                warmup_mode="CANDLE_COUNT",
                warmup_candle_count=2,
                allow_insufficient_warmup=True,
            ),
        )

    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "COMPLETED"
    assert run["warmup_degraded"] is True
    assert run["warmup_warnings"] == [
        {
            "code": "INSUFFICIENT_WARMUP",
            "severity": "WARNING",
            "instrument_id": "TEST_FX",
            "requested_warmup_candles": 2,
            "available_warmup_candles": 0,
            "message": "TEST_FX supplied 0 of 2 required warm-up candles.",
            "first_available_at": None,
            "trading_start_at": START.isoformat().replace("+00:00", "Z"),
        }
    ]


def test_strict_multi_instrument_warmup_failure_is_observable_without_analytics(
    client_factory, session, tmp_path
):
    repository = JsonlHistoricalDataRepository(tmp_path / "history")
    dataset = _multi_instrument_dataset(
        session,
        repository,
        ["ALPHA_FX", "BETA_FX"],
    )
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        created = client.post(
            "/backtests",
            headers=AUTH,
            json=_backtest_payload(
                dataset.id,
                shortlist=["ALPHA_FX", "BETA_FX"],
                warmup_mode="CANDLE_COUNT",
                warmup_candle_count=2,
            ),
        )
        assert created.status_code == 201
        run_id = created.json()["id"]
        detail = client.get(f"/backtests/{run_id}")
        warnings = client.get(f"/backtests/{run_id}/warnings")
        instruments = client.get(f"/backtests/{run_id}/instruments")
        analytics = {
            suffix: client.get(f"/backtests/{run_id}/{suffix}")
            for suffix in ("metrics", "trades", "equity")
        }

    assert detail.status_code == 200
    run = detail.json()
    assert run["status"] == "FAILED"
    assert "ALPHA_FX supplied 0 of 2" in run["failure_reason"]
    assert "BETA_FX supplied 0 of 2" in run["failure_reason"]
    assert {warning["instrument_id"] for warning in run["warmup_warnings"]} == {
        "ALPHA_FX",
        "BETA_FX",
    }
    assert all(warning["severity"] == "ERROR" for warning in run["warmup_warnings"])
    assert warnings.status_code == 200
    assert {warning["instrument"] for warning in warnings.json()} == {
        "ALPHA_FX",
        "BETA_FX",
    }
    assert instruments.status_code == 200
    assert [item["instrument"] for item in instruments.json()] == [
        "ALPHA_FX",
        "BETA_FX",
    ]
    assert all(item["metrics"] is None for item in instruments.json())
    assert all(
        item["first_tradable_at"] == START.isoformat().replace("+00:00", "Z")
        for item in instruments.json()
    )
    assert all(response.status_code == 409 for response in analytics.values())
    assert (
        session.exec(
            select(BacktestMetric).where(BacktestMetric.run_id == run_id)
        ).all()
        == []
    )
    assert (
        session.exec(select(BacktestTrade).where(BacktestTrade.run_id == run_id)).all()
        == []
    )
    assert (
        session.exec(
            select(BacktestEquityPoint).where(BacktestEquityPoint.run_id == run_id)
        ).all()
        == []
    )


def test_openapi_exposes_stable_warmup_warning_shape(client_factory, tmp_path):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        schema = client.get("/openapi.json").json()

    warning_schema = schema["components"]["schemas"]["BacktestWarmupWarningResponse"]
    assert set(warning_schema["required"]) == {
        "code",
        "severity",
        "instrument_id",
        "requested_warmup_candles",
        "available_warmup_candles",
        "message",
    }
    assert set(warning_schema["properties"]) == {
        "code",
        "severity",
        "instrument_id",
        "requested_warmup_candles",
        "available_warmup_candles",
        "message",
        "first_available_at",
        "trading_start_at",
    }


def test_api_rejects_checksum_valid_completed_run_with_false_failure_reason(
    client_factory, session, tmp_path
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        imported = client.post(
            "/historical-data/imports/csv",
            headers=AUTH,
            json={
                "display_name": "API fixture",
                "csv_text": _csv(),
                "asset_class": "FOREX",
                "venue": "TEST",
                "market_type": "SPOT_FX",
            },
        )
        created = client.post(
            "/backtests",
            headers=AUTH,
            json={
                "strategy_identifier": "smoke_test_hold",
                "profile_name": "default",
                "strategy_parameters": {
                    "warmup_ticks": 2,
                    "hold_minutes": 0.5,
                },
                "dataset_id": imported.json()["id"],
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": START.isoformat(),
                "end_at": (START + timedelta(minutes=6)).isoformat(),
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {
                    "fixed_size": 1,
                    "max_open_positions": 1,
                },
                "spread_model": "FIXED_BPS",
                "spread_assumption": {"value": 0},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
        )
        run = session.get(BacktestRun, created.json()["id"])
        assert run is not None
        original_checksum = run.result_checksum
        run.failure_reason = "false failure"
        session.add(run)
        session.commit()

        response = client.get(f"/backtests/{run.id}")

    assert run.result_checksum == original_checksum
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Backtest run has inconsistent persisted result state."
    )


def test_recovery_required_dataset_is_visible_but_not_selectable_or_replayable(
    client_factory, session, tmp_path
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        imported = client.post(
            "/historical-data/imports/csv",
            headers=AUTH,
            json={
                "display_name": "recovery fixture",
                "csv_text": _csv(),
                "asset_class": "FOREX",
                "venue": "TEST",
                "market_type": "SPOT_FX",
            },
        )
        assert imported.status_code == 201
        dataset_id = imported.json()["id"]
        dataset = session.get(HistoricalDataset, dataset_id)
        assert dataset is not None
        dataset.availability = DatasetAvailability.RECOVERY_REQUIRED.value
        dataset.availability_reason = "partition verification failed"
        dataset.availability_updated_at = datetime.now(UTC)
        session.add(dataset)
        session.commit()

        listed = client.get("/historical-data/datasets")
        assert listed.status_code == 200
        projection = next(item for item in listed.json() if item["id"] == dataset_id)
        assert projection["status"] == "READY"
        assert projection["availability"] == "RECOVERY_REQUIRED"
        assert projection["selectable"] is False

        created = client.post(
            "/backtests",
            headers=AUTH,
            json={
                "strategy_identifier": "smoke_test_hold",
                "profile_name": "default",
                "strategy_parameters": {
                    "warmup_ticks": 2,
                    "hold_minutes": 0.5,
                },
                "dataset_id": dataset_id,
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": START.isoformat(),
                "end_at": (START + timedelta(minutes=6)).isoformat(),
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {
                    "fixed_size": 1,
                    "max_open_positions": 1,
                },
                "spread_model": "FIXED_BPS",
                "spread_assumption": {"value": 0},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
        )

        assert created.status_code == 400
        assert "is not available" in str(created.json())
        assert session.exec(select(BacktestRun)).all() == []


def test_backtest_result_subresources_return_404_for_unknown_run(
    client_factory, tmp_path
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        for suffix in ("metrics", "trades", "equity", "warnings", "instruments"):
            response = client.get(f"/backtests/missing/{suffix}")
            assert response.status_code == 404


def test_backtest_contract_rejects_invalid_models_and_assumptions(
    client_factory, tmp_path
):
    with client_factory(
        operator_api_token="expected-token",
        historical_data_dir=str(tmp_path / "history"),
    ) as client:
        response = client.post(
            "/backtests",
            headers=AUTH,
            json={
                "strategy_identifier": "smoke_test_hold",
                "dataset_id": "dataset",
                "shortlist": ["TEST_FX"],
                "timeframe": "1m",
                "start_at": START.isoformat(),
                "end_at": (START + timedelta(minutes=1)).isoformat(),
                "starting_capital": 1000,
                "position_sizing_mode": "FIXED_UNITS",
                "risk_configuration": {"fixed_size": 1},
                "spread_model": "MADE_UP",
                "spread_assumption": {"value": -1},
                "slippage_model": "NONE",
                "slippage_assumption": {"value": 0},
                "fee_model": "NONE",
                "fee_assumption": {"value": 0},
                "open_position_treatment": "CLOSE_AT_END",
            },
        )

        assert response.status_code == 422
