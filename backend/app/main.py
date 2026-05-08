import asyncio
import contextlib
from contextlib import asynccontextmanager
import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from sqlmodel import Session

from app.api.auth import require_operator_identity, requires_operator_auth
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import initialize_database
from app.db.session import engine
from app.services.domain_event_service import domain_event_service
from app.services.health_service import get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.market_data_service import MarketDataService
from app.services.runtime_recovery_service import RuntimeRecoveryService

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

NOISY_POLLING_PATHS = {
    "/broker/positions",
    "/dashboard",
    "/executions",
    "/health/stream",
    "/system/health",
    "/trades",
    "/trades/positions",
}
SLOW_REQUEST_THRESHOLD_MS = 750.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting application")
    initialize_database()
    with Session(engine) as session:
        RuntimeRecoveryService(session).recover()
    streaming_service = get_ig_streaming_service()
    get_health_service().heartbeat()
    streaming_enabled = streaming_service.is_enabled()
    market_data_task = asyncio.create_task(
        MarketDataService(poll_prices=not streaming_enabled).run()
    )
    heartbeat_task = asyncio.create_task(_health_heartbeat_loop())
    streaming_task: asyncio.Task[None] | None = None
    if streaming_enabled:
        streaming_task = asyncio.create_task(streaming_service.run())
    yield
    heartbeat_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat_task
    if streaming_task is not None:
        streaming_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await streaming_task
    market_data_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await market_data_task
    logger.info("Shutting down application")


async def _health_heartbeat_loop() -> None:
    interval = get_settings().system_health_heartbeat_interval_seconds
    health_service = get_health_service()
    while True:
        health_service.heartbeat()
        await asyncio.sleep(interval)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_operator_auth(request: Request, call_next):
    if requires_operator_auth(
        method=request.method,
        path=request.url.path,
        query_params=request.query_params,
    ):
        try:
            require_operator_identity(request)
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers,
            )
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        domain_event_service.record_error(
            error_type="UnhandledRequestException",
            source="main.log_requests",
            event_type="api.request_failed",
            title="Unhandled API request exception",
            message=f"{request.method} {request.url.path} failed with an unhandled exception.",
            payload_json={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
            },
        )
        logger.exception(
            "API request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
            },
        )
        raise
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    if response.status_code >= 500:
        domain_event_service.record_error(
            error_type=f"HTTP{response.status_code}",
            source="main.log_requests",
            event_type="api.request_failed",
            title="API request returned server error",
            message=f"{request.method} {request.url.path} returned {response.status_code}.",
            payload_json={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
    log_level = _classify_request_log_level(
        request=request, response=response, duration_ms=duration_ms
    )
    logger.log(
        log_level,
        "API request handled",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


def _classify_request_log_level(
    *, request: Request, response: Response, duration_ms: float
) -> int:
    if response.status_code >= 500:
        return logging.ERROR
    if response.status_code >= 400:
        return logging.WARNING
    if duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
        return logging.INFO
    if request.method == "OPTIONS":
        return logging.DEBUG
    if request.method == "GET" and request.url.path in NOISY_POLLING_PATHS:
        return logging.DEBUG
    return logging.INFO


app.include_router(api_router)
