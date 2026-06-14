from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.backtesting.candles import (
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
from app.backtesting.storage import JsonlHistoricalDataRepository
from app.core.config import Settings, get_settings
from app.core.ig_broker import IGBroker
from app.models.backtest import (
    DatasetStatus,
    HistoricalDataset,
    HistoricalDatasetPartition,
)


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
        normalized_instruments = sorted(set(instruments))
        mappings = {
            instrument: provider.map_instrument(instrument)
            for instrument in normalized_instruments
        }
        source_identifier = (
            f"{capabilities.provider_id}:{timeframe}:"
            f"{normalized_start.isoformat()}:{normalized_end.isoformat()}"
        )
        dataset = self._create_dataset(
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
        try:
            for instrument in normalized_instruments:
                candles = provider.fetch_candles(
                    instrument,
                    timeframe,
                    normalized_start,
                    normalized_end,
                )
                self._add_partition(
                    dataset=dataset,
                    instrument=instrument,
                    provider_instrument=mappings[instrument],
                    candles=candles,
                    source_metadata={
                        "provider": capabilities.provider_id,
                        "venue": capabilities.venue,
                        "provider_instrument": mappings[instrument],
                    },
                )
            return self._complete_dataset(dataset)
        except Exception as exc:
            dataset.status = DatasetStatus.FAILED.value
            dataset.failure_reason = str(exc)
            self.session.add(dataset)
            self.session.commit()
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
        dataset = self._create_dataset(
            display_name=display_name,
            provider="CSV",
            venue=venue,
            market_type=market_type,
            asset_class=asset_class.upper(),
            timeframe=timeframe,
            source_identifier=source_identifier,
            source_metadata=dict(source_metadata or {}),
            import_parameters={
                "instrument": instrument,
                "row_count": len(candles),
            },
        )
        try:
            self._add_partition(
                dataset=dataset,
                instrument=instrument,
                provider_instrument=instrument,
                candles=candles,
                source_metadata=dict(source_metadata or {}),
            )
            return self._complete_dataset(dataset)
        except Exception as exc:
            dataset.status = DatasetStatus.FAILED.value
            dataset.failure_reason = str(exc)
            self.session.add(dataset)
            self.session.commit()
            raise

    def list_datasets(self) -> list[HistoricalDataset]:
        return list(
            self.session.exec(
                select(HistoricalDataset).order_by(HistoricalDataset.imported_at.desc())
            ).all()
        )

    def get_dataset(self, dataset_id: str) -> HistoricalDataset:
        dataset = self.session.get(HistoricalDataset, dataset_id)
        if dataset is None:
            raise ValueError(f"Historical dataset '{dataset_id}' was not found.")
        return dataset

    def list_partitions(self, dataset_id: str) -> list[HistoricalDatasetPartition]:
        return list(
            self.session.exec(
                select(HistoricalDatasetPartition)
                .where(HistoricalDatasetPartition.dataset_id == dataset_id)
                .order_by(HistoricalDatasetPartition.instrument)
            ).all()
        )

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
        if not dataset.immutable:
            raise ValueError("Backtest datasets must be immutable snapshots.")
        partitions = self.list_partitions(dataset.id)
        for partition in partitions:
            self.load_partition(partition)
        actual = self._dataset_checksum(dataset, partitions)
        if not dataset.checksum or actual != dataset.checksum:
            raise ValueError(
                f"Historical dataset checksum mismatch for '{dataset.id}'."
            )
        return dataset

    def _create_dataset(
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
        return dataset

    def _add_partition(
        self,
        *,
        dataset: HistoricalDataset,
        instrument: str,
        provider_instrument: str,
        candles: list[HistoricalCandle],
        source_metadata: dict[str, object],
    ) -> None:
        ordered, gaps = validate_candle_series(candles)
        relative_path, checksum = self.repository.write_partition(
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
        self.session.add(
            HistoricalDatasetPartition(
                dataset_id=dataset.id,
                instrument=instrument,
                provider_instrument=provider_instrument,
                timeframe=ordered[0].timeframe,
                earliest_at=ordered[0].timestamp,
                latest_at=ordered[-1].timestamp,
                candle_count=len(ordered),
                price_components=components,
                volume_available=any(row.volume is not None for row in ordered),
                checksum=checksum,
                storage_path=relative_path,
                detected_gaps=gaps,
                warnings=warnings,
                source_metadata=source_metadata,
            )
        )
        self.session.commit()

    def _complete_dataset(self, dataset: HistoricalDataset) -> HistoricalDataset:
        partitions = self.list_partitions(dataset.id)
        if not partitions:
            raise ValueError("Historical import produced no dataset partitions.")
        dataset.status = DatasetStatus.READY.value
        dataset.earliest_at = min(item.earliest_at for item in partitions)
        dataset.latest_at = max(item.latest_at for item in partitions)
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
        dataset.completeness_status = (
            "GAPS_DETECTED" if dataset.detected_gaps else "COMPLETE_FOR_INTERVAL"
        )
        dataset.checksum = self._dataset_checksum(dataset, partitions)
        self.session.add(dataset)
        self.session.commit()
        self.session.refresh(dataset)
        return dataset

    @staticmethod
    def _dataset_checksum(
        dataset: HistoricalDataset,
        partitions: list[HistoricalDatasetPartition],
    ) -> str:
        payload = {
            "provider": dataset.provider,
            "source_identifier": dataset.source_identifier,
            "venue": dataset.venue,
            "market_type": dataset.market_type,
            "asset_class": dataset.asset_class,
            "base_timeframe": dataset.base_timeframe,
            "timezone_rule": dataset.timezone_rule,
            "source_metadata": dataset.source_metadata,
            "import_parameters": dataset.import_parameters,
            "partitions": [
                {
                    "instrument": item.instrument,
                    "provider_instrument": item.provider_instrument,
                    "timeframe": item.timeframe,
                    "earliest_at": HistoricalDataService._stored_utc(
                        item.earliest_at
                    ).isoformat(),
                    "latest_at": HistoricalDataService._stored_utc(
                        item.latest_at
                    ).isoformat(),
                    "candle_count": item.candle_count,
                    "price_components": item.price_components,
                    "volume_available": item.volume_available,
                    "checksum": item.checksum,
                    "detected_gaps": item.detected_gaps,
                    "warnings": item.warnings,
                    "source_metadata": item.source_metadata,
                }
                for item in sorted(partitions, key=lambda row: row.instrument)
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

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
