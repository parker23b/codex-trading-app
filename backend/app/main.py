import asyncio
import contextlib
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import initialize_database
from app.db.session import engine
from app.services.market_data_service import MarketDataService
from app.services.simulation_service import simulation_service

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting application")
    if settings.ig_trading_enabled and settings.simulation_mode:
        raise RuntimeError("IG_TRADING_ENABLED cannot be true while SIMULATION_MODE is enabled.")

    initialize_database()
    market_data_task: asyncio.Task[None] | None = None
    with Session(engine) as session:
        simulation_service.bootstrap(session)
    if not settings.simulation_mode:
        market_data_task = asyncio.create_task(MarketDataService().run())
    yield
    if market_data_task is not None:
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
