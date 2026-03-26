from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ig_streaming_service import get_ig_streaming_service

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


class StreamHealthResponse(BaseModel):
    enabled: bool
    connected: bool
    dependency_ready: bool
    subscribed_instruments: list[str]
    last_tick_at: datetime | None
    last_status: str | None
    last_error: str | None


@router.get("/health/stream", response_model=StreamHealthResponse)
def stream_health_check() -> StreamHealthResponse:
    health = get_ig_streaming_service().get_health()
    return StreamHealthResponse(
        enabled=health.enabled,
        connected=health.connected,
        dependency_ready=health.dependency_ready,
        subscribed_instruments=list(health.subscribed_instruments),
        last_tick_at=health.last_tick_at,
        last_status=health.last_status,
        last_error=health.last_error,
    )
