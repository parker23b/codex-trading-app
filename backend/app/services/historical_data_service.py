from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.backtesting.candles import (
    TIMEFRAME_SECONDS,
    HistoricalCandle,
    parse_csv_candles,
    validate_candle_series,
)
from app.backtesting.providers import (
    BinanceHistoricalMarketDataProvider,
    CsvHistoricalMarketDataProvider,
    HistoricalMarketDataProvider,
    IGHistoricalMarketDataProvider,
    OandaHistoricalMarketDataProvider,
)
from app.backtesting.storage import (
    JsonlHistoricalDataRepository,
    StagedHistoricalPartition,
)
from app.core.config import Settings, get_settings
from app.core.ig_broker import IGBroker
from app.models.backtest import (
    DatasetAvailability,
    DatasetStatus,
    HistoricalDataset,
    HistoricalDatasetPartition,
)


MANIFEST_VERSION = "HISTORICAL_DATASET_MANIFEST_V3"

CANONICAL_DATASET_MANIFEST_SCHEMA = {
    "manifest_version": MANIFEST_VERSION,
    "dataset": (
        "id",
        "display_name",
        "provider",
        "source_identifier",
        "venue",
        "market_type",
        "asset_class",
        "base_timeframe",
        "status",
        "requested_start_at",
        "requested_end_at",
        "actual_earliest_at",
        "actual_latest_at",
        "candle_count",
        "timezone_rule",
        "price_components",
        "volume_available",
        "imported_at",
        "completeness_status",
        "detected_gaps",
        "warnings",
        "source_metadata",
        "import_parameters",
        "failure_reason",
        "storage_format",
        "immutable",
    ),
    "partition": (
        "id",
        "dataset_id",
        "instrument",
        "provider_instrument",
        "timeframe",
        "earliest_at",
        "latest_at",
        "candle_count",
        "price_components",
        "volume_available",
        "partition_hash",
        "storage_path",
        "detected_gaps",
        "warnings",
        "source_metadata",
    ),
}

AUTHORITATIVE_DATASET_MANIFEST_FIELDS = CANONICAL_DATASET_MANIFEST_SCHEMA["dataset"]
AUTHORITATIVE_PARTITION_MANIFEST_FIELDS = CANONICAL_DATASET_MANIFEST_SCHEMA["partition"]

MANIFEST_PROJECTION_ONLY_FIELDS = {
    "dataset": ("partitions",),
    "partition": (),
}

MANIFEST_VERIFICATION_ENVELOPE_FIELDS = {
    "dataset": ("checksum",),
    "partition": (),
}

MANIFEST_OPERATIONAL_FIELDS = {
    "dataset": (
        "availability",
        "availability_reason",
        "availability_updated_at",
    ),
    "partition": (),
}


class DatasetCoverageError(ValueError):
    pass


class DatasetRecoveryError(ValueError):
    pass


@dataclass(slots=True)
class _PreparedPartition:
    record: HistoricalDatasetPartition
    staged: StagedHistoricalPartition


class HistoricalDataService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        repository: JsonlHistoricalDataRepository | None = None,
        providers: dict[str, HistoricalMarketDataProvider] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = repository or JsonlHistoricalDataRepository(
            Path(self.settings.historical_data_dir)
        )
        self.providers = providers or self._configured_providers()

    def list_providers(self) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for provider_id in sorted(self.providers):
            provider = self.providers[provider_id]
            capabilities = provider.describe_capabilities()
            configured = True
            configuration_warning = None
            if provider_id == "OANDA" and not self.settings.oanda_practice_token:
                configured = False
                configuration_warning = (
                    "Optional OANDA practice token is not configured."
                )
            if provider_id == "IG" and not all(
                [
                    self.settings.ig_api_key,
                    self.settings.ig_username,
                    self.settings.ig_password,
                ]
            ):
                configured = False
                configuration_warning = "Existing IG credentials are not configured."
            results.append(
                {
                    **asdict(capabilities),
                    "configured": configured,
                    "configuration_warning": configuration_warning,
                }
            )
        return results

    def get_provider(self, provider_id: str) -> HistoricalMarketDataProvider:
        try:
            return self.providers[provider_id.upper()]
        except KeyError as exc:
            raise ValueError(
                f"Historical provider '{provider_id}' is not configured."
            ) from exc

    def import_from_provider(
        self,
        *,
        provider_id: str,
        display_name: str,
        instruments: list[str],
        timeframe: str,
        start_at: datetime,
        end_at: datetime,
        asset_class: str,
        market_type: str,
        venue: str | None = None,
    ) -> HistoricalDataset:
        provider = self.get_provider(provider_id)
        if not instruments:
            raise ValueError("At least one instrument is required.")
        capabilities = provider.describe_capabilities()
        normalized_asset_class = asset_class.upper()
        normalized_market_type = market_type.upper()
        normalized_start = self._utc(start_at)
        normalized_end = self._utc(end_at)
        if normalized_start >= normalized_end:
            raise ValueError("Historical import start must be before end.")
        if timeframe not in capabilities.available_timeframes:
            raise ValueError(
                f"{capabilities.provider_id} does not support timeframe '{timeframe}'."
            )
        if normalized_asset_class not in capabilities.supported_asset_classes:
            raise ValueError(
                f"{capabilities.provider_id} does not support asset class "
                f"'{normalized_asset_class}'."
            )
        if normalized_market_type not in capabilities.supported_market_types:
            raise ValueError(
                f"{capabilities.provider_id} does not support market type "
                f"'{normalized_market_type}'."
            )
        if venue is not None and venue.upper() != capabilities.venue.upper():
            raise ValueError(
                f"{capabilities.provider_id} data must use venue "
                f"'{capabilities.venue}', not '{venue}'."
            )
        interval = TIMEFRAME_SECONDS[timeframe]
        fetch_start = self._floor_boundary(normalized_start, interval)
        fetch_end = self._ceil_boundary(normalized_end, interval)
        normalized_instruments = sorted(set(instruments))
        mappings = {
            instrument: provider.map_instrument(instrument)
            for instrument in normalized_instruments
        }
        source_identifier = (
            f"{capabilities.provider_id}:{timeframe}:"
            f"{normalized_start.isoformat()}:{normalized_end.isoformat()}"
        )
        dataset = self._start_dataset(
            display_name=display_name,
            provider=capabilities.provider_id,
            venue=capabilities.venue,
            market_type=normalized_market_type,
            asset_class=normalized_asset_class,
            timeframe=timeframe,
            source_identifier=source_identifier,
            source_metadata={
                "capabilities": asdict(capabilities),
                "instrument_mappings": mappings,
            },
            import_parameters={
                "instruments": normalized_instruments,
                "start_at": normalized_start.isoformat(),
                "end_at": normalized_end.isoformat(),
                "timeframe": timeframe,
            },
        )
        prepared: list[_PreparedPartition] = []
        try:
            for instrument in normalized_instruments:
                candles = provider.fetch_candles(
                    instrument,
                    timeframe,
                    fetch_start,
                    fetch_end,
                )
                prepared.append(
                    self._prepare_partition(
                        dataset=dataset,
                        instrument=instrument,
                        provider_instrument=mappings[instrument],
                        candles=candles,
                        requested_start=normalized_start,
                        requested_end=normalized_end,
                        requested_timeframe=timeframe,
                        source_metadata={
                            "provider": capabilities.provider_id,
                            "venue": capabilities.venue,
                            "provider_instrument": mappings[instrument],
                        },
                    )
                )
            return self._publish_dataset(
                dataset=dataset,
                prepared=prepared,
                requested_instruments=normalized_instruments,
            )
        except Exception as exc:
            recovered = self._reconcile_import_exception(
                dataset_id=dataset.id,
                exc=exc,
                partial=bool(prepared) or isinstance(exc, DatasetCoverageError),
            )
            if recovered is not None:
                return recovered
            raise

    def import_csv(
        self,
        *,
        display_name: str,
        csv_text: str,
        asset_class: str,
        venue: str,
        market_type: str,
        source_identifier: str | None = None,
        source_metadata: dict[str, object] | None = None,
    ) -> HistoricalDataset:
        candles = parse_csv_candles(csv_text)
        instrument = candles[0].instrument
        timeframe = candles[0].timeframe
        ordered, gaps = validate_candle_series(candles)
        requested_start = ordered[0].timestamp.astimezone(UTC)
        requested_end = ordered[-1].close_timestamp
        dataset = self._start_dataset(
            display_name=display_name,
            provider="CSV",
            venue=venue,
            market_type=market_type,
            asset_class=asset_class.upper(),
            timeframe=timeframe,
            source_identifier=source_identifier,
            source_metadata=dict(source_metadata or {}),
            import_parameters={
                "instruments": [instrument],
                "row_count": len(candles),
                "start_at": requested_start.isoformat(),
                "end_at": requested_end.isoformat(),
                "timeframe": timeframe,
            },
        )
        prepared: list[_PreparedPartition] = []
        try:
            prepared.append(
                self._prepare_partition(
                    dataset=dataset,
                    instrument=instrument,
                    provider_instrument=instrument,
                    candles=ordered,
                    requested_start=requested_start,
                    requested_end=requested_end,
                    requested_timeframe=timeframe,
                    source_metadata={
                        **dict(source_metadata or {}),
                        "provider": "CSV",
                        "venue": venue,
                        "provider_instrument": instrument,
                    },
                )
            )
            if gaps:
                raise DatasetCoverageError(
                    "CSV coverage contains missing candles inside the inferred interval."
                )
            return self._publish_dataset(
                dataset=dataset,
                prepared=prepared,
                requested_instruments=[instrument],
            )
        except Exception as exc:
            recovered = self._reconcile_import_exception(
                dataset_id=dataset.id,
                exc=exc,
                partial=bool(prepared) or isinstance(exc, DatasetCoverageError),
            )
            if recovered is not None:
                return recovered
            raise

    def list_datasets(
        self, *, selectable_only: bool = False
    ) -> list[HistoricalDataset]:
        datasets = list(
            self.session.exec(
                select(HistoricalDataset).order_by(HistoricalDataset.imported_at.desc())
            ).all()
        )
        if not selectable_only:
            return datasets
        return [
            dataset for dataset in datasets if self.dataset_is_selectable(dataset.id)
        ]

    def get_dataset(self, dataset_id: str) -> HistoricalDataset:
        dataset = self.session.get(HistoricalDataset, dataset_id)
        if dataset is None:
            raise ValueError(f"Historical dataset '{dataset_id}' was not found.")
        return self._normalize_dataset_timestamps(dataset)

    def list_partitions(self, dataset_id: str) -> list[HistoricalDatasetPartition]:
        partitions = list(
            self.session.exec(
                select(HistoricalDatasetPartition)
                .where(HistoricalDatasetPartition.dataset_id == dataset_id)
                .order_by(HistoricalDatasetPartition.instrument)
            ).all()
        )
        return [self._normalize_partition_timestamps(item) for item in partitions]

    def load_partition(
        self, partition: HistoricalDatasetPartition
    ) -> list[HistoricalCandle]:
        candles = self.repository.read_partition(partition.storage_path)
        from app.backtesting.candles import candle_checksum

        if candle_checksum(candles) != partition.checksum:
            raise ValueError(
                f"Historical partition checksum mismatch for {partition.instrument}."
            )
        return candles

    def verify_dataset_checksum(self, dataset_id: str) -> HistoricalDataset:
        dataset = self.get_dataset(dataset_id)
        if dataset.status != DatasetStatus.READY.value or not dataset.immutable:
            raise ValueError("Backtest datasets must be completed immutable snapshots.")
        if dataset.availability != DatasetAvailability.AVAILABLE.value:
            reason = dataset.availability_reason or "operational recovery is required"
            raise ValueError(
                f"Historical dataset '{dataset.id}' is not available: {reason}."
            )
        partitions = self.list_partitions(dataset.id)
        for partition in partitions:
            self.load_partition(partition)
        actual = self.dataset_checksum(dataset, partitions)
        if not dataset.checksum or actual != dataset.checksum:
            raise ValueError(
                f"Historical dataset checksum mismatch for '{dataset.id}'."
            )
        return dataset

    def dataset_is_selectable(self, dataset_id: str) -> bool:
        try:
            self.verify_dataset_checksum(dataset_id)
        except (OSError, ValueError):
            return False
        return True

    def delete_dataset(self, dataset_id: str) -> None:
        dataset = self.get_dataset(dataset_id)
        self._require_mutable(dataset)
        for partition in self.list_partitions(dataset_id):
            self.session.delete(partition)
        self.session.delete(dataset)
        self.session.commit()
        self.repository.cleanup_dataset(dataset_id)

    def _start_dataset(
        self,
        *,
        display_name: str,
        provider: str,
        venue: str,
        market_type: str,
        asset_class: str,
        timeframe: str,
        source_identifier: str | None = None,
        source_metadata: dict[str, object] | None = None,
        import_parameters: dict[str, object] | None = None,
    ) -> HistoricalDataset:
        dataset = HistoricalDataset(
            id=str(uuid4()),
            display_name=display_name.strip() or f"{provider} historical dataset",
            provider=provider,
            source_identifier=source_identifier,
            venue=venue,
            market_type=market_type,
            asset_class=asset_class,
            base_timeframe=timeframe,
            status=DatasetStatus.IMPORTING.value,
            source_metadata=dict(source_metadata or {}),
            import_parameters=dict(import_parameters or {}),
        )
        self.session.add(dataset)
        self.session.commit()
        self.session.refresh(dataset)
        return self._normalize_dataset_timestamps(dataset)

    def _prepare_partition(
        self,
        *,
        dataset: HistoricalDataset,
        instrument: str,
        provider_instrument: str,
        candles: list[HistoricalCandle],
        requested_start: datetime,
        requested_end: datetime,
        requested_timeframe: str,
        source_metadata: dict[str, object],
    ) -> _PreparedPartition:
        ordered, gaps = validate_candle_series(candles)
        if ordered[0].instrument != instrument:
            raise DatasetCoverageError(
                f"Provider returned instrument '{ordered[0].instrument}' for '{instrument}'."
            )
        if ordered[0].timeframe != requested_timeframe:
            raise DatasetCoverageError(
                f"Provider returned timeframe '{ordered[0].timeframe}' for requested "
                f"'{requested_timeframe}'."
            )
        self._validate_source_metadata(
            source_metadata=source_metadata,
            provider=dataset.provider,
            venue=dataset.venue,
            provider_instrument=provider_instrument,
        )
        self._validate_requested_coverage(
            instrument=instrument,
            candles=ordered,
            gaps=gaps,
            requested_start=requested_start,
            requested_end=requested_end,
            timeframe=requested_timeframe,
        )
        staged = self.repository.stage_partition(
            dataset_id=dataset.id,
            instrument=instrument,
            timeframe=ordered[0].timeframe,
            candles=ordered,
        )
        components = sorted(
            {
                component
                for candle in ordered
                for component in candle.available_components
            }
        )
        warnings: list[dict[str, object]] = []
        if "bid" not in components or "ask" not in components:
            warnings.append(
                {
                    "code": "SYNTHETIC_SPREAD_REQUIRED",
                    "message": "Dataset lacks complete bid/ask candles.",
                }
            )
        return _PreparedPartition(
            staged=staged,
            record=HistoricalDatasetPartition(
                dataset_id=dataset.id,
                instrument=instrument,
                provider_instrument=provider_instrument,
                timeframe=ordered[0].timeframe,
                earliest_at=ordered[0].timestamp,
                latest_at=ordered[-1].timestamp,
                candle_count=len(ordered),
                price_components=components,
                volume_available=any(row.volume is not None for row in ordered),
                checksum=staged.checksum,
                storage_path=staged.storage_path,
                detected_gaps=gaps,
                warnings=warnings,
                source_metadata=source_metadata,
            ),
        )

    def _publish_dataset(
        self,
        *,
        dataset: HistoricalDataset,
        prepared: list[_PreparedPartition],
        requested_instruments: list[str],
    ) -> HistoricalDataset:
        if not prepared:
            raise ValueError("Historical import produced no dataset partitions.")
        partitions = [item.record for item in prepared]
        actual_instruments = {item.instrument for item in partitions}
        if actual_instruments != set(requested_instruments):
            missing = sorted(set(requested_instruments) - actual_instruments)
            raise DatasetCoverageError(
                "Historical import is missing requested instruments: "
                + ", ".join(missing)
            )

        dataset.earliest_at = min(
            self._stored_utc(item.earliest_at) for item in partitions
        )
        dataset.latest_at = max(self._stored_utc(item.latest_at) for item in partitions)
        dataset.candle_count = sum(item.candle_count for item in partitions)
        dataset.price_components = sorted(
            {component for item in partitions for component in item.price_components}
        )
        dataset.volume_available = any(item.volume_available for item in partitions)
        dataset.detected_gaps = [
            {**gap, "instrument": item.instrument}
            for item in partitions
            for gap in item.detected_gaps
        ]
        dataset.warnings = [
            {**warning, "instrument": item.instrument}
            for item in partitions
            for warning in item.warnings
        ]
        if dataset.detected_gaps:
            raise DatasetCoverageError(
                "Historical import contains missing candles and cannot be published."
            )
        dataset.completeness_status = "COMPLETE_FOR_INTERVAL"
        dataset.failure_reason = None
        dataset.availability = DatasetAvailability.AVAILABLE.value
        dataset.availability_reason = None
        dataset.availability_updated_at = datetime.now(UTC)

        self.session.add_all(partitions)
        self.session.flush()
        dataset.status = DatasetStatus.READY.value
        dataset.checksum = self.dataset_checksum(dataset, partitions)
        for item in prepared:
            self.repository.publish_partition(item.staged)
        self.session.add(dataset)
        self.session.commit()
        self.session.refresh(dataset)
        return self._normalize_dataset_timestamps(dataset)

    @classmethod
    def canonical_dataset_manifest(
        cls,
        dataset: HistoricalDataset,
        partitions: list[HistoricalDatasetPartition],
    ) -> dict[str, object]:
        return {
            "manifest_version": MANIFEST_VERSION,
            "dataset": {
                "id": dataset.id,
                "display_name": dataset.display_name,
                "provider": dataset.provider,
                "source_identifier": dataset.source_identifier,
                "venue": dataset.venue,
                "market_type": dataset.market_type,
                "asset_class": dataset.asset_class,
                "base_timeframe": dataset.base_timeframe,
                "status": dataset.status,
                "requested_start_at": cls._manifest_import_timestamp(
                    dataset.import_parameters, "start_at"
                ),
                "requested_end_at": cls._manifest_import_timestamp(
                    dataset.import_parameters, "end_at"
                ),
                "actual_earliest_at": cls._canonical_timestamp(dataset.earliest_at),
                "actual_latest_at": cls._canonical_timestamp(dataset.latest_at),
                "candle_count": dataset.candle_count,
                "timezone_rule": dataset.timezone_rule,
                "price_components": sorted(dataset.price_components),
                "volume_available": dataset.volume_available,
                "imported_at": cls._canonical_timestamp(dataset.imported_at),
                "completeness_status": dataset.completeness_status,
                "detected_gaps": dataset.detected_gaps,
                "warnings": dataset.warnings,
                "source_metadata": dataset.source_metadata,
                "import_parameters": dataset.import_parameters,
                "failure_reason": dataset.failure_reason,
                "storage_format": dataset.storage_format,
                "immutable": dataset.immutable,
            },
            "partitions": [
                {
                    "id": item.id,
                    "dataset_id": item.dataset_id,
                    "instrument": item.instrument,
                    "provider_instrument": item.provider_instrument,
                    "timeframe": item.timeframe,
                    "earliest_at": cls._canonical_timestamp(item.earliest_at),
                    "latest_at": cls._canonical_timestamp(item.latest_at),
                    "candle_count": item.candle_count,
                    "price_components": sorted(item.price_components),
                    "volume_available": item.volume_available,
                    "partition_hash": item.checksum,
                    "storage_path": item.storage_path,
                    "detected_gaps": item.detected_gaps,
                    "warnings": item.warnings,
                    "source_metadata": item.source_metadata,
                }
                for item in sorted(
                    partitions,
                    key=lambda row: (
                        row.instrument,
                        row.provider_instrument,
                        row.timeframe,
                    ),
                )
            ],
        }

    @classmethod
    def dataset_checksum(
        cls,
        dataset: HistoricalDataset,
        partitions: list[HistoricalDatasetPartition],
    ) -> str:
        payload = cls.canonical_dataset_manifest(dataset, partitions)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def _reconcile_import_exception(
        self,
        *,
        dataset_id: str,
        exc: Exception,
        partial: bool,
    ) -> HistoricalDataset | None:
        self.session.rollback()
        try:
            with Session(self.session.get_bind()) as reconciliation_session:
                reconciliation_service = HistoricalDataService(
                    reconciliation_session,
                    settings=self.settings,
                    repository=self.repository,
                    providers=self.providers,
                )
                recovered = reconciliation_session.get(HistoricalDataset, dataset_id)
                if (
                    recovered is not None
                    and recovered.status == DatasetStatus.READY.value
                ):
                    try:
                        verified = reconciliation_service.verify_dataset_checksum(
                            dataset_id
                        )
                    except Exception as verification_exc:
                        reason = (
                            "Durable READY dataset failed recovery verification after "
                            f"an ambiguous publication outcome: {verification_exc}"
                        )
                        recovered.availability = (
                            DatasetAvailability.RECOVERY_REQUIRED.value
                        )
                        recovered.availability_reason = reason
                        recovered.availability_updated_at = datetime.now(UTC)
                        reconciliation_session.add(recovered)
                        reconciliation_session.commit()
                        raise DatasetRecoveryError(reason) from verification_exc
                    reconciliation_session.expunge(verified)
                    return verified
        except DatasetRecoveryError:
            raise
        except Exception as reconciliation_exc:
            raise RuntimeError(
                "Historical import publication outcome is uncertain; retained "
                f"dataset artifacts for recovery ({reconciliation_exc})."
            ) from exc

        self.repository.cleanup_dataset(dataset_id)
        self._record_import_failure(
            dataset_id=dataset_id,
            exc=exc,
            partial=partial,
        )
        return None

    def _record_import_failure(
        self,
        *,
        dataset_id: str,
        exc: Exception,
        partial: bool,
    ) -> None:
        dataset = self.session.get(HistoricalDataset, dataset_id)
        if dataset is None:
            return
        dataset.status = (
            DatasetStatus.PARTIAL.value if partial else DatasetStatus.FAILED.value
        )
        dataset.completeness_status = "PARTIAL_COVERAGE" if partial else "IMPORT_FAILED"
        dataset.failure_reason = str(exc)
        dataset.checksum = None
        dataset.availability = DatasetAvailability.UNAVAILABLE.value
        dataset.availability_reason = str(exc)
        dataset.availability_updated_at = datetime.now(UTC)
        dataset.warnings = [
            {
                "code": (
                    "PARTIAL_COVERAGE"
                    if isinstance(exc, DatasetCoverageError)
                    else "IMPORT_FAILED"
                ),
                "message": str(exc),
            }
        ]
        self.session.add(dataset)
        self.session.commit()

    @staticmethod
    def _validate_source_metadata(
        *,
        source_metadata: dict[str, object],
        provider: str,
        venue: str,
        provider_instrument: str,
    ) -> None:
        expected = {
            "provider": provider,
            "venue": venue,
            "provider_instrument": provider_instrument,
        }
        for key, value in expected.items():
            if source_metadata.get(key) != value:
                raise DatasetCoverageError(
                    f"Partition source metadata '{key}' does not match import provenance."
                )

    @classmethod
    def _validate_requested_coverage(
        cls,
        *,
        instrument: str,
        candles: list[HistoricalCandle],
        gaps: list[dict[str, object]],
        requested_start: datetime,
        requested_end: datetime,
        timeframe: str,
    ) -> None:
        interval = TIMEFRAME_SECONDS[timeframe]
        required_start = cls._floor_boundary(requested_start, interval)
        required_end = cls._ceil_boundary(requested_end, interval)
        first = candles[0].timestamp.astimezone(UTC)
        last_close = candles[-1].close_timestamp
        if first > required_start:
            raise DatasetCoverageError(
                f"{instrument} coverage starts at {first.isoformat()}, after required "
                f"boundary {required_start.isoformat()}."
            )
        if first < required_start:
            raise DatasetCoverageError(
                f"{instrument} coverage starts before the aligned import boundary "
                f"{required_start.isoformat()}."
            )
        if last_close < required_end:
            raise DatasetCoverageError(
                f"{instrument} coverage ends at {last_close.isoformat()}, before required "
                f"boundary {required_end.isoformat()}; provider response may be truncated."
            )
        if last_close > required_end:
            raise DatasetCoverageError(
                f"{instrument} coverage extends beyond the aligned import boundary "
                f"{required_end.isoformat()}."
            )
        if any(candle.close_timestamp > datetime.now(UTC) for candle in candles):
            raise DatasetCoverageError(
                f"{instrument} includes an incomplete or still-open provider candle."
            )
        expected = {
            required_start + timedelta(seconds=index * interval)
            for index in range(
                int((required_end - required_start).total_seconds() // interval)
            )
        }
        actual = {
            candle.timestamp.astimezone(UTC)
            for candle in candles
            if required_start <= candle.timestamp.astimezone(UTC) < required_end
        }
        missing = sorted(expected - actual)
        if missing or gaps:
            first_missing = missing[0].isoformat() if missing else "reported gap"
            raise DatasetCoverageError(
                f"{instrument} is missing {len(missing) or len(gaps)} required candles; "
                f"first missing boundary is {first_missing}."
            )

    @staticmethod
    def _floor_boundary(value: datetime, interval_seconds: int) -> datetime:
        normalized = value.astimezone(UTC)
        epoch = int(normalized.timestamp())
        return datetime.fromtimestamp(
            epoch - (epoch % interval_seconds),
            tz=UTC,
        )

    @staticmethod
    def _ceil_boundary(value: datetime, interval_seconds: int) -> datetime:
        normalized = value.astimezone(UTC)
        epoch = int(normalized.timestamp())
        remainder = epoch % interval_seconds
        if normalized.microsecond or remainder:
            epoch += interval_seconds - remainder
        return datetime.fromtimestamp(epoch, tz=UTC)

    @staticmethod
    def _canonical_timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        normalized = HistoricalDataService._stored_utc(value)
        return normalized.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _manifest_import_timestamp(
        import_parameters: dict[str, object], key: str
    ) -> str | None:
        raw = import_parameters.get(key)
        if raw is None:
            return None
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return HistoricalDataService._canonical_timestamp(parsed)

    @staticmethod
    def _require_mutable(dataset: HistoricalDataset) -> None:
        if dataset.status == DatasetStatus.READY.value:
            raise ValueError("Completed historical datasets are append-only.")

    @staticmethod
    def _normalize_dataset_timestamps(
        dataset: HistoricalDataset,
    ) -> HistoricalDataset:
        dataset.imported_at = HistoricalDataService._stored_utc(dataset.imported_at)
        if dataset.earliest_at is not None:
            dataset.earliest_at = HistoricalDataService._stored_utc(dataset.earliest_at)
        if dataset.latest_at is not None:
            dataset.latest_at = HistoricalDataService._stored_utc(dataset.latest_at)
        return dataset

    @staticmethod
    def _normalize_partition_timestamps(
        partition: HistoricalDatasetPartition,
    ) -> HistoricalDatasetPartition:
        partition.earliest_at = HistoricalDataService._stored_utc(partition.earliest_at)
        partition.latest_at = HistoricalDataService._stored_utc(partition.latest_at)
        return partition

    def _configured_providers(self) -> dict[str, HistoricalMarketDataProvider]:
        ig_broker = IGBroker(
            api_key=self.settings.ig_api_key,
            username=self.settings.ig_username,
            password=self.settings.ig_password,
            account_id=self.settings.ig_account_id,
            base_url=self.settings.ig_api_base_url,
            request_timeout_seconds=self.settings.ig_request_timeout_seconds,
            trading_enabled=False,
            live_trading_acknowledged=False,
            verify_ssl=self.settings.ig_verify_ssl,
            ca_bundle_path=self.settings.ig_ca_bundle_path,
        )
        return {
            "BINANCE": BinanceHistoricalMarketDataProvider(
                base_url=self.settings.binance_api_base_url
            ),
            "CSV": CsvHistoricalMarketDataProvider(),
            "IG": IGHistoricalMarketDataProvider(ig_broker),
            "OANDA": OandaHistoricalMarketDataProvider(
                token=self.settings.oanda_practice_token,
                base_url=self.settings.oanda_api_base_url,
            ),
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Historical date ranges must include a timezone.")
        return value.astimezone(UTC)

    @staticmethod
    def _stored_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
