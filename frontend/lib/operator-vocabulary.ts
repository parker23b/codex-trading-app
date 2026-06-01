import type {
  AlignmentStatus,
  BrokerExecutionSource,
  BrokerSyncStatus,
  ControlMode,
  ExecutionStatus,
  GovernanceApprovalState,
  OpenRiskManagementState,
  RiskTruthConfidence,
  RuntimeMode,
  StrategyDeploymentState,
  TradeIntentState,
} from "./types";

export type VocabularyTone = "neutral" | "positive" | "warning" | "negative" | "inactive";
export type BadgeVocabularyTone = "neutral" | "positive" | "warning" | "negative";

type VocabularyMeta = {
  label: string;
  tone: VocabularyTone;
  detail: string;
};

type BadgeVocabularyMeta = {
  label: string;
  tone: BadgeVocabularyTone;
  detail: string;
};

function titleize(value: string) {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function riskTruthConfidenceMeta(
  value?: RiskTruthConfidence | string | null,
): VocabularyMeta {
  switch (value) {
    case "EXACT_FILL_DERIVED":
      return {
        label: "Exact",
        tone: "positive",
        detail: "Fill-derived risk was recomputed from actual execution data.",
      };
    case "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED":
      return {
        label: "Broker Confirmed",
        tone: "neutral",
        detail:
          "Risk uses broker-confirmed average fill and size, but exact recomputation is still estimate-based.",
      };
    case "PARTIAL_FILL_PROVISIONAL":
      return {
        label: "Provisional",
        tone: "warning",
        detail:
          "Risk reflects a partial fill and may change as the order completes or is reconciled.",
      };
    case "SUBMITTED_EXECUTABLE_ESTIMATE":
      return {
        label: "Submitted Estimate",
        tone: "warning",
        detail: "Risk is based on broker-valid submitted size, not final fill truth.",
      };
    case "ALLOCATION_INTENT_ONLY":
      return {
        label: "Allocated Only",
        tone: "inactive",
        detail: "Risk still reflects allocator intent rather than broker-confirmed execution.",
      };
    case "INCOMPLETE_DEGRADED":
      return {
        label: "Degraded",
        tone: "negative",
        detail: "Fill truth is incomplete or inconsistent; post-trade risk remains degraded.",
      };
    case "SIMULATED_LOCAL_FILL":
      return {
        label: "Simulated",
        tone: "warning",
        detail: "Risk comes from a local simulated fill and is not broker-confirmed truth.",
      };
    case "UNKNOWN":
    default:
      return {
        label: "Unknown",
        tone: "negative",
        detail: "Risk truth confidence is explicitly unknown or unavailable.",
      };
  }
}

export function closeExecutionSourceMeta(
  source?: BrokerExecutionSource | string | null,
): BadgeVocabularyMeta {
  switch (source) {
    case "SIMULATED_LOCAL_CLOSE":
      return {
        label: "Simulated local close",
        tone: "warning",
        detail: "Local simulation; not broker-confirmed close truth.",
      };
    case "SIMULATED_LOCAL_FILL":
      return {
        label: "Simulated local fill",
        tone: "warning",
        detail: "Local simulation; not broker-confirmed execution truth.",
      };
    case "BROKER_CONFIRMED":
      return {
        label: "Broker confirmed",
        tone: "positive",
        detail: "Execution result came from broker-confirmed truth.",
      };
    default:
      return {
        label: "Close source unknown",
        tone: "warning",
        detail: "Backend did not provide broker-confirmed or simulated close provenance.",
      };
  }
}

export function brokerSyncStatusMeta(
  status?: BrokerSyncStatus | string | null,
): BadgeVocabularyMeta {
  switch (status) {
    case "CONFIRMED":
      return {
        label: "Broker synced",
        tone: "positive",
        detail: "Position state is currently confirmed against broker truth.",
      };
    case "PENDING":
      return {
        label: "Pending sync",
        tone: "warning",
        detail: "Broker sync is still pending and should not be treated as confirmed truth.",
      };
    case "MISSING_AT_BROKER":
      return {
        label: "Missing at broker",
        tone: "negative",
        detail: "Local position no longer matches broker truth and needs reconciliation.",
      };
    case "SIMULATED_LOCAL_FILL":
      return {
        label: "Simulated local fill",
        tone: "warning",
        detail: "Open-risk provenance comes from local simulated fill behavior, not broker truth.",
      };
    case "SIMULATED_LOCAL_CLOSE":
      return {
        label: "Simulated local close",
        tone: "warning",
        detail: "Close provenance comes from local simulated behavior, not broker truth.",
      };
    case "UNAVAILABLE":
      return {
        label: "Sync unavailable",
        tone: "negative",
        detail: "Broker sync state is unavailable and must not be read as healthy or exact.",
      };
    case "UNKNOWN":
    default:
      return {
        label: "Sync unknown",
        tone: "negative",
        detail: "Broker sync state is unknown and must not be treated as confirmed.",
      };
  }
}

export function controlModeMeta(
  mode?: ControlMode | string | null,
): VocabularyMeta {
  switch (mode) {
    case "MANUAL":
      return {
        label: "Manual control",
        tone: "warning",
        detail: "Runtime ownership is manual and must not be mistaken for autonomous control.",
      };
    case "AUTO":
      return {
        label: "Autonomous control",
        tone: "positive",
        detail: "Runtime ownership is autonomous, subject to governance and operational gates.",
      };
    default:
      return {
        label: "Control mode unknown",
        tone: "negative",
        detail: "Backend did not provide a supported control mode; do not assume manual or autonomous ownership.",
      };
  }
}

export function runtimeModeMeta(
  mode?: RuntimeMode | string | null,
): VocabularyMeta {
  switch (mode) {
    case "NORMAL":
      return {
        label: "Normal runtime",
        tone: "positive",
        detail: "Runtime may evaluate its normal entry and exit behavior, subject to backend gates.",
      };
    case "EXITS_ONLY":
      return {
        label: "Exits-only runtime",
        tone: "warning",
        detail: "Runtime is restricted to protective or exit handling and must not be read as entry-capable.",
      };
    case "STOPPED":
      return {
        label: "Stopped runtime",
        tone: "inactive",
        detail: "Runtime process is stopped; any remaining open risk still needs separate visibility and handling.",
      };
    default:
      return {
        label: "Runtime mode unknown",
        tone: "negative",
        detail: "Backend did not provide a supported runtime mode; do not assume normal, exits-only, or stopped state.",
      };
  }
}

export function governanceApprovalStateMeta(
  state?: GovernanceApprovalState | string | null,
): VocabularyMeta {
  switch (state) {
    case "APPROVED":
      return {
        label: "Approved",
        tone: "positive",
        detail: "Governance permits this family, but approval alone does not imply deployment or running runtime truth.",
      };
    case "NOT_APPROVED":
      return {
        label: "Not approved",
        tone: "inactive",
        detail: "Governance has not approved autonomous operation for this family.",
      };
    case "DISABLED":
      return {
        label: "Disabled",
        tone: "negative",
        detail: "Governance is explicitly disabled and new autonomous entries must remain blocked.",
      };
    default:
      return {
        label: "Governance unknown",
        tone: "negative",
        detail: "Backend returned an unsupported governance state; do not treat it as approved.",
      };
  }
}

export function feedSourceStateMeta(
  state?: "LIVE" | "POLLING_FALLBACK" | "STALE" | "DISCONNECTED" | string | null,
  options?: { recovered?: boolean },
): VocabularyMeta {
  if (options?.recovered && state === "LIVE") {
    return {
      label: "Recovered",
      tone: "warning",
      detail:
        "Stream truth recovered after degradation; confirm fresh ticks continue before treating the path as stable.",
    };
  }

  switch (state) {
    case "LIVE":
      return {
        label: "Live",
        tone: "positive",
        detail: "Streaming market data is connected and currently acting as the live source.",
      };
    case "POLLING_FALLBACK":
      return {
        label: "Polling fallback",
        tone: "warning",
        detail:
          "Fallback polling is active because live streaming is unavailable; do not treat this path as full live stream truth.",
      };
    case "STALE":
      return {
        label: "Stale",
        tone: "warning",
        detail: "The latest live tick is stale and should not be treated as fresh stream truth.",
      };
    case "DISCONNECTED":
      return {
        label: "Disconnected",
        tone: "negative",
        detail: "Live streaming is disconnected or unavailable; freshness and entry truth are degraded.",
      };
    default:
      return {
        label: "Feed state unknown",
        tone: "negative",
        detail: "Backend returned an unsupported feed-source state; do not treat it as live.",
      };
  }
}

export function deploymentStateMeta(
  state?: StrategyDeploymentState | string | null,
): VocabularyMeta {
  switch (state) {
    case "NOT_APPROVED":
      return {
        label: "Not approved",
        tone: "inactive",
        detail: "Deployment is blocked by governance approval and is not deployable truth.",
      };
    case "APPROVED":
      return {
        label: "Approved",
        tone: "neutral",
        detail: "Deployment is approved as intent, but that alone does not imply runtime alignment.",
      };
    case "AUTO_DEPLOYABLE":
      return {
        label: "Auto deployable",
        tone: "neutral",
        detail: "Backend considers the family deployable, but that is not the same as already running.",
      };
    case "AUTO_DEPLOYED":
      return {
        label: "Auto deployed",
        tone: "positive",
        detail: "Deployment intent is active, but runtime alignment should still be checked separately.",
      };
    case "AUTO_PAUSED":
      return {
        label: "Auto paused",
        tone: "warning",
        detail: "Autonomous deployment is paused and should not be mistaken for active entry readiness.",
      };
    case "DEGRADED":
      return {
        label: "Degraded",
        tone: "warning",
        detail: "Deployment is degraded and requires operator attention before it is treated as healthy.",
      };
    case "BLOCKED":
      return {
        label: "Blocked",
        tone: "negative",
        detail: "Deployment is blocked and must not be read as active or ready.",
      };
    case "EMERGENCY_STOPPED":
      return {
        label: "Emergency stopped",
        tone: "negative",
        detail: "Emergency stop is active; new entries are blocked and open-risk handling must stay visible.",
      };
    default:
      return {
        label: "Deployment unknown",
        tone: "negative",
        detail: "Backend returned an unsupported deployment state; do not treat it as healthy or active.",
      };
  }
}

export function alignmentStatusMeta(
  status?: AlignmentStatus | string | null,
): VocabularyMeta {
  switch (status) {
    case "ALIGNED":
      return {
        label: "Aligned",
        tone: "positive",
        detail: "Runtime and deployment truth match on the checked fields.",
      };
    case "MISMATCH":
      return {
        label: "Mismatch",
        tone: "warning",
        detail: "Runtime and deployment truth diverge and should not be treated as aligned.",
      };
    case "NO_DEPLOYMENT":
      return {
        label: "No deployment",
        tone: "inactive",
        detail: "No deployment target exists, so alignment truth is unavailable for autonomous deployment.",
      };
    default:
      return {
        label: "Alignment unknown",
        tone: "negative",
        detail: "Backend returned an unsupported alignment state; do not treat it as aligned.",
      };
  }
}

export function openRiskManagementStateMeta(
  state?: OpenRiskManagementState | string | null,
): VocabularyMeta {
  switch (state) {
    case "NO_OPEN_RISK":
      return {
        label: "No open risk",
        tone: "positive",
        detail: "Backend reports no known open exposure requiring runtime or reconciliation handling.",
      };
    case "MANAGED":
      return {
        label: "Managed open risk",
        tone: "positive",
        detail: "Known open exposure still exists, but backend reports an active management path.",
      };
    case "EXITS_ONLY":
      return {
        label: "Exits-only open risk",
        tone: "warning",
        detail: "Open exposure remains live and should be managed under exits-only protection.",
      };
    case "UNMANAGED_OPEN_RISK":
      return {
        label: "Unmanaged open risk",
        tone: "negative",
        detail: "Known open exposure lacks a safe active management path and requires operator attention.",
      };
    case "UNAVAILABLE":
      return {
        label: "Open-risk state unavailable",
        tone: "negative",
        detail: "Backend did not provide open-risk management truth; do not treat the state as cleared.",
      };
    case "UNKNOWN":
    default:
      return {
        label: "Open-risk state unknown",
        tone: "negative",
        detail: "Open-risk management truth is unknown or unsupported and must not be treated as safe.",
      };
  }
}

export function executionStatusMeta(
  status?: ExecutionStatus | string | null,
): BadgeVocabularyMeta {
  switch (status) {
    case "SUBMISSION_PENDING":
      return {
        label: "Submission pending",
        tone: "warning",
        detail: "Broker submission is still pending and is not fill-confirmed truth.",
      };
    case "SIGNAL_GENERATED":
      return {
        label: "Signal generated",
        tone: "warning",
        detail: "Legacy decision-style execution row; not a broker outcome.",
      };
    case "RISK_APPROVED":
      return {
        label: "Risk approved",
        tone: "warning",
        detail: "Legacy decision-style execution row; not a broker-confirmed execution state.",
      };
    case "RISK_REJECTED":
      return {
        label: "Risk rejected",
        tone: "warning",
        detail: "Legacy decision-style execution row; no broker fill occurred.",
      };
    case "ORDER_SUBMITTED":
      return {
        label: "Order submitted",
        tone: "warning",
        detail: "Submission reached the broker path, but final fill truth is still pending.",
      };
    case "ORDER_ACKNOWLEDGED":
      return {
        label: "Order acknowledged",
        tone: "warning",
        detail: "Broker acknowledged the request, but final fill truth is still pending.",
      };
    case "FILL_PARTIAL":
      return {
        label: "Partial fill",
        tone: "warning",
        detail: "Only a partial fill is known; remaining exposure may still be unresolved.",
      };
    case "FILL_FULL":
      return {
        label: "Fill full",
        tone: "positive",
        detail: "A full fill is recorded for this execution attempt.",
      };
    case "POSITION_OPENED":
      return {
        label: "Position opened",
        tone: "positive",
        detail: "Open position truth is recorded for this execution attempt.",
      };
    case "CLOSE_REQUESTED":
      return {
        label: "Close requested",
        tone: "warning",
        detail: "Close intent exists, but close confirmation is still pending.",
      };
    case "CLOSE_CONFIRMED":
      return {
        label: "Close confirmed",
        tone: "positive",
        detail: "Close confirmation is recorded for this execution attempt.",
      };
    case "FAILED":
      return {
        label: "Failed",
        tone: "negative",
        detail: "Execution failed and requires operator review of the preserved reason.",
      };
    case "CANCELLED":
      return {
        label: "Cancelled",
        tone: "warning",
        detail: "Execution was cancelled and should not be interpreted as a filled result.",
      };
    case "NEEDS_MANUAL_REVIEW":
      return {
        label: "Needs manual review",
        tone: "negative",
        detail: "Execution truth is ambiguous or degraded and requires manual review.",
      };
    default:
      return {
        label: "Unknown execution state",
        tone: "negative",
        detail: "Backend returned an unsupported execution state; do not treat it as healthy or final.",
      };
  }
}

export function tradeIntentStateMeta(
  state?: TradeIntentState | string | null,
): BadgeVocabularyMeta {
  switch (state) {
    case "PROPOSED":
      return {
        label: "Proposed",
        tone: "neutral",
        detail: "Intent exists but has not been admitted yet.",
      };
    case "REJECTED":
      return {
        label: "Rejected",
        tone: "warning",
        detail: "Intent was rejected and did not become executable broker truth.",
      };
    case "APPROVED":
      return {
        label: "Approved",
        tone: "neutral",
        detail: "Intent is admitted, but no broker-confirmed execution is implied yet.",
      };
    case "SUBMITTED":
      return {
        label: "Submitted",
        tone: "warning",
        detail: "Intent has entered the broker submission path but is not final truth yet.",
      };
    case "ACKNOWLEDGED":
      return {
        label: "Acknowledged",
        tone: "warning",
        detail: "Intent has broker acknowledgement but final fill truth is still pending.",
      };
    case "PARTIALLY_FILLED":
      return {
        label: "Partially filled",
        tone: "warning",
        detail: "Intent remains provisional because only a partial fill is known.",
      };
    case "FILLED":
      return {
        label: "Filled",
        tone: "positive",
        detail: "Filled intent state is recorded.",
      };
    case "POSITION_OPENED":
      return {
        label: "Position opened",
        tone: "positive",
        detail: "Open position truth is recorded on the intent.",
      };
    case "CLOSE_REQUESTED":
      return {
        label: "Close requested",
        tone: "warning",
        detail: "Close path has started, but close completion is not yet confirmed.",
      };
    case "CLOSED":
      return {
        label: "Closed",
        tone: "positive",
        detail: "Closed lifecycle truth is recorded on the intent.",
      };
    case "FAILED":
      return {
        label: "Failed",
        tone: "negative",
        detail: "Intent execution failed and requires the recorded failure reason.",
      };
    case "CANCELLED":
      return {
        label: "Cancelled",
        tone: "warning",
        detail: "Intent was cancelled and should not be shown as filled or open.",
      };
    case "EXTERNAL_POSITION_ADOPTED":
      return {
        label: "External position adopted",
        tone: "warning",
        detail: "Open risk was adopted from broker truth rather than normal strategy-owned entry.",
      };
    case "RECOVERED_POSITION_ATTACHED":
      return {
        label: "Recovered position attached",
        tone: "warning",
        detail: "Open risk was recovered and attached with recovery provenance.",
      };
    case "FORCED_RECONCILIATION_CLOSE":
      return {
        label: "Forced reconciliation close",
        tone: "negative",
        detail: "Lifecycle was closed through reconciliation rather than normal broker close flow.",
      };
    default:
      return {
        label: titleize(state ?? "UNKNOWN"),
        tone: "negative",
        detail: "Backend returned an unsupported intent state; do not treat it as healthy or exact.",
      };
  }
}
