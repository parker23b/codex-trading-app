from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
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
from app.backtesting.replay import BacktestReplayEngine, ReplayConfiguration
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
        dataset = self.datasets.get_dataset(dataset_id)
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
                .order_by(BacktestTrade.open_time)
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
                .order_by(BacktestWarning.created_at)
            ).all()
        )

    def metrics(self, run_id: str) -> dict[str, object]:
        rows = self.session.exec(
            select(BacktestMetric).where(BacktestMetric.run_id == run_id)
        ).all()
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
        result,
        partitions: dict[str, HistoricalDatasetPartition],
        candles_by_instrument: dict[str, list[HistoricalCandle]],
    ) -> None:
        run.status = BacktestRunStatus.COMPLETED.value
        run.completed_at = datetime.now(UTC)
        run.effective_start_at = result.effective_start_at
        run.effective_end_at = result.effective_end_at
        run.pricing_mode = (
            result.pricing_modes[0]
            if len(result.pricing_modes) == 1
            else "MIXED:" + ",".join(result.pricing_modes)
        )
        run.result_summary = dict(result.metrics)
        self.session.add(run)

        for trade in result.trades:
            self.session.add(
                BacktestTrade(
                    run_id=run.id,
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
            )
        for sample, drawdown, drawdown_percent in equity_drawdown(result.equity):
            self.session.add(
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
            )
        for key, value in result.metrics.items():
            self.session.add(
                BacktestMetric(run_id=run.id, scope="RUN", metric_key=key, value=value)
            )
        for instrument, metrics in result.metrics_by_instrument.items():
            for key, value in metrics.items():
                self.session.add(
                    BacktestMetric(
                        run_id=run.id,
                        scope=f"INSTRUMENT:{instrument}",
                        metric_key=key,
                        value=value,
                    )
                )
        for warning in result.warnings:
            self.session.add(
                BacktestWarning(
                    run_id=run.id,
                    code=warning.code,
                    message=warning.message,
                    instrument=warning.instrument,
                    timestamp=warning.timestamp,
                    details=warning.details,
                )
            )
        for partition in partitions.values():
            for gap in partition.detected_gaps:
                self.session.add(
                    BacktestWarning(
                        run_id=run.id,
                        code="DATASET_GAP",
                        message=(
                            "The selected historical partition contains missing "
                            "candles within its stored coverage."
                        ),
                        instrument=partition.instrument,
                        details=dict(gap),
                    )
                )
        if any(
            "bid" not in partition.price_components
            or "ask" not in partition.price_components
            for partition in partitions.values()
        ):
            self.session.add(
                BacktestWarning(
                    run_id=run.id,
                    code="SYNTHETIC_SPREAD",
                    message=(
                        "Execution used an explicit synthetic spread because the "
                        "dataset does not contain complete bid/ask candles."
                    ),
                )
            )
        for instrument, partition in sorted(partitions.items()):
            self.session.add(
                BacktestRunInstrument(
                    run_id=run.id,
                    instrument=instrument,
                    provider_instrument=partition.provider_instrument,
                    dataset_partition_id=partition.id or 0,
                    candle_count=len(candles_by_instrument[instrument]),
                    metrics=result.metrics_by_instrument.get(instrument, {}),
                )
            )
        self.session.commit()

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
