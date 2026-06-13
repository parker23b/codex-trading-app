from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
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
        dataset = self._create_dataset(
            display_name=display_name,
            provider=provider_id.upper(),
            venue=venue or provider.describe_capabilities().venue,
            market_type=market_type,
            asset_class=asset_class.upper(),
            timeframe=timeframe,
            import_parameters={
                "instruments": sorted(instruments),
                "start_at": self._utc(start_at).isoformat(),
                "end_at": self._utc(end_at).isoformat(),
            },
        )
        try:
            for instrument in sorted(set(instruments)):
                candles = provider.fetch_candles(
                    instrument,
                    timeframe,
                    self._utc(start_at),
                    self._utc(end_at),
                )
                self._add_partition(
                    dataset=dataset,
                    instrument=instrument,
                    provider_instrument=provider.map_instrument(instrument),
                    candles=candles,
                    source_metadata={
                        "provider": provider_id.upper(),
                        "venue": provider.describe_capabilities().venue,
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
        digest = sha256()
        for item in sorted(partitions, key=lambda row: row.instrument):
            digest.update(
                f"{item.instrument}:{item.timeframe}:{item.checksum}\n".encode("utf-8")
            )
        dataset.checksum = digest.hexdigest()
        self.session.add(dataset)
        self.session.commit()
        self.session.refresh(dataset)
        return dataset

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
