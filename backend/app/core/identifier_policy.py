from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal


IdentifierClassification = Literal[
    "AUTHORITY_REQUIRED_RAW_DB_ONLY",
    "INTERNAL_CORRELATION_ALLOWED",
    "OPERATOR_SAFE_REDACTED",
    "PUBLIC_API_ALLOWED",
    "SECRET_FORBIDDEN",
    "LEGACY_OR_UNUSED",
]


IdentifierKind = Literal[
    "account_id",
    "broker_reference",
    "correlation_id",
    "request_id",
    "runtime_id",
]


@dataclass(frozen=True)
class IdentifierPolicyEntry:
    location: str
    classification: IdentifierClassification
    notes: str


IDENTIFIER_POLICY: tuple[IdentifierPolicyEntry, ...] = (
    IdentifierPolicyEntry(
        "AllocationAlert.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key used for operator alert acknowledgement and resolution.",
    ),
    IdentifierPolicyEntry(
        "AllocationAlert.alert_key",
        "INTERNAL_CORRELATION_ALLOWED",
        "Internal recurrence key; not broker authority and not operator-facing.",
    ),
    IdentifierPolicyEntry(
        "AllocationAlert.related_intent_ids",
        "PUBLIC_API_ALLOWED",
        "Local intent ids used for operator drill-down and route linking.",
    ),
    IdentifierPolicyEntry(
        "AllocationAlert.related_cycle_ids",
        "PUBLIC_API_ALLOWED",
        "Allocation cycle ids remain operator-visible for local audit correlation.",
    ),
    IdentifierPolicyEntry(
        "AllocationAlert.related_execution_ids",
        "PUBLIC_API_ALLOWED",
        "Local execution ids remain operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "AllocationAlert.details",
        "OPERATOR_SAFE_REDACTED",
        "Structured alert context may carry identifiers but must pass redaction boundaries.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.id",
        "PUBLIC_API_ALLOWED",
        "Local append-only event id used for pagination and drill-down.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.correlation_id",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw correlation/request ids stay durable internally for lifecycle joins and retry analysis.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.runtime_id",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw runtime ids stay durable internally for runtime recovery and lifecycle traceability.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.position_id",
        "PUBLIC_API_ALLOWED",
        "Local position id is safe for operator drill-down.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.trade_id",
        "PUBLIC_API_ALLOWED",
        "Local trade id is safe for operator drill-down.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.execution_id",
        "PUBLIC_API_ALLOWED",
        "Local execution id is safe for operator drill-down.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.actor_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Actor ids are local operator/service identifiers and not broker authority.",
    ),
    IdentifierPolicyEntry(
        "DomainEvent.payload_json",
        "OPERATOR_SAFE_REDACTED",
        "Domain-event payloads may contain correlated identifiers but must be sanitized before persistence and serialization.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.scope_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Observability scope ids are internal correlation handles, not operator-safe truth by default.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.state_key",
        "INTERNAL_CORRELATION_ALLOWED",
        "Observability state keys are internal correlation identifiers for rollups and probes.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.worker_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Worker ids are platform-internal process correlation handles.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.process_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Process ids are internal runtime correlation handles, not operator-facing authority.",
    ),
    IdentifierPolicyEntry(
        "ObservabilityState.payload_json",
        "OPERATOR_SAFE_REDACTED",
        "Observability payloads may include identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "OperatorControlState.id",
        "PUBLIC_API_ALLOWED",
        "Singleton local row id only.",
    ),
    IdentifierPolicyEntry(
        "PromotionRequest.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.id",
        "PUBLIC_API_ALLOWED",
        "Local review record id only.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.scope",
        "OPERATOR_SAFE_REDACTED",
        "Review scope payload may contain local ids and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.facts_payload",
        "OPERATOR_SAFE_REDACTED",
        "Persisted review facts may include identifiers from read models and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.derived_observations",
        "OPERATOR_SAFE_REDACTED",
        "Structured review observations may include identifiers and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.possible_contributors",
        "OPERATOR_SAFE_REDACTED",
        "Structured review contributor payload may include identifiers and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.warnings",
        "OPERATOR_SAFE_REDACTED",
        "Structured review warning payload may include identifiers and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.supporting_metrics",
        "OPERATOR_SAFE_REDACTED",
        "Structured review metrics may include identifiers and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.ai_summary",
        "OPERATOR_SAFE_REDACTED",
        "Persisted summary payload must not carry raw broker/account/request identifiers.",
    ),
    IdentifierPolicyEntry(
        "GeneratedReviewRecord.raw_model_response",
        "LEGACY_OR_UNUSED",
        "Raw LLM text is retained for reviewer diagnostics only and must not become lifecycle authority.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.runtime_id",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Runtime lifecycle authority uses raw runtime ids internally.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.deployment_id",
        "PUBLIC_API_ALLOWED",
        "Local deployment foreign key is safe for operator drill-down and runtime linkage.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.current_position_broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Recovery and reconcile flows require the raw broker reference internally.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.parameters",
        "OPERATOR_SAFE_REDACTED",
        "Runtime parameters must not include secrets; if ids appear they remain operator-safe only through projection.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.startup_context",
        "OPERATOR_SAFE_REDACTED",
        "Startup context may carry correlation/runtime identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "StrategyRuntimeState.strategy_state_snapshot",
        "OPERATOR_SAFE_REDACTED",
        "Runtime snapshots may carry correlated identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "RuntimeLease.lease_name",
        "INTERNAL_CORRELATION_ALLOWED",
        "Lease names are internal coordination identifiers.",
    ),
    IdentifierPolicyEntry(
        "RuntimeLease.owner_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Lease owner ids are process correlation identifiers, not operator authority.",
    ),
    IdentifierPolicyEntry(
        "StrategyDeployment.id",
        "PUBLIC_API_ALLOWED",
        "Local deployment id remains operator-visible for local linking.",
    ),
    IdentifierPolicyEntry(
        "StrategyDeployment.governance_id",
        "PUBLIC_API_ALLOWED",
        "Local governance foreign key only.",
    ),
    IdentifierPolicyEntry(
        "StrategyDeployment.deployment_key",
        "INTERNAL_CORRELATION_ALLOWED",
        "Internal deployment correlation key; not required on operator API surfaces.",
    ),
    IdentifierPolicyEntry(
        "StrategyDeployment.deployment_metadata",
        "OPERATOR_SAFE_REDACTED",
        "Deployment metadata may carry runtime identifiers and must stay sanitized.",
    ),
    IdentifierPolicyEntry(
        "StrategyFamilyGovernance.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "Trade.id",
        "PUBLIC_API_ALLOWED",
        "Local trade id remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "Trade.trade_intent_id",
        "PUBLIC_API_ALLOWED",
        "Local trade-intent foreign key is safe for operator correlation.",
    ),
    IdentifierPolicyEntry(
        "Trade.broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw broker deal reference must remain durable internally for lifecycle reconciliation.",
    ),
    IdentifierPolicyEntry(
        "Trade.close_broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw close broker reference must remain durable internally for lifecycle reconciliation.",
    ),
    IdentifierPolicyEntry(
        "Position.id",
        "PUBLIC_API_ALLOWED",
        "Local position id remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "Position.trade_intent_id",
        "PUBLIC_API_ALLOWED",
        "Local foreign key for operator drill-down and lifecycle joins.",
    ),
    IdentifierPolicyEntry(
        "Position.broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Recovery, reconciliation, and close authority require raw broker position references internally.",
    ),
    IdentifierPolicyEntry(
        "Execution.id",
        "PUBLIC_API_ALLOWED",
        "Local execution id remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "Execution.trade_intent_id",
        "PUBLIC_API_ALLOWED",
        "Local trade-intent foreign key is safe for operator drill-down.",
    ),
    IdentifierPolicyEntry(
        "Execution.client_request_id",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Duplicate suppression and broker retry correlation require the raw client request id internally.",
    ),
    IdentifierPolicyEntry(
        "Execution.broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw broker reference remains required for broker-confirmation authority internally.",
    ),
    IdentifierPolicyEntry(
        "Execution.local_position_id",
        "PUBLIC_API_ALLOWED",
        "Local position foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "Execution.local_trade_id",
        "PUBLIC_API_ALLOWED",
        "Local trade foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "Execution.details",
        "OPERATOR_SAFE_REDACTED",
        "Execution detail payloads may include broker/account/request identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "ReconciliationEvent.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "ReconciliationEvent.trade_intent_id",
        "PUBLIC_API_ALLOWED",
        "Local trade-intent foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "ReconciliationEvent.broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Reconciliation authority needs the raw broker reference internally.",
    ),
    IdentifierPolicyEntry(
        "ReconciliationEvent.local_position_id",
        "PUBLIC_API_ALLOWED",
        "Local position foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "ReconciliationEvent.details",
        "OPERATOR_SAFE_REDACTED",
        "Reconciliation details may include broker/account/request identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.id",
        "PUBLIC_API_ALLOWED",
        "Local trade-intent id remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.allocation_cycle_id",
        "PUBLIC_API_ALLOWED",
        "Allocation cycle ids remain operator-visible for local risk-audit correlation.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw broker entry reference must remain durable internally for lifecycle authority.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.close_broker_reference",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw broker close reference must remain durable internally for lifecycle authority.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.position_id",
        "PUBLIC_API_ALLOWED",
        "Local position foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.trade_id",
        "PUBLIC_API_ALLOWED",
        "Local trade foreign key remains operator-visible for drill-down.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.execution_client_request_id",
        "AUTHORITY_REQUIRED_RAW_DB_ONLY",
        "Raw execution client request id remains durable internally for duplicate suppression and audit linkage.",
    ),
    IdentifierPolicyEntry(
        "TradeIntent.details",
        "OPERATOR_SAFE_REDACTED",
        "Intent details may include broker/account/request identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "AllocationCycle.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "AllocationCycle.cycle_id",
        "PUBLIC_API_ALLOWED",
        "Allocation cycle ids remain operator-visible for local correlation.",
    ),
    IdentifierPolicyEntry(
        "AllocationCycle.binding_budget_counts",
        "OPERATOR_SAFE_REDACTED",
        "Structured allocation counts may include intent/execution linkage and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "AllocationCycle.rejection_reason_counts",
        "OPERATOR_SAFE_REDACTED",
        "Structured allocation counts may include identifier-bearing reasons and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "AllocationCycle.details",
        "OPERATOR_SAFE_REDACTED",
        "Structured allocation details may include broker/account/request identifiers and must remain sanitized.",
    ),
    IdentifierPolicyEntry(
        "WatchlistEntry.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "OperatorShortlistEntry.id",
        "PUBLIC_API_ALLOWED",
        "Local primary key only.",
    ),
    IdentifierPolicyEntry(
        "OperatorShortlistEntry.actor_id",
        "INTERNAL_CORRELATION_ALLOWED",
        "Local operator actor id is internal correlation, not broker authority.",
    ),
    IdentifierPolicyEntry(
        "api.dashboard.DashboardBrokerInfoResponse.accountId",
        "OPERATOR_SAFE_REDACTED",
        "Operator dashboard may show only a masked/fingerprinted broker account identifier.",
    ),
    IdentifierPolicyEntry(
        "api.dashboard.DashboardRunningStrategyResponse.brokerReference",
        "OPERATOR_SAFE_REDACTED",
        "Dashboard running-strategy surfaces may show only a safe broker-reference projection.",
    ),
    IdentifierPolicyEntry(
        "api.trading.TradeResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Trade route surfaces may show only a safe broker-reference projection.",
    ),
    IdentifierPolicyEntry(
        "api.trading.TradeResponse.close_broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Trade route surfaces may show only a safe close broker-reference projection.",
    ),
    IdentifierPolicyEntry(
        "api.trading.OpenPositionResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Position route surfaces may show only a safe broker-reference projection.",
    ),
    IdentifierPolicyEntry(
        "api.execution.ExecutionResponse.client_request_id",
        "OPERATOR_SAFE_REDACTED",
        "Execution route surfaces may show only a safe request-correlation projection.",
    ),
    IdentifierPolicyEntry(
        "api.execution.ExecutionResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Execution route surfaces may show only a safe broker-reference projection.",
    ),
    IdentifierPolicyEntry(
        "api.events.DomainEventResponse.correlation_id",
        "OPERATOR_SAFE_REDACTED",
        "Event routes may expose only a safe correlation projection while raw ids remain internal.",
    ),
    IdentifierPolicyEntry(
        "api.events.DomainEventResponse.runtime_id",
        "OPERATOR_SAFE_REDACTED",
        "Event routes may expose only a safe runtime projection while raw ids remain internal.",
    ),
    IdentifierPolicyEntry(
        "api.control_plane.ControlPlanePersistedRuntimeResponse.runtime_id",
        "OPERATOR_SAFE_REDACTED",
        "Control-plane runtime projections may show only safe runtime identifiers.",
    ),
    IdentifierPolicyEntry(
        "api.control_plane.ControlPlaneRuntimeSummaryResponse.active_runtime_id",
        "OPERATOR_SAFE_REDACTED",
        "Control-plane runtime summaries may show only safe runtime identifiers.",
    ),
    IdentifierPolicyEntry(
        "api.strategies.StrategyRuntimeResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Strategy runtime summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.strategies.StrategyPositionSummaryResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Strategy position summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.strategies.StrategyPersistedRuntimeResponse.runtime_id",
        "OPERATOR_SAFE_REDACTED",
        "Strategy persisted runtimes may show only safe runtime identifiers.",
    ),
    IdentifierPolicyEntry(
        "api.allocation.AllocationIntentExecutionResponse.client_request_id",
        "OPERATOR_SAFE_REDACTED",
        "Allocation execution summaries may show only safe request-correlation projections.",
    ),
    IdentifierPolicyEntry(
        "api.allocation.AllocationIntentExecutionResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Allocation execution summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.allocation.AllocationIntentPositionResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Allocation position summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.allocation.AllocationIntentTradeResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Allocation trade summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.allocation.AllocationIntentTradeResponse.close_broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Allocation trade summaries may show only safe broker-reference projections.",
    ),
    IdentifierPolicyEntry(
        "api.broker.BrokerPositionResponse.broker_reference",
        "OPERATOR_SAFE_REDACTED",
        "Broker position reads may show only a safe broker-reference projection.",
    ),
)


POLICY_BY_LOCATION = {entry.location: entry for entry in IDENTIFIER_POLICY}

FORBIDDEN_RESPONSE_FIELD_PARTS = (
    "authorization",
    "password",
    "secret",
    "token",
    "session",
    "header",
    "api_key",
    "apikey",
)

SENSITIVE_PAYLOAD_KEY_PARTS = {
    "account_id": ("account_id", "accountid", "current_account_id", "currentaccountid"),
    "broker_reference": (
        "deal_reference",
        "dealreference",
        "deal_id",
        "dealid",
        "broker_reference",
        "close_broker_reference",
        "current_position_broker_reference",
    ),
    "correlation_id": ("correlation_id",),
    "request_id": ("client_request_id", "execution_client_request_id"),
    "runtime_id": ("runtime_id",),
    "secret": (
        "authorization",
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "session",
        "credential",
        "header",
    ),
}

PERSISTED_IDENTIFIER_FIELD_NAMES = {
    entry.location for entry in IDENTIFIER_POLICY if not entry.location.startswith("api.")
}


def project_identifier(
    value: str | None,
    *,
    kind: IdentifierKind,
) -> dict[str, str] | None:
    if not value:
        return None
    return {
        "display": _display_identifier(value, kind=kind),
        "fingerprint": identifier_fingerprint(value),
    }


def identifier_fingerprint(value: str) -> str:
    return f"fp:{sha256(value.encode('utf-8')).hexdigest()[:12]}"


def identifier_matches_fingerprint(
    value: str | None,
    *,
    fingerprint: str | None,
) -> bool:
    if value is None or not fingerprint:
        return False
    return identifier_fingerprint(value) == fingerprint


def _display_identifier(value: str, *, kind: IdentifierKind) -> str:
    suffix = value[-4:] if len(value) > 4 else value
    prefix = {
        "account_id": "acct",
        "broker_reference": "ref",
        "correlation_id": "corr",
        "request_id": "req",
        "runtime_id": "rt",
    }[kind]
    return f"{prefix} …{suffix}"
