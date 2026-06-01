from __future__ import annotations

from typing import get_args, get_origin

from app.api.contracts.allocation import (
    AllocationIntentExecutionResponse,
    AllocationIntentPositionResponse,
    AllocationIntentTradeResponse,
)
from app.api.contracts.control_plane import (
    ControlPlanePersistedRuntimeResponse,
    ControlPlaneRuntimeSummaryResponse,
)
from app.api.contracts.dashboard import (
    DashboardBrokerInfoResponse,
    DashboardRunningStrategyResponse,
)
from app.api.contracts.identifiers import IdentifierProjection
from app.api.contracts.strategies import (
    StrategyPersistedRuntimeResponse,
    StrategyPositionSummaryResponse,
    StrategyRuntimeResponse,
)
from app.api.contracts.trading import OpenPositionResponse, TradeResponse
from app.api.routes.broker import BrokerPositionResponse
from app.api.routes.events import DomainEventResponse
from app.api.routes.executions import ExecutionResponse
from app.core.identifier_policy import (
    FORBIDDEN_RESPONSE_FIELD_PARTS,
    IDENTIFIER_POLICY,
    POLICY_BY_LOCATION,
    SENSITIVE_PAYLOAD_KEY_PARTS,
    identifier_fingerprint,
    project_identifier,
)
from app.core.redaction import sanitize_payload
from app.models.allocation_alert import AllocationAlert
from app.models.domain_event import DomainEvent
from app.models.observability import ObservabilityState
from app.models.operator_control import OperatorControlState
from app.models.promotion_request import PromotionRequest
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.runtime_leadership import RuntimeLease
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import (
    AllocationCycle,
    Execution,
    Position,
    ReconciliationEvent,
    Trade,
    TradeIntent,
)
from app.models.watchlist import OperatorShortlistEntry, WatchlistEntry


PERSISTED_MODELS = (
    AllocationAlert,
    DomainEvent,
    ObservabilityState,
    OperatorControlState,
    OperatorShortlistEntry,
    PromotionRequest,
    GeneratedReviewRecord,
    StrategyRuntimeState,
    RuntimeLease,
    StrategyDeployment,
    StrategyFamilyGovernance,
    AllocationCycle,
    Execution,
    Position,
    ReconciliationEvent,
    Trade,
    TradeIntent,
    WatchlistEntry,
)

RESPONSE_MODELS = (
    AllocationIntentExecutionResponse,
    AllocationIntentPositionResponse,
    AllocationIntentTradeResponse,
    ControlPlanePersistedRuntimeResponse,
    ControlPlaneRuntimeSummaryResponse,
    DashboardBrokerInfoResponse,
    DashboardRunningStrategyResponse,
    TradeResponse,
    OpenPositionResponse,
    StrategyPersistedRuntimeResponse,
    StrategyPositionSummaryResponse,
    StrategyRuntimeResponse,
    BrokerPositionResponse,
    DomainEventResponse,
    ExecutionResponse,
)

IDENTIFIER_JSON_FIELDS = {
    "details",
    "payload_json",
    "scope",
    "facts_payload",
    "derived_observations",
    "possible_contributors",
    "warnings",
    "supporting_metrics",
    "ai_summary",
    "raw_model_response",
    "parameters",
    "startup_context",
    "strategy_state_snapshot",
    "deployment_metadata",
    "binding_budget_counts",
    "rejection_reason_counts",
}

SENSITIVE_RESPONSE_FIELDS = {
    DashboardBrokerInfoResponse: ("accountId",),
    DashboardRunningStrategyResponse: ("brokerReference",),
    TradeResponse: ("broker_reference", "close_broker_reference"),
    OpenPositionResponse: ("broker_reference",),
    StrategyRuntimeResponse: ("broker_reference",),
    StrategyPositionSummaryResponse: ("broker_reference",),
    StrategyPersistedRuntimeResponse: ("runtime_id",),
    ControlPlanePersistedRuntimeResponse: ("runtime_id",),
    ControlPlaneRuntimeSummaryResponse: ("active_runtime_id",),
    AllocationIntentExecutionResponse: ("client_request_id", "broker_reference"),
    AllocationIntentPositionResponse: ("broker_reference",),
    AllocationIntentTradeResponse: ("broker_reference", "close_broker_reference"),
    BrokerPositionResponse: ("broker_reference",),
    DomainEventResponse: ("correlation_id", "runtime_id"),
    ExecutionResponse: ("client_request_id", "broker_reference"),
}


def _candidate_persisted_identifier_fields() -> set[str]:
    candidates: set[str] = set()
    for model in PERSISTED_MODELS:
        for field_name in model.model_fields:
            normalized = field_name.lower()
            if (
                field_name == "id"
                or normalized.endswith("_id")
                or normalized.endswith("_ids")
                or "reference" in normalized
                or normalized.endswith("_key")
                or normalized in IDENTIFIER_JSON_FIELDS
                or normalized in {"owner_id", "lease_name", "scope_id", "worker_id", "actor_id"}
            ):
                candidates.add(f"{model.__name__}.{field_name}")
    return candidates


def _annotation_includes_identifier_projection(annotation: object) -> bool:
    if annotation is IdentifierProjection:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    return any(arg is IdentifierProjection for arg in get_args(annotation))


def test_identifier_policy_guard_covers_all_persisted_identifier_fields():
    assert _candidate_persisted_identifier_fields() <= {
        entry.location for entry in IDENTIFIER_POLICY if not entry.location.startswith("api.")
    }


def test_identifier_policy_guard_forbids_secret_like_response_fields():
    for model in RESPONSE_MODELS:
        for field_name in model.model_fields:
            normalized = field_name.lower()
            assert not any(
                forbidden in normalized for forbidden in FORBIDDEN_RESPONSE_FIELD_PARTS
            ), f"{model.__name__}.{field_name} must not expose secret/header/token fields."


def test_identifier_policy_guard_requires_safe_projection_for_sensitive_response_fields():
    for model, fields in SENSITIVE_RESPONSE_FIELDS.items():
        for field_name in fields:
            field = model.model_fields[field_name]
            assert _annotation_includes_identifier_projection(field.annotation), (
                f"{model.__name__}.{field_name} must use IdentifierProjection instead "
                "of a raw string."
            )


def test_identifier_policy_guard_redacts_all_sensitive_payload_identifier_families():
    sample_payload = {
        "Authorization": "Bearer secret-token",
        "account_id": "ACC-12345",
        "broker_reference": "DEAL-54321",
        "close_broker_reference": "DEAL-77777",
        "client_request_id": "entry-request-1",
        "execution_client_request_id": "close-request-1",
        "correlation_id": "corr-1",
        "runtime_id": "runtime-1",
    }

    sanitized = sanitize_payload(sample_payload)

    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["account_id"].startswith("[REDACTED_ACCOUNT_ID:")
    assert sanitized["broker_reference"].startswith("[REDACTED_BROKER_REF:")
    assert sanitized["close_broker_reference"].startswith("[REDACTED_BROKER_REF:")
    assert sanitized["client_request_id"].startswith("[REDACTED_REQUEST_ID:")
    assert sanitized["execution_client_request_id"].startswith("[REDACTED_REQUEST_ID:")
    assert sanitized["correlation_id"].startswith("[REDACTED_CORRELATION_ID:")
    assert sanitized["runtime_id"].startswith("[REDACTED_RUNTIME_ID:")

    covered_keys = {
        key
        for family in SENSITIVE_PAYLOAD_KEY_PARTS.values()
        for key in family
    }
    assert {
        "authorization",
        "account_id",
        "broker_reference",
        "client_request_id",
        "correlation_id",
        "runtime_id",
    } <= covered_keys


def test_identifier_projection_fingerprint_is_stable_for_operator_correlation():
    request_projection = project_identifier("shared-correlation-1", kind="request_id")
    correlation_projection = project_identifier(
        "shared-correlation-1",
        kind="correlation_id",
    )
    runtime_projection = project_identifier("runtime-1", kind="runtime_id")

    assert request_projection is not None
    assert correlation_projection is not None
    assert runtime_projection is not None
    assert request_projection["fingerprint"] == correlation_projection["fingerprint"]
    assert request_projection["fingerprint"] == identifier_fingerprint(
        "shared-correlation-1"
    )
    assert runtime_projection["fingerprint"] == identifier_fingerprint("runtime-1")


def test_identifier_policy_manifest_uses_only_supported_classifications():
    allowed = {
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "INTERNAL_CORRELATION_ALLOWED",
        "OPERATOR_SAFE_REDACTED",
        "PUBLIC_API_ALLOWED",
        "SECRET_FORBIDDEN",
        "LEGACY_OR_UNUSED",
    }

    for entry in IDENTIFIER_POLICY:
        assert entry.classification in allowed, entry
        assert POLICY_BY_LOCATION[entry.location] == entry


def test_identifier_routes_expose_safe_projections_and_fingerprint_filter(
    monkeypatch, session, client_factory, fixed_now
):
    monkeypatch.setattr(
        "app.services.domain_event_service.engine",
        session.get_bind(),
    )
    session.add(
        DomainEvent(
            created_at=fixed_now,
            event_type="execution.order_submitted",
            category="execution",
            severity="info",
            source="tests.identifier_policy",
            correlation_id="entry-route-1",
            runtime_id="runtime-route-1",
            title="Execution submitted",
            message="Operator-safe projection check.",
        )
    )
    session.commit()

    with client_factory() as client:
        response = client.get(
            f"/events?correlation_fingerprint={identifier_fingerprint('entry-route-1')}"
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["correlation_id"] == project_identifier(
        "entry-route-1",
        kind="correlation_id",
    )
    assert payload[0]["runtime_id"] == project_identifier(
        "runtime-route-1",
        kind="runtime_id",
    )
