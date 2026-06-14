from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.api.contracts.backtesting import (
    BacktestEquityPointResponse,
    BacktestInstrumentResponse,
    BacktestMetricsResponse,
    BacktestRunCreateRequest,
    BacktestRunResponse,
    BacktestTradeResponse,
    BacktestWarningResponse,
    CsvImportRequest,
    HistoricalDatasetPartitionResponse,
    HistoricalDatasetResponse,
    HistoricalProviderCapabilitiesResponse,
    ProviderImportRequest,
)
from app.api.errors import operator_error_detail
from app.api.auth import resolve_request_settings
from app.db.session import get_session
from app.services.backtest_service import BacktestService
from app.services.historical_data_service import HistoricalDataService

router = APIRouter()


def _existing_backtest_service(
    *,
    run_id: str,
    request: Request,
    session: Session,
) -> BacktestService:
    service = BacktestService(session, settings=resolve_request_settings(request))
    try:
        service.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service


def _dataset_response(
    service: HistoricalDataService, dataset_id: str
) -> HistoricalDatasetResponse:
    dataset = service.get_dataset(dataset_id)
    return HistoricalDatasetResponse(
        **dataset.model_dump(),
        partitions=[
            HistoricalDatasetPartitionResponse.model_validate(partition)
            for partition in service.list_partitions(dataset_id)
        ],
    )


@router.get(
    "/historical-data/providers",
    response_model=list[HistoricalProviderCapabilitiesResponse],
)
def list_historical_providers(
    request: Request,
    session: Session = Depends(get_session),
) -> list[HistoricalProviderCapabilitiesResponse]:
    return [
        HistoricalProviderCapabilitiesResponse(**item)
        for item in HistoricalDataService(
            session, settings=resolve_request_settings(request)
        ).list_providers()
    ]


@router.get(
    "/historical-data/providers/{provider_id}",
    response_model=HistoricalProviderCapabilitiesResponse,
)
def get_historical_provider(
    provider_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HistoricalProviderCapabilitiesResponse:
    providers = {
        item["provider_id"]: item
        for item in HistoricalDataService(
            session, settings=resolve_request_settings(request)
        ).list_providers()
    }
    provider = providers.get(provider_id.upper())
    if provider is None:
        raise HTTPException(status_code=404, detail="Historical provider not found.")
    return HistoricalProviderCapabilitiesResponse(**provider)


@router.post(
    "/historical-data/imports",
    response_model=HistoricalDatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_historical_provider_data(
    payload: ProviderImportRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> HistoricalDatasetResponse:
    service = HistoricalDataService(session, settings=resolve_request_settings(request))
    try:
        dataset = service.import_from_provider(**payload.model_dump())
        return _dataset_response(service, dataset.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=operator_error_detail(
                exc, default_detail="Historical provider import failed."
            ),
        ) from exc


@router.post(
    "/historical-data/imports/csv",
    response_model=HistoricalDatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_historical_csv(
    payload: CsvImportRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> HistoricalDatasetResponse:
    service = HistoricalDataService(session, settings=resolve_request_settings(request))
    try:
        dataset = service.import_csv(**payload.model_dump())
        return _dataset_response(service, dataset.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=operator_error_detail(
                exc, default_detail="Historical CSV import failed."
            ),
        ) from exc


@router.get(
    "/historical-data/imports/{dataset_id}",
    response_model=HistoricalDatasetResponse,
)
def get_historical_import(
    dataset_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HistoricalDatasetResponse:
    return get_historical_dataset(dataset_id, request, session)


@router.get(
    "/historical-data/datasets",
    response_model=list[HistoricalDatasetResponse],
)
def list_historical_datasets(
    request: Request,
    session: Session = Depends(get_session),
) -> list[HistoricalDatasetResponse]:
    service = HistoricalDataService(session, settings=resolve_request_settings(request))
    return [
        HistoricalDatasetResponse(**dataset.model_dump(), partitions=[])
        for dataset in service.list_datasets()
    ]


@router.get(
    "/historical-data/datasets/{dataset_id}",
    response_model=HistoricalDatasetResponse,
)
def get_historical_dataset(
    dataset_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HistoricalDatasetResponse:
    service = HistoricalDataService(session, settings=resolve_request_settings(request))
    try:
        return _dataset_response(service, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/backtests",
    response_model=BacktestRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_backtest(
    payload: BacktestRunCreateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> BacktestRunResponse:
    try:
        run = BacktestService(
            session, settings=resolve_request_settings(request)
        ).create_and_run(**payload.model_dump())
        return BacktestRunResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=operator_error_detail(exc, default_detail="Backtest run failed."),
        ) from exc


@router.get("/backtests", response_model=list[BacktestRunResponse])
def list_backtests(
    request: Request,
    session: Session = Depends(get_session),
) -> list[BacktestRunResponse]:
    return [
        BacktestRunResponse.model_validate(run)
        for run in BacktestService(
            session, settings=resolve_request_settings(request)
        ).list_runs()
    ]


@router.get("/backtests/{run_id}", response_model=BacktestRunResponse)
def get_backtest(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> BacktestRunResponse:
    try:
        return BacktestRunResponse.model_validate(
            BacktestService(
                session, settings=resolve_request_settings(request)
            ).get_run(run_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/backtests/{run_id}/configuration", response_model=BacktestRunResponse)
def get_backtest_configuration(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> BacktestRunResponse:
    return get_backtest(run_id, request, session)


@router.get("/backtests/{run_id}/metrics", response_model=BacktestMetricsResponse)
def get_backtest_metrics(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> BacktestMetricsResponse:
    service = _existing_backtest_service(
        run_id=run_id, request=request, session=session
    )
    return BacktestMetricsResponse(**service.metrics(run_id))


@router.get("/backtests/{run_id}/trades", response_model=list[BacktestTradeResponse])
def get_backtest_trades(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[BacktestTradeResponse]:
    service = _existing_backtest_service(
        run_id=run_id, request=request, session=session
    )
    return [
        BacktestTradeResponse.model_validate(trade) for trade in service.trades(run_id)
    ]


@router.get(
    "/backtests/{run_id}/equity",
    response_model=list[BacktestEquityPointResponse],
)
def get_backtest_equity(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[BacktestEquityPointResponse]:
    service = _existing_backtest_service(
        run_id=run_id, request=request, session=session
    )
    return [
        BacktestEquityPointResponse.model_validate(point)
        for point in service.equity(run_id)
    ]


@router.get(
    "/backtests/{run_id}/warnings",
    response_model=list[BacktestWarningResponse],
)
def get_backtest_warnings(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[BacktestWarningResponse]:
    service = _existing_backtest_service(
        run_id=run_id, request=request, session=session
    )
    return [
        BacktestWarningResponse.model_validate(warning)
        for warning in service.warnings(run_id)
    ]


@router.get(
    "/backtests/{run_id}/instruments",
    response_model=list[BacktestInstrumentResponse],
)
def get_backtest_instruments(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[BacktestInstrumentResponse]:
    service = _existing_backtest_service(
        run_id=run_id, request=request, session=session
    )
    return [
        BacktestInstrumentResponse.model_validate(item)
        for item in service.instruments(run_id)
    ]
