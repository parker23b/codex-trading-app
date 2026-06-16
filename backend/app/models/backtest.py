from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC and restore timezone awareness across SQLite and PostgreSQL."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Persisted backtesting timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DatasetStatus(StrEnum):
    IMPORTING = "IMPORTING"
    PARTIAL = "PARTIAL"
    READY = "READY"
    FAILED = "FAILED"


class DatasetAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


class BacktestRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HistoricalDataset(SQLModel, table=True):
    __tablename__ = "historical_dataset"

    id: str = Field(primary_key=True)
    display_name: str
    provider: str = Field(index=True)
    source_identifier: str | None = None
    venue: str
    market_type: str
    asset_class: str
    base_timeframe: str
    status: str = Field(default=DatasetStatus.IMPORTING.value, index=True)
    availability: str = Field(
        default=DatasetAvailability.UNAVAILABLE.value,
        sa_column=Column(
            String,
            nullable=False,
            server_default=text("'UNAVAILABLE'"),
        ),
    )
    availability_reason: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    availability_updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )
    earliest_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    latest_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    candle_count: int = 0
    timezone_rule: str = "UTC"
    price_components: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    volume_available: bool = False
    imported_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    checksum: str | None = Field(default=None, index=True)
    completeness_status: str = "UNKNOWN"
    detected_gaps: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    warnings: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    import_parameters: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    failure_reason: str | None = None
    storage_format: str = "JSONL_GZIP_V1"
    immutable: bool = True


class HistoricalDatasetPartition(SQLModel, table=True):
    __tablename__ = "historical_dataset_partition"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "instrument",
            "timeframe",
            name="uq_historical_partition_dataset_instrument_timeframe",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    dataset_id: str = Field(index=True)
    instrument: str = Field(index=True)
    provider_instrument: str
    timeframe: str = Field(index=True)
    earliest_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    latest_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    candle_count: int
    price_components: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    volume_available: bool = False
    checksum: str = Field(index=True)
    storage_path: str
    detected_gaps: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    warnings: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class BacktestRun(SQLModel, table=True):
    __tablename__ = "backtest_run"
    __table_args__ = (Index("ix_backtest_run_created_at", "created_at"),)

    id: str = Field(primary_key=True)
    name: str | None = None
    notes: str | None = None
    strategy_identifier: str = Field(index=True)
    strategy_version: str
    strategy_configuration: dict[str, Any] = Field(sa_column=Column(JSON))
    dataset_id: str = Field(index=True)
    dataset_checksum: str
    shortlist: list[str] = Field(sa_column=Column(JSON))
    timeframe: str
    requested_start_at: datetime = Field(
        sa_column=Column(UTCDateTime(), nullable=False)
    )
    requested_end_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    warmup_mode: str = Field(default="NONE")
    warmup_candle_count: int = Field(default=0)
    allow_insufficient_warmup: bool = Field(default=False)
    warmup_start_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    trading_start_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    warmup_sufficient: bool = Field(default=True)
    warmup_degraded: bool = Field(default=False)
    warmup_warnings: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    effective_start_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    effective_end_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    starting_capital: float
    position_sizing_mode: str
    risk_configuration: dict[str, Any] = Field(sa_column=Column(JSON))
    spread_model: str
    spread_assumption: dict[str, Any] = Field(sa_column=Column(JSON))
    slippage_model: str
    slippage_assumption: dict[str, Any] = Field(sa_column=Column(JSON))
    fee_model: str
    fee_assumption: dict[str, Any] = Field(sa_column=Column(JSON))
    open_position_treatment: str
    pricing_mode: str
    evaluation_boundary: str = "CANDLE_CLOSE_NEXT_OPEN"
    status: str = Field(default=BacktestRunStatus.PENDING.value, index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    failure_reason: str | None = None
    result_manifest_version: str | None = None
    result_checksum: str | None = Field(default=None, index=True)
    result_summary: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class BacktestRunInstrument(SQLModel, table=True):
    __tablename__ = "backtest_run_instrument"
    __table_args__ = (
        UniqueConstraint("run_id", "instrument", name="uq_backtest_run_instrument"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    instrument: str = Field(index=True)
    provider_instrument: str
    dataset_partition_id: int
    candle_count: int = 0
    warmup_candles_consumed: int = 0
    first_tradable_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    metrics: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class BacktestTrade(SQLModel, table=True):
    __tablename__ = "backtest_trade"
    __table_args__ = (Index("ix_backtest_trade_run_open", "run_id", "open_time"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    deterministic_sequence: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
    )
    instrument: str = Field(index=True)
    direction: str
    size: float
    open_price: float
    close_price: float
    open_time: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    close_time: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    gross_pnl: float
    fees: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    net_pnl: float
    exit_reason: str
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    conservative_ambiguity: bool = False
    pricing_mode: str
    details: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class BacktestEquityPoint(SQLModel, table=True):
    __tablename__ = "backtest_equity_point"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "timestamp", name="uq_backtest_equity_run_timestamp"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    timestamp: datetime = Field(
        sa_column=Column(UTCDateTime(), nullable=False, index=True)
    )
    cash: float
    unrealized_pnl: float
    equity: float
    drawdown: float
    drawdown_percent: float
    open_position_count: int


class BacktestMetric(SQLModel, table=True):
    __tablename__ = "backtest_metric"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "scope", "metric_key", name="uq_backtest_metric_scope_key"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    scope: str = Field(default="RUN", index=True)
    metric_key: str
    value: Any = Field(default=None, sa_column=Column(JSON))


class BacktestWarning(SQLModel, table=True):
    __tablename__ = "backtest_warning"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    deterministic_sequence: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
    )
    code: str = Field(index=True)
    severity: str = "warning"
    message: str
    instrument: str | None = Field(default=None, index=True)
    timestamp: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime(), nullable=True)
    )
    details: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
