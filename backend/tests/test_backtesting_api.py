from __future__ import annotations

from datetime import UTC, datetime, timedelta


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


def test_typed_dataset_and_backtest_route_flow(client_factory, tmp_path):
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
        assert dataset["checksum"]
        assert dataset["partitions"][0]["instrument"] == "TEST_FX"

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

        metrics = client.get(f"/backtests/{run['id']}/metrics")
        trades = client.get(f"/backtests/{run['id']}/trades")
        equity = client.get(f"/backtests/{run['id']}/equity")

        assert metrics.status_code == 200
        assert metrics.json()["run"]["total_trades"] == 2
        assert trades.status_code == 200
        assert equity.status_code == 200
        assert len(equity.json()) == 6


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
