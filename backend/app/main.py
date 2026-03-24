import asyncio
import contextlib
import secrets
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import initialize_database
from app.services.market_data_service import MarketDataService

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


def _requires_auth(path: str) -> bool:
    if path.startswith("/strategy/"):
        return True
    if path.startswith("/broker"):
        return True
    if path.startswith("/strategies/") and (path.endswith("/start") or path.endswith("/stop")):
        return True
    return False


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting application")
    initialize_database()
    market_data_task: asyncio.Task[None] | None = asyncio.create_task(MarketDataService().run())
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


@app.middleware("http")
async def enforce_auth(request: Request, call_next):
    if not _requires_auth(request.url.path):
        return await call_next(request)

    configured_token = settings.api_auth_token
    presented_token = _extract_bearer_token(request)
    if not configured_token or not presented_token or not secrets.compare_digest(configured_token, presented_token):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


app.include_router(api_router)
