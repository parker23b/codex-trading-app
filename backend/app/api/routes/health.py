from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.auth import resolve_request_settings
from app.core.config import get_settings
from app.db.session import get_session
from app.services.health_service import SystemHealth, get_health_service
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.operational_telemetry_service import OperationalTelemetryService

router = APIRouter()


@router.get("/health")
def health_check(
    response: Response, session: Session = Depends(get_session)
) -> dict[str, str]:
    current_status = str(
        get_health_service().get_health_report(session=session)["status"]
    )
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


class ProcessIdentityResponse(BaseModel):
    worker_id: str
    hostname: str
    process_id: int
    instance_id: str


class RuntimeLeaderResponse(BaseModel):
    owner_id: str | None
    heartbeat_at: datetime | None
    expires_at: datetime | None
    stale: bool


class ObservabilityObservationResponse(BaseModel):
    state_key: str
    scope_type: str
    scope_id: str
    worker_id: str
    hostname: str
    process_id: int
    source: str
    status: str
    observed_at: datetime
    expires_at: datetime | None
    stale: bool
    payload: dict[str, Any]


class ObservabilitySummaryResponse(BaseModel):
    mode: str
    aggregation_available: bool
    local_details_scope: str
    degradation_scope: str
    current_process: ProcessIdentityResponse
    runtime_leader: RuntimeLeaderResponse
    last_aggregate_update_at: datetime | None
    active_observation_count: int
    stale_observation_count: int


class SystemHealthResponse(BaseModel):
    status: str
    details: SystemHealth
    degradations: OperationalDegradationResponse
    observability: ObservabilitySummaryResponse


@router.get("/system/health", response_model=SystemHealthResponse)
def system_health_check(
    session: Session = Depends(get_session),
) -> SystemHealthResponse:
    report = get_health_service().get_health_report(session=session)
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
        observability=ObservabilitySummaryResponse(
            **{
                key: telemetry["observability"][key]
                for key in {
                    "mode",
                    "aggregation_available",
                    "local_details_scope",
                    "degradation_scope",
                    "current_process",
                    "runtime_leader",
                    "last_aggregate_update_at",
                    "active_observation_count",
                    "stale_observation_count",
                }
            }
        ),
    )


class OperationalTelemetryObservabilityResponse(ObservabilitySummaryResponse):
    observations: list[ObservabilityObservationResponse]


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
    open_risk_authority_version: int | None
    open_risk_authority_updated_at: datetime | None
    open_risk_reconciliation_status: str | None
    broker_resilience: dict[str, object]
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
    observability: OperationalTelemetryObservabilityResponse


class BrokerEnvironmentStatusResponse(BaseModel):
    provider: str
    environment: str
    endpoint_classification: str
    dealing_enabled: bool
    streaming_enabled: bool
    live_trading_acknowledged: bool
    configuration_valid: bool
    blocking_reason: str | None


@router.get(
    "/system/broker-environment", response_model=BrokerEnvironmentStatusResponse
)
def broker_environment_status(request: Request) -> BrokerEnvironmentStatusResponse:
    settings = resolve_request_settings(request) or get_settings()
    return BrokerEnvironmentStatusResponse(
        provider=settings.broker_provider,
        environment=settings.broker_environment.value,
        endpoint_classification=settings.broker_endpoint_classification.value,
        dealing_enabled=settings.ig_trading_enabled,
        streaming_enabled=settings.ig_streaming_enabled,
        live_trading_acknowledged=settings.ig_live_trading_acknowledged,
        configuration_valid=True,
        blocking_reason=None,
    )


@router.get("/system/telemetry", response_model=OperationalTelemetryResponse)
def operational_telemetry(
    session: Session = Depends(get_session),
) -> OperationalTelemetryResponse:
    return OperationalTelemetryResponse(
        **OperationalTelemetryService(session).get_summary()
    )
