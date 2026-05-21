from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.services.health_service import SystemHealth, get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.operational_telemetry_service import OperationalTelemetryService

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
    last_tick_at_by_instrument: dict[str, datetime]
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
        last_tick_at_by_instrument=health.last_tick_at_by_instrument or {},
        last_status=health.last_status,
        last_error=health.last_error,
    )


class OperationalDegradationResponse(BaseModel):
    audit_write_degraded: bool
    polling_fallback_active: bool
    polling_fallback_active_instrument_count: int
    stale_stream_instrument_count: int
    stream_degraded: bool
    runtime_degraded: bool
    degradation_reasons: list[str]


class SystemHealthResponse(BaseModel):
    status: str
    details: SystemHealth
    degradations: OperationalDegradationResponse


@router.get("/system/health", response_model=SystemHealthResponse)
def system_health_check(
    session: Session = Depends(get_session),
) -> SystemHealthResponse:
    report = get_health_service().get_health_report()
    telemetry = OperationalTelemetryService(session).get_summary()
    return SystemHealthResponse(
        status=str(report["status"]),
        details=report["details"],
        degradations=OperationalDegradationResponse(
            audit_write_degraded=bool(telemetry["audit_write_degraded"]),
            polling_fallback_active=bool(telemetry["polling_fallback_active"]),
            polling_fallback_active_instrument_count=int(
                telemetry["polling_fallback_active_instrument_count"]
            ),
            stale_stream_instrument_count=int(
                telemetry["stale_stream_instrument_count"]
            ),
            stream_degraded=bool(telemetry["stream_degraded"]),
            runtime_degraded=bool(telemetry["runtime_degraded"]),
            degradation_reasons=list(telemetry["degradation_reasons"]),
        ),
    )


class OperationalTelemetryResponse(BaseModel):
    status: str
    last_heartbeat: datetime
    heartbeat_age_ms: float | None
    last_price_update: datetime | None
    last_price_age_ms: float | None
    last_reconciliation: datetime | None
    last_reconciliation_age_ms: float | None
    last_audit_write_failure: datetime | None
    last_audit_write_failure_age_ms: float | None
    stream_connected: bool
    stream_last_tick_at: datetime | None
    stream_last_tick_age_ms: float | None
    subscribed_instrument_count: int
    desired_instrument_count: int
    broker_connected: bool
    feed_source_state: str
    feed_health_state: str
    broker_connectivity_state: str
    entry_eligible: bool
    exit_eligible: bool
    entry_block_reason: str | None
    exit_block_reason: str | None
    open_risk_management_state: str
    open_risk_management_reason: str | None
    audit_write_degraded: bool
    polling_fallback_active: bool
    polling_fallback_active_instrument_count: int
    stale_stream_instrument_count: int
    stream_degraded: bool
    runtime_degraded: bool
    degradation_reasons: list[str]
    broker_latency_ms: float | None
    runtime_count: int
    active_runtime_count: int
    stale_runtime_count: int
    stale_price_runtime_count: int
    reconciliation_mismatches: int
    order_failures_last_5m: int
    rejected_orders_last_5m: int
    audit_write_failures_last_5m: int
    strategies_paused_by_health: int


@router.get("/system/telemetry", response_model=OperationalTelemetryResponse)
def operational_telemetry(
    session: Session = Depends(get_session),
) -> OperationalTelemetryResponse:
    return OperationalTelemetryResponse(
        **OperationalTelemetryService(session).get_summary()
    )
