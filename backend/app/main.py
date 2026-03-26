import asyncio
import contextlib
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import initialize_database
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.market_data_service import MarketDataService

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting application")
    initialize_database()
    streaming_service = get_ig_streaming_service()
    streaming_enabled = streaming_service.is_enabled()
    market_data_task = asyncio.create_task(MarketDataService(poll_prices=not streaming_enabled).run())
    streaming_task: asyncio.Task[None] | None = None
    if streaming_enabled:
        streaming_task = asyncio.create_task(streaming_service.run())
    yield
    if streaming_task is not None:
        streaming_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await streaming_task
    market_data_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await market_data_task
    logger.info("Shutting down application")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = perf_counter()
    response = await call_next(request)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "API request handled",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(api_router)
