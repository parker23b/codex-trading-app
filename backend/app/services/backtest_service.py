from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.backtesting.candles import (
    TIMEFRAME_SECONDS,
    HistoricalCandle,
    resample_candles,
)
from app.backtesting.clock import SimulatedClock
from app.backtesting.execution import ExecutionAssumptions
from app.backtesting.metrics import equity_drawdown
from app.backtesting.replay import (
    BacktestReplayEngine,
    ReplayConfiguration,
    ReplayResult,
)
from app.backtesting.storage import JsonlHistoricalDataRepository
from app.core.config import Settings, get_settings
from app.models.backtest import (
    BacktestEquityPoint,
    BacktestMetric,
    BacktestRun,
    BacktestRunInstrument,
    BacktestRunStatus,
    BacktestTrade,
    BacktestWarning,
    DatasetStatus,
    HistoricalDatasetPartition,
)
from app.services.historical_data_service import HistoricalDataService
from app.strategies.registry import strategy_registry


BACKTEST_RESULT_MANIFEST_VERSION = "BACKTEST_RESULT_MANIFEST_V1"
BACKTEST_ACCOUNTING_MODEL_VERSION = "EXECUTABLE_FILL_ACCOUNTING_V1"
CANONICAL_BACKTEST_RESULT_MANIFEST_SCHEMA = {
    "manifest_version": BACKTEST_RESULT_MANIFEST_VERSION,
    "accounting_model": BACKTEST_ACCOUNTING_MODEL_VERSION,
    "run": (
        "strategy_identifier",
        "strategy_version",
        "strategy_configuration",
        "dataset_id",
        "dataset_checksum",
        "shortlist",
        "timeframe",
        "requested_start_at",
        "requested_end_at",
        "effective_start_at",
        "effective_end_at",
        "starting_capital",
        "position_sizing_mode",
        "risk_configuration",
        "spread_model",
        "spread_assumption",
        "slippage_model",
        "slippage_assumption",
        "fee_model",
        "fee_assumption",
        "open_position_treatment",
        "pricing_mode",
        "evaluation_boundary",
        "status",
        "result_summary",
    ),
    "trade": (
        "deterministic_sequence",
        "instrument",
        "direction",
        "size",
        "open_price",
        "close_price",
        "open_time",
        "close_time",
        "gross_pnl",
        "fees",
        "spread_cost",
        "slippage_cost",
        "net_pnl",
        "exit_reason",
        "stop_loss_price",
        "take_profit_price",
        "conservative_ambiguity",
        "pricing_mode",
        "details",
    ),
    "equity": (
        "timestamp",
        "cash",
        "unrealised_pnl",
        "equity",
        "drawdown",
        "drawdown_percent",
        "open_position_count",
    ),
    "metric": ("scope", "metric_key", "value"),
    "warning": (
        "deterministic_sequence",
        "code",
        "severity",
        "message",
        "instrument",
        "timestamp",
        "details",
    ),
    "instrument": (
        "instrument",
        "provider_instrument",
        "candle_count",
        "metrics",
    ),
}
BACKTEST_RESULT_PROJECTION_ONLY_FIELDS = {
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
BACKTEST_RESULT_STATUS_CONSTRAINED_FIELDS = {
    "run": ("failure_reason",),
}
BACKTEST_RESULT_VERIFICATION_ENVELOPE_FIELDS = {
    "run": ("result_manifest_version", "result_checksum"),
}


class BacktestService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        repository: JsonlHistoricalDataRepository | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = repository or JsonlHistoricalDataRepository(
            Path(self.settings.historical_data_dir)
        )
        self.datasets = HistoricalDataService(
            session, settings=self.settings, repository=self.repository
        )

    def create_and_run(
        self,
        *,
        name: str | None,
        notes: str | None,
        strategy_identifier: str,
        profile_name: str | None,
        strategy_parameters: dict[str, object],
        dataset_id: str,
        shortlist: list[str],
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
        starting_capital: float,
        position_sizing_mode: str,
        risk_configuration: dict[str, object],
        spread_model: str,
        spread_assumption: dict[str, object],
        slippage_model: str,
        slippage_assumption: dict[str, object],
        fee_model: str,
        fee_assumption: dict[str, object],
        open_position_treatment: str,
    ) -> BacktestRun:
        dataset = self.datasets.verify_dataset_checksum(dataset_id)
        metadata = strategy_registry.get_metadata(strategy_identifier)
        resolved = strategy_registry.resolve_profile(strategy_identifier, profile_name)
        allowed_parameters = {definition.key for definition in metadata.parameters}
        unknown_parameters = sorted(set(strategy_parameters) - allowed_parameters)
        if unknown_parameters:
            raise ValueError(
                "Unknown strategy parameters: " + ", ".join(unknown_parameters)
            )
        parameters = dict(resolved.parameter_values)
        parameters.update(strategy_parameters)
        constructor_kwargs = {
            definition.constructor_key or definition.key: parameters.get(
                definition.key, definition.value
            )
            for definition in metadata.parameters
        }
        normalized_shortlist = sorted(
            {instrument.strip() for instrument in shortlist if instrument.strip()}
        )
        self._validate_configuration(
            timeframe=timeframe,
            start_at=start_at,
            end_at=end_at,
            starting_capital=starting_capital,
            position_sizing_mode=position_sizing_mode,
            risk_configuration=risk_configuration,
            spread_model=spread_model,
            spread_assumption=spread_assumption,
            slippage_model=slippage_model,
            slippage_assumption=slippage_assumption,
            fee_model=fee_model,
            fee_assumption=fee_assumption,
            open_position_treatment=open_position_treatment,
        )
        run = BacktestRun(
            id=str(uuid4()),
            name=name,
            notes=notes,
            strategy_identifier=strategy_identifier,
            strategy_version=metadata.implementation_version,
            strategy_configuration={
                "profile_name": resolved.profile_name,
                "parameters": parameters,
            },
            dataset_id=dataset.id,
            dataset_checksum=dataset.checksum or "",
            shortlist=normalized_shortlist,
            timeframe=timeframe,
            requested_start_at=self._utc(start_at),
            requested_end_at=self._utc(end_at),
            starting_capital=starting_capital,
            position_sizing_mode=position_sizing_mode,
            risk_configuration=dict(risk_configuration),
            spread_model=spread_model,
            spread_assumption=dict(spread_assumption),
            slippage_model=slippage_model,
            slippage_assumption=dict(slippage_assumption),
            fee_model=fee_model,
            fee_assumption=dict(fee_assumption),
            open_position_treatment=open_position_treatment,
            pricing_mode="PENDING_VALIDATION",
        )
        self.session.add(run)
        self.session.commit()
        try:
            candles, partitions = self._validate_and_load(
                run=run,
                supported_asset_classes=metadata.supported_asset_classes,
            )
            run.status = BacktestRunStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            self.session.add(run)
            self.session.commit()

            strategies = {
                instrument: strategy_registry.create(
                    strategy_identifier, parameters=constructor_kwargs
                )
                for instrument in sorted(candles)
            }
            engine = BacktestReplayEngine(
                strategies=strategies,
                configuration=ReplayConfiguration(
                    starting_capital=starting_capital,
                    position_sizing_mode=position_sizing_mode,
                    risk_configuration=dict(risk_configuration),
                    execution_assumptions=ExecutionAssumptions(
                        spread_model=spread_model,
                        spread_value=float(spread_assumption.get("value", 0.0)),
                        slippage_model=slippage_model,
                        slippage_value=float(slippage_assumption.get("value", 0.0)),
                        fee_model=fee_model,
                        fee_value=float(fee_assumption.get("value", 0.0)),
                    ),
                    open_position_treatment=open_position_treatment,
                ),
                clock=SimulatedClock(self._stored_utc(run.requested_start_at)),
            )
            result = engine.run(candles)
            self._persist_result(run, result, partitions, candles)
        except Exception as exc:
            self.session.rollback()
            persisted_run = self.session.get(BacktestRun, run.id)
            if persisted_run is not None:
                run = persisted_run
            run.status = BacktestRunStatus.FAILED.value
            run.failure_reason = str(exc)
            run.completed_at = datetime.now(UTC)
            self.session.add(run)
            self.session.commit()
        self.session.refresh(run)
        return run

    def list_runs(self) -> list[BacktestRun]:
        return list(
            self.session.exec(
                select(BacktestRun).order_by(BacktestRun.created_at.desc())
            ).all()
        )

    def get_run(self, run_id: str) -> BacktestRun:
        run = self.session.get(BacktestRun, run_id)
        if run is None:
            raise ValueError(f"Backtest run '{run_id}' was not found.")
        return run

    def trades(self, run_id: str) -> list[BacktestTrade]:
        return list(
            self.session.exec(
                select(BacktestTrade)
                .where(BacktestTrade.run_id == run_id)
                .order_by(
                    BacktestTrade.open_time,
                    BacktestTrade.instrument,
                    BacktestTrade.deterministic_sequence,
                )
            ).all()
        )

    def equity(self, run_id: str) -> list[BacktestEquityPoint]:
        return list(
            self.session.exec(
                select(BacktestEquityPoint)
                .where(BacktestEquityPoint.run_id == run_id)
                .order_by(BacktestEquityPoint.timestamp)
            ).all()
        )

    def warnings(self, run_id: str) -> list[BacktestWarning]:
        return list(
            self.session.exec(
                select(BacktestWarning)
                .where(BacktestWarning.run_id == run_id)
                .order_by(BacktestWarning.deterministic_sequence)
            ).all()
        )

    def metrics(self, run_id: str) -> dict[str, object]:
        rows = self._metric_rows(run_id)
        return {
            "run": {row.metric_key: row.value for row in rows if row.scope == "RUN"},
            "by_instrument": {
                scope.removeprefix("INSTRUMENT:"): {
                    row.metric_key: row.value for row in rows if row.scope == scope
                }
                for scope in sorted(
                    {row.scope for row in rows if row.scope.startswith("INSTRUMENT:")}
                )
            },
        }

    def instruments(self, run_id: str) -> list[BacktestRunInstrument]:
        return list(
            self.session.exec(
                select(BacktestRunInstrument)
                .where(BacktestRunInstrument.run_id == run_id)
                .order_by(BacktestRunInstrument.instrument)
            ).all()
        )

    def canonical_result_manifest(
        self,
        run: BacktestRun,
        *,
        trades: list[BacktestTrade] | None = None,
        equity: list[BacktestEquityPoint] | None = None,
        metrics: list[BacktestMetric] | None = None,
        warnings: list[BacktestWarning] | None = None,
        instruments: list[BacktestRunInstrument] | None = None,
    ) -> dict[str, object]:
        trade_rows = trades if trades is not None else self.trades(run.id)
        equity_rows = equity if equity is not None else self.equity(run.id)
        metric_rows = metrics if metrics is not None else self._metric_rows(run.id)
        warning_rows = warnings if warnings is not None else self.warnings(run.id)
        instrument_rows = (
            instruments if instruments is not None else self.instruments(run.id)
        )
        return {
            "manifest_version": BACKTEST_RESULT_MANIFEST_VERSION,
            "accounting_model": BACKTEST_ACCOUNTING_MODEL_VERSION,
            "run": {
                "strategy_identifier": run.strategy_identifier,
                "strategy_version": run.strategy_version,
                "strategy_configuration": run.strategy_configuration,
                "dataset_id": run.dataset_id,
                "dataset_checksum": run.dataset_checksum,
                "shortlist": sorted(run.shortlist),
                "timeframe": run.timeframe,
                "requested_start_at": self._canonical_timestamp(run.requested_start_at),
                "requested_end_at": self._canonical_timestamp(run.requested_end_at),
                "effective_start_at": self._canonical_timestamp(run.effective_start_at),
                "effective_end_at": self._canonical_timestamp(run.effective_end_at),
                "starting_capital": run.starting_capital,
                "position_sizing_mode": run.position_sizing_mode,
                "risk_configuration": run.risk_configuration,
                "spread_model": run.spread_model,
                "spread_assumption": run.spread_assumption,
                "slippage_model": run.slippage_model,
                "slippage_assumption": run.slippage_assumption,
                "fee_model": run.fee_model,
                "fee_assumption": run.fee_assumption,
                "open_position_treatment": run.open_position_treatment,
                "pricing_mode": run.pricing_mode,
                "evaluation_boundary": run.evaluation_boundary,
                "status": run.status,
                "result_summary": run.result_summary,
            },
            "trades": [
                {
                    "deterministic_sequence": row.deterministic_sequence,
                    "instrument": row.instrument,
                    "direction": row.direction,
                    "size": row.size,
                    "open_price": row.open_price,
                    "close_price": row.close_price,
                    "open_time": self._canonical_timestamp(row.open_time),
                    "close_time": self._canonical_timestamp(row.close_time),
                    "gross_pnl": row.gross_pnl,
                    "fees": row.fees,
                    "spread_cost": row.spread_cost,
                    "slippage_cost": row.slippage_cost,
                    "net_pnl": row.net_pnl,
                    "exit_reason": row.exit_reason,
                    "stop_loss_price": row.stop_loss_price,
                    "take_profit_price": row.take_profit_price,
                    "conservative_ambiguity": row.conservative_ambiguity,
                    "pricing_mode": row.pricing_mode,
                    "details": row.details,
                }
                for row in sorted(
                    trade_rows,
                    key=lambda item: (
                        item.open_time,
                        item.instrument,
                        item.deterministic_sequence,
                    ),
                )
            ],
            "equity": [
                {
                    "timestamp": self._canonical_timestamp(row.timestamp),
                    "cash": row.cash,
                    "unrealised_pnl": row.unrealized_pnl,
                    "equity": row.equity,
                    "drawdown": row.drawdown,
                    "drawdown_percent": row.drawdown_percent,
                    "open_position_count": row.open_position_count,
                }
                for row in sorted(equity_rows, key=lambda item: item.timestamp)
            ],
            "metrics": [
                {
                    "scope": row.scope,
                    "metric_key": row.metric_key,
                    "value": row.value,
                }
                for row in sorted(
                    metric_rows,
                    key=lambda item: (item.scope, item.metric_key),
                )
            ],
            "warnings": [
                {
                    "deterministic_sequence": row.deterministic_sequence,
                    "code": row.code,
                    "severity": row.severity,
                    "message": row.message,
                    "instrument": row.instrument,
                    "timestamp": self._canonical_timestamp(row.timestamp),
                    "details": row.details,
                }
                for row in sorted(
                    warning_rows,
                    key=lambda item: item.deterministic_sequence,
                )
            ],
            "instruments": [
                {
                    "instrument": row.instrument,
                    "provider_instrument": row.provider_instrument,
                    "candle_count": row.candle_count,
                    "metrics": row.metrics,
                }
                for row in sorted(
                    instrument_rows,
                    key=lambda item: item.instrument,
                )
            ],
        }

    def result_checksum(
        self,
        run: BacktestRun,
        *,
        trades: list[BacktestTrade] | None = None,
        equity: list[BacktestEquityPoint] | None = None,
        metrics: list[BacktestMetric] | None = None,
        warnings: list[BacktestWarning] | None = None,
        instruments: list[BacktestRunInstrument] | None = None,
    ) -> str:
        payload = self.canonical_result_manifest(
            run,
            trades=trades,
            equity=equity,
            metrics=metrics,
            warnings=warnings,
            instruments=instruments,
        )
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def verify_backtest_result_checksum(self, run_id: str) -> BacktestRun:
        run = self.get_run(run_id)
        if run.status != BacktestRunStatus.COMPLETED.value:
            raise ValueError("Only completed backtest results can be verified.")
        if run.failure_reason is not None:
            raise ValueError("Completed backtest result cannot have a failure reason.")
        if run.result_manifest_version != BACKTEST_RESULT_MANIFEST_VERSION:
            raise ValueError("Backtest result manifest version is unsupported.")
        actual = self.result_checksum(run)
        if not run.result_checksum or actual != run.result_checksum:
            raise ValueError(f"Backtest result checksum mismatch for '{run.id}'.")
        return run

    def _validate_and_load(
        self,
        *,
        run: BacktestRun,
        supported_asset_classes: tuple[str, ...],
    ) -> tuple[
        dict[str, list[HistoricalCandle]],
        dict[str, HistoricalDatasetPartition],
    ]:
        dataset = self.datasets.verify_dataset_checksum(run.dataset_id)
        if dataset.status != DatasetStatus.READY.value or not dataset.checksum:
            raise ValueError("Backtest requires a completed immutable dataset.")
        if dataset.checksum != run.dataset_checksum:
            raise ValueError("Dataset checksum changed after run creation.")
        if dataset.asset_class.upper() not in {
            item.upper() for item in supported_asset_classes
        }:
            raise ValueError(
                f"Strategy '{run.strategy_identifier}' is not compatible with "
                f"asset class '{dataset.asset_class}'."
            )
        if not run.shortlist:
            raise ValueError("Backtest shortlist cannot be empty.")
        requested_start = self._stored_utc(run.requested_start_at)
        requested_end = self._stored_utc(run.requested_end_at)
        if requested_start >= requested_end:
            raise ValueError("Backtest start must be before end.")
        target_seconds = TIMEFRAME_SECONDS[run.timeframe]
        for label, value in (
            ("start", requested_start),
            ("end", requested_end),
        ):
            if value.microsecond or int(value.timestamp()) % target_seconds:
                raise ValueError(
                    f"Backtest {label} must align to a {run.timeframe} boundary."
                )
        partitions = {
            item.instrument: item for item in self.datasets.list_partitions(dataset.id)
        }
        missing = sorted(set(run.shortlist) - set(partitions))
        if missing:
            raise ValueError(
                "Selected instruments are absent from the dataset: "
                + ", ".join(missing)
            )

        candles_by_instrument: dict[str, list[HistoricalCandle]] = {}
        total_candles = 0
        for instrument in sorted(run.shortlist):
            partition = partitions[instrument]
            coverage_end = self._stored_utc(partition.latest_at) + timedelta(
                seconds=TIMEFRAME_SECONDS[partition.timeframe]
            )
            if (
                requested_start < self._stored_utc(partition.earliest_at)
                or requested_end > coverage_end
            ):
                raise ValueError(
                    f"Requested date range is not covered for {instrument}."
                )
            candles = [
                candle
                for candle in self.datasets.load_partition(partition)
                if requested_start <= candle.timestamp.astimezone(UTC) < requested_end
            ]
            if run.timeframe != partition.timeframe:
                candles = resample_candles(candles, run.timeframe)
            if not candles:
                raise ValueError(
                    f"Requested date range produced no candles for {instrument}."
                )
            components = set(candles[0].available_components)
            if (
                not {"bid", "ask"}.issubset(components)
                and run.spread_model == "DATASET"
            ):
                raise ValueError(
                    f"{instrument} lacks bid/ask candles; configure a synthetic spread."
                )
            candles_by_instrument[instrument] = candles
            total_candles += len(candles)
        if total_candles > self.settings.backtest_max_candles_per_run:
            raise ValueError(
                f"Run contains {total_candles} candles, exceeding the synchronous "
                f"limit of {self.settings.backtest_max_candles_per_run}."
            )
        return candles_by_instrument, {
            instrument: partitions[instrument] for instrument in run.shortlist
        }

    def _persist_result(
        self,
        run: BacktestRun,
        result: ReplayResult,
        partitions: dict[str, HistoricalDatasetPartition],
        candles_by_instrument: dict[str, list[HistoricalCandle]],
    ) -> None:
        run.status = BacktestRunStatus.COMPLETED.value
        run.failure_reason = None
        run.completed_at = datetime.now(UTC)
        run.effective_start_at = result.effective_start_at
        run.effective_end_at = result.effective_end_at
        run.pricing_mode = (
            result.pricing_modes[0]
            if len(result.pricing_modes) == 1
            else "MIXED:" + ",".join(result.pricing_modes)
        )
        run.result_manifest_version = BACKTEST_RESULT_MANIFEST_VERSION
        run.result_summary = {
            **result.metrics,
            "accounting_model": BACKTEST_ACCOUNTING_MODEL_VERSION,
            "open_positions": [
                {
                    "instrument": item.position.instrument,
                    "direction": item.position.direction.value,
                    "size": item.position.size,
                    "open_time": self._canonical_timestamp(item.position.open_time),
                    "open_price": item.position.open_price,
                    "mark_time": self._canonical_timestamp(item.mark_time),
                    "mark_price": item.mark_price,
                    "unrealised_pnl": item.unrealized_pnl,
                    "open_position_value": item.open_position_value,
                    "entry_fee": item.position.entry_fee,
                    "entry_spread_cost": item.position.entry_spread_cost,
                    "entry_slippage_cost": item.position.entry_slippage_cost,
                    "stop_loss_price": item.position.stop_loss_price,
                    "take_profit_price": item.position.take_profit_price,
                    "pricing_mode": item.pricing_mode,
                    "details": item.position.metadata,
                }
                for item in result.open_positions
            ],
        }
        self.session.add(run)

        trade_rows = [
            BacktestTrade(
                run_id=run.id,
                deterministic_sequence=sequence,
                instrument=trade.position.instrument,
                direction=trade.position.direction.value,
                size=trade.position.size,
                open_price=trade.position.open_price,
                close_price=trade.close_price,
                open_time=trade.position.open_time,
                close_time=trade.close_time,
                gross_pnl=trade.gross_pnl,
                fees=trade.fees,
                spread_cost=trade.spread_cost,
                slippage_cost=trade.slippage_cost,
                net_pnl=trade.net_pnl,
                exit_reason=trade.exit_reason,
                stop_loss_price=trade.position.stop_loss_price,
                take_profit_price=trade.position.take_profit_price,
                conservative_ambiguity=trade.conservative_ambiguity,
                pricing_mode=trade.pricing_mode,
                details=trade.position.metadata,
            )
            for sequence, trade in enumerate(result.trades, start=1)
        ]
        equity_rows = [
            BacktestEquityPoint(
                run_id=run.id,
                timestamp=sample.timestamp,
                cash=sample.cash,
                unrealized_pnl=sample.unrealized_pnl,
                equity=sample.equity,
                drawdown=drawdown,
                drawdown_percent=drawdown_percent,
                open_position_count=sample.open_position_count,
            )
            for sample, drawdown, drawdown_percent in equity_drawdown(result.equity)
        ]
        metric_rows = [
            BacktestMetric(run_id=run.id, scope="RUN", metric_key=key, value=value)
            for key, value in sorted(result.metrics.items())
        ]
        for instrument, metrics in sorted(result.metrics_by_instrument.items()):
            for key, value in sorted(metrics.items()):
                metric_rows.append(
                    BacktestMetric(
                        run_id=run.id,
                        scope=f"INSTRUMENT:{instrument}",
                        metric_key=key,
                        value=value,
                    )
                )

        warning_values: list[dict[str, Any]] = [
            {
                "code": warning.code,
                "message": warning.message,
                "instrument": warning.instrument,
                "timestamp": warning.timestamp,
                "details": warning.details,
            }
            for warning in result.warnings
        ]
        for partition in partitions.values():
            for gap in partition.detected_gaps:
                warning_values.append(
                    {
                        "code": "DATASET_GAP",
                        "message": (
                            "The selected historical partition contains missing "
                            "candles within its stored coverage."
                        ),
                        "instrument": partition.instrument,
                        "timestamp": None,
                        "details": dict(gap),
                    }
                )
        if any(
            "bid" not in partition.price_components
            or "ask" not in partition.price_components
            for partition in partitions.values()
        ):
            warning_values.append(
                {
                    "code": "SYNTHETIC_SPREAD",
                    "message": (
                        "Execution used an explicit synthetic spread because the "
                        "dataset does not contain complete bid/ask candles."
                    ),
                    "instrument": None,
                    "timestamp": None,
                    "details": {},
                }
            )
        warning_values.sort(
            key=lambda item: (
                self._canonical_timestamp(item["timestamp"]) or "",
                str(item["instrument"] or ""),
                str(item["code"]),
                str(item["message"]),
                json.dumps(
                    item["details"],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            )
        )
        warning_rows = [
            BacktestWarning(
                run_id=run.id,
                deterministic_sequence=sequence,
                code=str(item["code"]),
                message=str(item["message"]),
                instrument=(
                    str(item["instrument"]) if item["instrument"] is not None else None
                ),
                timestamp=item["timestamp"],
                details=dict(item["details"]),
            )
            for sequence, item in enumerate(warning_values, start=1)
        ]
        instrument_rows = [
            BacktestRunInstrument(
                run_id=run.id,
                instrument=instrument,
                provider_instrument=partition.provider_instrument,
                dataset_partition_id=partition.id or 0,
                candle_count=len(candles_by_instrument[instrument]),
                metrics=result.metrics_by_instrument.get(instrument, {}),
            )
            for instrument, partition in sorted(partitions.items())
        ]
        self.session.add_all(
            [
                *trade_rows,
                *equity_rows,
                *metric_rows,
                *warning_rows,
                *instrument_rows,
            ]
        )
        self.session.flush()
        self.session.expire_all()
        run.result_checksum = self.result_checksum(run)
        self.session.add(run)
        self.session.commit()

    def _metric_rows(self, run_id: str) -> list[BacktestMetric]:
        return list(
            self.session.exec(
                select(BacktestMetric)
                .where(BacktestMetric.run_id == run_id)
                .order_by(BacktestMetric.scope, BacktestMetric.metric_key)
            ).all()
        )

    @staticmethod
    def _validate_configuration(
        *,
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
        starting_capital: float,
        position_sizing_mode: str,
        risk_configuration: dict[str, object],
        spread_model: str,
        spread_assumption: dict[str, object],
        slippage_model: str,
        slippage_assumption: dict[str, object],
        fee_model: str,
        fee_assumption: dict[str, object],
        open_position_treatment: str,
    ) -> None:
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported backtest timeframe '{timeframe}'.")
        normalized_start = BacktestService._utc(start_at)
        normalized_end = BacktestService._utc(end_at)
        if normalized_start >= normalized_end:
            raise ValueError("Backtest start must be before end.")
        if not isfinite(starting_capital) or starting_capital <= 0:
            raise ValueError("Starting capital must be finite and positive.")
        if position_sizing_mode not in {"FIXED_UNITS", "PERCENT_RISK"}:
            raise ValueError(
                f"Unsupported position sizing mode '{position_sizing_mode}'."
            )
        max_open_positions = BacktestService._positive_number(
            risk_configuration, "max_open_positions", default=1
        )
        if not float(max_open_positions).is_integer():
            raise ValueError("max_open_positions must be a whole number.")
        if position_sizing_mode == "FIXED_UNITS":
            BacktestService._positive_number(risk_configuration, "fixed_size")
        else:
            risk_percent = BacktestService._positive_number(
                risk_configuration, "risk_per_trade_percent"
            )
            if risk_percent > 100:
                raise ValueError("risk_per_trade_percent cannot exceed 100.")
            BacktestService._positive_number(
                risk_configuration, "fallback_stop_percent"
            )
            if risk_configuration.get("max_size") is not None:
                BacktestService._positive_number(risk_configuration, "max_size")

        model_options = (
            ("spread", spread_model, {"DATASET", "FIXED_PRICE", "FIXED_BPS", "NONE"}),
            ("slippage", slippage_model, {"NONE", "FIXED_PRICE", "FIXED_BPS"}),
            (
                "fee",
                fee_model,
                {"NONE", "FIXED_PER_ORDER", "PER_UNIT", "BPS_NOTIONAL"},
            ),
        )
        for label, model, allowed in model_options:
            if model not in allowed:
                raise ValueError(f"Unsupported {label} model '{model}'.")
        for label, assumption in (
            ("spread", spread_assumption),
            ("slippage", slippage_assumption),
            ("fee", fee_assumption),
        ):
            value = float(assumption.get("value", 0.0))
            if not isfinite(value) or value < 0:
                raise ValueError(
                    f"{label.capitalize()} assumption must be finite and non-negative."
                )
        if open_position_treatment not in {"CLOSE_AT_END", "MARK_TO_MARKET"}:
            raise ValueError(
                f"Unsupported open-position treatment '{open_position_treatment}'."
            )

    @staticmethod
    def _positive_number(
        values: dict[str, object],
        key: str,
        *,
        default: float | None = None,
    ) -> float:
        raw = values.get(key, default)
        if raw is None:
            raise ValueError(f"{key} is required.")
        value = float(raw)
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive.")
        return value

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Backtest date ranges must include a timezone.")
        return value.astimezone(UTC)

    @staticmethod
    def _stored_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _canonical_timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        return BacktestService._stored_utc(value).isoformat().replace("+00:00", "Z")
