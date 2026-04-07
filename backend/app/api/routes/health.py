from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.services.health_service import SystemHealth, get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service

router = APIRouter()


@router.get("/health")
def health_check(response: Response) -> dict[str, str]:
    current_status = str(get_health_service().get_health_report()["status"])
    response.status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if current_status == "critical"
        else status.HTTP_200_OK
    )
    return {"status": current_status}


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


class SystemHealthResponse(BaseModel):
    status: str
    details: SystemHealth


@router.get("/system/health", response_model=SystemHealthResponse)
def system_health_check() -> SystemHealthResponse:
    report = get_health_service().get_health_report()
    return SystemHealthResponse(status=str(report["status"]), details=report["details"])
