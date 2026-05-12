import { formatInstrumentLabel } from "@/lib/format";
import type {
  AllocationAlert,
  AllocationExposureSummary,
  BrokerAuthStatus,
  ControlPlaneFamily,
  ControlPlaneSummary,
  CoverageSummary,
  DomainEvent,
  Execution,
  OperationalTelemetry,
  Position,
  StrategyDefinition,
  StreamHealthStatus,
} from "@/lib/types";

export type LiveTone = "neutral" | "positive" | "warning" | "negative" | "inactive";
export type LiveSelectionType = "instrument" | "strategy" | "anomaly" | "activity";
export type LiveSelection = { type: LiveSelectionType; id: string } | null;

type LiveDataErrors = {
  positions: string | null;
  executions: string | null;
  strategies: string | null;
  brokerAuth: string | null;
  streamHealth: string | null;
  coverage: string | null;
  controlPlane: string | null;
  telemetry: string | null;
  exposure: string | null;
  alerts: string | null;
  events: string | null;
};

type LiveDataResources = {
  positions: Position[];
  executions: Execution[];
  strategies: StrategyDefinition[];
  brokerAuth: BrokerAuthStatus;
  streamHealth: StreamHealthStatus;
  coverage: CoverageSummary;
  controlPlane: ControlPlaneSummary;
  telemetry: OperationalTelemetry;
  exposure: AllocationExposureSummary;
  alerts: AllocationAlert[];
  events: DomainEvent[];
  errors: LiveDataErrors;
  refreshedAt: string;
};

export type LiveStatusChip = {
  id: string;
  label: string;
  value: string;
  tone: LiveTone;
  meta: string;
  source: string;
};

export type LiveActivityItem = {
  id: string;
  title: string;
  detail: string;
  tone: LiveTone;
  timestamp: string;
  relativeTime: string;
  entityType: "instrument" | "strategy" | "system" | "anomaly";
  entityId: string;
  groupCount: number;
  source: string;
  relatedStrategy?: string | null;
  relatedInstrument?: string | null;
};

export type LiveInstrumentItem = {
  id: string;
  canonical: string;
  label: string;
  assetClass: string;
  state: "active" | "idle" | "blocked" | "degraded" | "unknown";
  tone: LiveTone;
  bias: "long" | "short" | "neutral" | "mixed" | "unknown";
  significance: number;
  riskPercent: number | null;
  activeStrategyCount: number;
  activeStrategies: string[];
  activePositionCount: number;
  healthSummary: string;
  constraint: string | null;
  whyActive: string;
  isAnomalous: boolean;
  canonicalIds: string[];
};

export type LiveStrategyItem = {
  id: string;
  name: string;
  tone: LiveTone;
  mode: "scaling" | "holding" | "waiting" | "blocked" | "constrained" | "degraded" | "idle" | "unknown";
  summary: string;
  activeInstruments: string[];
  runtimeCount: number;
  openPositionCount: number;
  warnings: string[];
  isAnomalous: boolean;
};

export type LiveAnomalyItem = {
  id: string;
  title: string;
  explanation: string;
  whyItMatters: string;
  affects: string[];
  tone: LiveTone;
  severityRank: number;
  timestamp: string;
  source: string;
  entityType: "instrument" | "strategy" | "system";
  entityId: string;
};

export type LiveInspectionLink = {
  label: string;
  href: string;
};

export type LiveInspectionSection = {
  label: string;
  value: string;
};

export type LiveInspectionModel = {
  title: string;
  subtitle: string;
  tone: LiveTone;
  kicker: string;
  status: string;
  freshness: string;
  source: string;
  sections: LiveInspectionSection[];
  related: string[];
  recentNotes: string[];
  identifiers: string[];
  links: LiveInspectionLink[];
};

export type LiveSystemViewModel = {
  trustRail: LiveStatusChip[];
  activity: LiveActivityItem[];
  instruments: LiveInstrumentItem[];
  strategies: LiveStrategyItem[];
  anomalies: LiveAnomalyItem[];
  assetClasses: string[];
  inspection: Record<string, LiveInspectionModel>;
  defaultSelection: LiveSelection;
  dataWarnings: string[];
};

const UNKNOWN_LABEL = "Unknown";

function toTitleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatShortTime(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatRelativeTime(value: string, now = Date.now()) {
  const deltaMs = Math.max(0, now - new Date(value).getTime());
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  return `${hours}h${remainderMinutes ? ` ${remainderMinutes}m` : ""}`;
}

function ageMs(value?: string | null) {
  if (!value) {
    return null;
  }
  return Math.max(0, Date.now() - new Date(value).getTime());
}

function formatAgeMs(value?: number | null) {
  if (value == null) {
    return UNKNOWN_LABEL;
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  if (value < 60_000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  const minutes = Math.round(value / 60_000);
  return `${minutes}m`;
}

function assetClassForInstrument(instrument: string) {
  const normalized = instrument.toUpperCase();
  if (normalized.startsWith("IX.D.")) {
    return "Indices";
  }
  if (normalized.startsWith("CC.D.") || ["XAUUSD", "XAGUSD", "WTI", "BRENT", "NG", "CL"].includes(normalized)) {
    return "Commodities";
  }
  if (normalized.startsWith("CR.D.") || normalized.endsWith("BTCUSD") || normalized.endsWith("ETHUSD") || normalized.endsWith("SOLUSD")) {
    return "Crypto";
  }
  if (normalized.startsWith("CS.D.") || /^[A-Z]{6}$/.test(normalized)) {
    return "FX";
  }
  return "Other";
}

function readableDirection(value?: "BUY" | "SELL" | null) {
  if (!value) {
    return "neutral";
  }
  return value === "BUY" ? "long" : "short";
}

function summarizeReason(value?: string | null) {
  if (!value) {
    return null;
  }
  return toTitleCase(value);
}

function executionTone(execution: Execution): LiveTone {
  if (execution.status === "FAILED" || execution.requires_manual_review) {
    return "negative";
  }
  if (execution.status === "RISK_REJECTED" || execution.status === "CANCELLED" || execution.status === "FILL_PARTIAL") {
    return "warning";
  }
  return "positive";
}

function executionMessage(execution: Execution) {
  const strategy = execution.strategy_name;
  const instrument = formatInstrumentLabel(execution.instrument);
  const direction = readableDirection(execution.details.direction as "BUY" | "SELL" | null | undefined) === "short" ? "short" : "long";

  switch (execution.status) {
    case "SIGNAL_GENERATED":
      return `${strategy} flagged ${instrument} for ${direction} entry`;
    case "RISK_APPROVED":
      return `${strategy} cleared risk gates on ${instrument}`;
    case "RISK_REJECTED":
      return `${strategy} signal was rejected on ${instrument}`;
    case "ORDER_SUBMITTED":
      return `${strategy} submitted ${instrument} to execution`;
    case "ORDER_ACKNOWLEDGED":
      return `Execution accepted ${strategy} on ${instrument}`;
    case "FILL_PARTIAL":
      return `${strategy} partially filled ${instrument}`;
    case "FILL_FULL":
    case "POSITION_OPENED":
      return `${strategy} entered ${direction} ${instrument}`;
    case "CLOSE_REQUESTED":
      return `${strategy} requested exit on ${instrument}`;
    case "CLOSE_CONFIRMED":
      return `${strategy} closed ${instrument}`;
    case "FAILED":
      return `${strategy} execution failed on ${instrument}`;
    case "CANCELLED":
      return `${strategy} execution was cancelled on ${instrument}`;
    case "NEEDS_MANUAL_REVIEW":
      return `${strategy} needs execution review on ${instrument}`;
    default:
      return `${strategy} updated ${instrument}`;
  }
}

function eventTone(event: DomainEvent): LiveTone {
  if (event.severity === "error") {
    return "negative";
  }
  if (event.severity === "warning") {
    return "warning";
  }
  return "neutral";
}

function eventMessage(event: DomainEvent) {
  const instrument = event.instrument ? formatInstrumentLabel(event.instrument) : null;
  const strategy = event.strategy_name;

  switch (event.event_type) {
    case "strategy.runtime_started":
      return `${strategy ?? "Strategy"} began watching ${instrument ?? "its market"}`;
    case "strategy.runtime_stopped":
      return `${strategy ?? "Strategy"} stopped watching ${instrument ?? "its market"}`;
    case "risk.entry_approved":
      return `Allocator approved ${strategy ?? "a strategy"} on ${instrument ?? "an instrument"}`;
    case "risk.entry_rejected":
      return `Allocator rejected ${strategy ?? "a strategy"} on ${instrument ?? "an instrument"}`;
    case "reconciliation.mismatch_detected":
      return `Execution truth drifted on ${instrument ?? "broker state"}`;
    case "health.stream_stale":
      return `Coverage went stale on ${instrument ?? "the live stream"}`;
    case "health.stream_recovered":
      return `Coverage recovered for ${instrument ?? "the live stream"}`;
    case "health.polling_fallback_started":
      return `Market data moved to polling fallback`;
    case "health.polling_fallback_stopped":
      return `Streaming path recovered`;
    case "health.broker_auth_failed":
      return `Broker authentication failed`;
    default:
      return event.title || toTitleCase(event.event_type);
  }
}

function alertTone(alert: AllocationAlert): LiveTone {
  if (alert.severity === "error") {
    return "negative";
  }
  if (alert.severity === "warning") {
    return "warning";
  }
  return "neutral";
}

function activityGroupKey(item: Pick<LiveActivityItem, "title" | "entityType" | "entityId" | "tone">) {
  return `${item.entityType}:${item.entityId}:${item.tone}:${item.title}`;
}

function aggregateActivity(items: LiveActivityItem[]) {
  const grouped: LiveActivityItem[] = [];

  for (const item of items) {
    const previous = grouped[grouped.length - 1];
    if (!previous) {
      grouped.push(item);
      continue;
    }

    const sameGroup = activityGroupKey(previous) === activityGroupKey(item);
    const closeInTime = Math.abs(new Date(previous.timestamp).getTime() - new Date(item.timestamp).getTime()) <= 180_000;

    if (sameGroup && closeInTime) {
      previous.groupCount += 1;
      continue;
    }

    grouped.push(item);
  }

  return grouped.slice(0, 24);
}

function biasFromPositions(positions: Position[]) {
  if (!positions.length) {
    return "neutral" as const;
  }

  const score = positions.reduce((sum, position) => sum + (position.direction === "BUY" ? 1 : -1), 0);
  if (score > 0 && score !== positions.length && score !== -positions.length) {
    return "mixed" as const;
  }
  if (score < 0 && score !== positions.length && score !== -positions.length) {
    return "mixed" as const;
  }
  if (score > 0) {
    return "long" as const;
  }
  if (score < 0) {
    return "short" as const;
  }
  return "mixed" as const;
}

function uniqueStrings(values: Array<string | null | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function buildInstrumentItems(resources: LiveDataResources, anomalyEntityIds: Set<string>) {
  const byInstrumentBucket = new Map(resources.exposure.by_instrument.map((bucket) => [bucket.name, bucket]));
  const readinessByInstrument = new Map(resources.coverage.streaming.execution_readiness.map((row) => [row.instrument, row]));
  const activeCoverageByInstrument = new Map(resources.coverage.streaming.active_instruments.map((row) => [row.instrument, row]));
  const positionsByInstrument = new Map<string, Position[]>();
  const strategyMap = new Map(resources.strategies.map((strategy) => [strategy.name, strategy]));
  const familyMap = new Map(resources.controlPlane.families.map((family) => [family.strategy_name, family]));

  for (const position of resources.positions) {
    const existing = positionsByInstrument.get(position.instrument) ?? [];
    existing.push(position);
    positionsByInstrument.set(position.instrument, existing);
  }

  const instrumentSet = new Set<string>();
  resources.positions.forEach((position) => instrumentSet.add(position.instrument));
  resources.exposure.by_instrument.forEach((bucket) => instrumentSet.add(bucket.name));
  resources.coverage.streaming.active_instruments.forEach((entry) => instrumentSet.add(entry.instrument));
  resources.coverage.streaming.execution_readiness.forEach((entry) => instrumentSet.add(entry.instrument));
  resources.strategies.forEach((strategy) => {
    instrumentSet.add(strategy.instrument);
    strategy.active_instruments?.forEach((instrument) => instrumentSet.add(instrument));
  });
  resources.controlPlane.families.forEach((family) => {
    if (family.runtime.active_instrument) {
      instrumentSet.add(family.runtime.active_instrument);
    }
    if (family.deployment?.selected_instrument) {
      instrumentSet.add(family.deployment.selected_instrument);
    }
  });

  const instrumentItems = [...instrumentSet].map((instrument) => {
    const bucket = byInstrumentBucket.get(instrument);
    const readiness = readinessByInstrument.get(instrument);
    const coverage = activeCoverageByInstrument.get(instrument);
    const positions = positionsByInstrument.get(instrument) ?? [];
    const activeStrategies = uniqueStrings(
      resources.strategies.flatMap((strategy) => {
        const touchesInstrument =
          strategy.instrument === instrument ||
          strategy.active_instruments?.includes(instrument) ||
          strategy.open_positions?.some((position) => position.instrument === instrument);
        if (!touchesInstrument) {
          return [];
        }
        return [strategy.name];
      }),
    );

    const runtimeStrategies = uniqueStrings(
      resources.controlPlane.families.flatMap((family) => {
        const selected =
          family.runtime.active_instrument === instrument ||
          family.deployment?.selected_instrument === instrument ||
          family.runtime.persisted_runtimes.some((runtime) => runtime.instrument === instrument);
        return selected ? [family.strategy_name] : [];
      }),
    );

    const allStrategies = uniqueStrings([...activeStrategies, ...runtimeStrategies]);
    const blockedReason =
      summarizeReason(readiness?.reason) ??
      (resources.coverage.streaming.capped_instruments.includes(instrument) ? "Coverage cap reached" : null);

    let state: LiveInstrumentItem["state"] = "idle";
    let tone: LiveTone = "inactive";

    if (resources.errors.coverage && !bucket && !positions.length) {
      state = "unknown";
      tone = "inactive";
    } else if (readiness && !readiness.is_ok) {
      state = "blocked";
      tone = readiness.market_open && readiness.tradable ? "warning" : "negative";
    } else if (
      (coverage && !coverage.streamed) ||
      (readiness && !readiness.quote_fresh) ||
      resources.coverage.streaming.capped_instruments.includes(instrument)
    ) {
      state = "degraded";
      tone = "warning";
    } else if ((bucket?.live_risk_percent ?? 0) > 0 || positions.length > 0 || allStrategies.length > 0) {
      state = "active";
      tone = anomalyEntityIds.has(`instrument:${instrument}`) ? "warning" : "positive";
    }

    const strategySummaries = allStrategies.map((strategyName) => {
      const strategy = strategyMap.get(strategyName);
      const family = familyMap.get(strategyName);
      return strategy?.warning_message ?? family?.deployment?.blocked_reason ?? family?.deployment?.degraded_reason ?? null;
    });

    const whyActiveParts = [];
    if ((bucket?.live_risk_percent ?? 0) > 0) {
      whyActiveParts.push(`${bucket?.live_risk_percent.toFixed(2)}% live risk`);
    }
    if (positions.length > 0) {
      whyActiveParts.push(`${positions.length} open position${positions.length === 1 ? "" : "s"}`);
    }
    if (allStrategies.length > 0) {
      whyActiveParts.push(`${allStrategies.length} strategy${allStrategies.length === 1 ? "" : "ies"} engaged`);
    }

    return {
      id: instrument,
      canonical: instrument,
      label: formatInstrumentLabel(instrument),
      assetClass: assetClassForInstrument(instrument),
      state,
      tone,
      bias: positions.length ? biasFromPositions(positions) : "neutral",
      significance: Math.max(bucket?.total_risk_percent ?? 0, positions.length * 0.35, allStrategies.length * 0.2),
      riskPercent: bucket?.live_risk_percent ?? null,
      activeStrategyCount: allStrategies.length,
      activeStrategies: allStrategies,
      activePositionCount: positions.length,
      healthSummary: strategySummaries.find(Boolean) ?? (readiness?.is_ok ? "Execution ready" : blockedReason ?? "Standing by"),
      constraint: blockedReason,
      whyActive: whyActiveParts.join(" · ") || "Observed but not currently engaged",
      isAnomalous: anomalyEntityIds.has(`instrument:${instrument}`),
      canonicalIds: [instrument, ...(coverage?.reason ? [coverage.reason] : [])],
    };
  });

  return instrumentItems.sort((left, right) => {
    if (left.state !== right.state) {
      const order = ["active", "degraded", "blocked", "idle", "unknown"];
      return order.indexOf(left.state) - order.indexOf(right.state);
    }
    return right.significance - left.significance || left.label.localeCompare(right.label);
  });
}

function familyMode(strategy: StrategyDefinition | undefined, family: ControlPlaneFamily | undefined) {
  if (!strategy && !family) {
    return "unknown" as const;
  }
  if (family?.governance.emergency_stop || family?.deployment?.state === "BLOCKED") {
    return "blocked" as const;
  }
  if (family?.deployment?.state === "DEGRADED" || strategy?.warning_message) {
    return "degraded" as const;
  }
  if (family && !family.governance.autonomous_operation_allowed) {
    return "constrained" as const;
  }
  if ((strategy?.open_position_count ?? 0) > 1 || (strategy?.active_runtime_count ?? 0) > 1) {
    return "scaling" as const;
  }
  if ((strategy?.open_position_count ?? 0) > 0) {
    return "holding" as const;
  }
  if (strategy?.status === "RUNNING" || family?.runtime.is_running) {
    return "waiting" as const;
  }
  if (strategy?.status === "STOPPED") {
    return "idle" as const;
  }
  return "unknown" as const;
}

function buildStrategyItems(resources: LiveDataResources, anomalyEntityIds: Set<string>) {
  const familyMap = new Map(resources.controlPlane.families.map((family) => [family.strategy_name, family]));
  const strategyNames = new Set<string>();
  resources.strategies.forEach((strategy) => strategyNames.add(strategy.name));
  resources.controlPlane.families.forEach((family) => strategyNames.add(family.strategy_name));

  return [...strategyNames]
    .map((name) => {
      const strategy = resources.strategies.find((item) => item.name === name);
      const family = familyMap.get(name);
      const mode = familyMode(strategy, family);
      const warnings = uniqueStrings([
        strategy?.warning_message,
        family?.deployment?.blocked_reason,
        family?.deployment?.degraded_reason,
        family?.alignment?.is_aligned === false ? family.alignment.reason : null,
      ]);

      const activeInstruments = uniqueStrings([
        strategy?.instrument,
        ...(strategy?.active_instruments ?? []),
        ...(strategy?.open_positions?.map((position) => position.instrument) ?? []),
        family?.runtime.active_instrument,
        family?.deployment?.selected_instrument,
      ]);

      const tone =
        mode === "blocked"
          ? "negative"
          : mode === "degraded" || mode === "constrained"
            ? "warning"
            : mode === "holding" || mode === "scaling" || mode === "waiting"
              ? "positive"
              : "inactive";

      const runtimeCount =
        strategy?.active_runtime_count ??
        (family?.runtime.persisted_runtimes.length ?? 0) ??
        0;
      const openPositionCount = strategy?.open_position_count ?? strategy?.open_positions?.length ?? 0;

      return {
        id: name,
        name,
        tone,
        mode,
        summary:
          mode === "scaling"
            ? `${runtimeCount || openPositionCount} live deployments extending exposure`
            : mode === "holding"
              ? `${openPositionCount} live position${openPositionCount === 1 ? "" : "s"} under management`
              : mode === "waiting"
                ? `${runtimeCount || 1} runtime${runtimeCount === 1 ? "" : "s"} observing for entries`
                : mode === "blocked"
                  ? warnings[0] ?? "Governance or runtime gates are blocking deployment"
                  : mode === "constrained"
                    ? "Autonomous deployment is disallowed for this family"
                    : mode === "degraded"
                      ? warnings[0] ?? "Health warnings are affecting normal behaviour"
                      : "No live runtime on watch",
        activeInstruments,
        runtimeCount,
        openPositionCount,
        warnings,
        isAnomalous: anomalyEntityIds.has(`strategy:${name}`),
      } satisfies LiveStrategyItem;
    })
    .sort((left, right) => {
      if (left.isAnomalous !== right.isAnomalous) {
        return Number(right.isAnomalous) - Number(left.isAnomalous);
      }
      if (left.mode !== right.mode) {
        const order = ["blocked", "degraded", "constrained", "scaling", "holding", "waiting", "idle", "unknown"];
        return order.indexOf(left.mode) - order.indexOf(right.mode);
      }
      return left.name.localeCompare(right.name);
    });
}

function buildAnomalies(resources: LiveDataResources) {
  const items: LiveAnomalyItem[] = [];

  for (const alert of resources.alerts.filter((item) => item.state !== "RESOLVED")) {
    const instrument = typeof alert.details.instrument === "string" ? alert.details.instrument : null;
    const strategy = typeof alert.details.strategy_name === "string" ? alert.details.strategy_name : null;
    items.push({
      id: `anomaly:alert:${alert.id}`,
      title: alert.title,
      explanation: alert.message,
      whyItMatters:
        alert.severity === "error"
          ? "The system is already outside its normal risk or execution envelope."
          : "If it persists, the system may act on weaker information or accumulate hidden risk.",
      affects: uniqueStrings([strategy, instrument ? formatInstrumentLabel(instrument) : null]),
      tone: alertTone(alert),
      severityRank: alert.severity === "error" ? 4 : alert.severity === "warning" ? 3 : 2,
      timestamp: alert.last_seen_at,
      source: "Allocator alert",
      entityType: instrument ? "instrument" : strategy ? "strategy" : "system",
      entityId: instrument ?? strategy ?? "system",
    });
  }

  if (!resources.errors.streamHealth) {
    const tickAge = ageMs(resources.streamHealth.last_tick_at);
    if (!resources.streamHealth.connected || (tickAge != null && tickAge > 60_000)) {
      items.push({
        id: "anomaly:stream:freshness",
        title: resources.streamHealth.connected ? "Market data freshness slipping" : "Live stream disconnected",
        explanation: resources.streamHealth.connected
          ? `Latest tick age is ${formatAgeMs(tickAge)}.`
          : resources.streamHealth.last_error ?? "Streaming path is not connected.",
        whyItMatters: "Perception quality falls first. The operator should know when observation truth is degrading before execution quality follows.",
        affects: resources.streamHealth.subscribed_instruments.slice(0, 4).map((instrument) => formatInstrumentLabel(instrument)),
        tone: resources.streamHealth.connected ? "warning" : "negative",
        severityRank: resources.streamHealth.connected ? 3 : 4,
        timestamp: resources.streamHealth.last_tick_at ?? resources.refreshedAt,
        source: "Stream health",
        entityType: "system",
        entityId: "system",
      });
    }
  }

  if (!resources.errors.telemetry) {
    if (resources.telemetry.reconciliation_mismatches > 0) {
      items.push({
        id: "anomaly:telemetry:reconciliation",
        title: "Execution integrity drift detected",
        explanation: `${resources.telemetry.reconciliation_mismatches} reconciliation mismatch${resources.telemetry.reconciliation_mismatches === 1 ? "" : "es"} remain open.`,
        whyItMatters: "Broker-confirmed truth and local execution state may not agree, which undermines trust in live posture.",
        affects: ["Execution state", "Risk visibility"],
        tone: "negative",
        severityRank: 4,
        timestamp: resources.telemetry.last_reconciliation ?? resources.refreshedAt,
        source: "Operational telemetry",
        entityType: "system",
        entityId: "system",
      });
    }

    if (resources.telemetry.order_failures_last_5m > 0 || resources.telemetry.rejected_orders_last_5m > 0) {
      items.push({
        id: "anomaly:telemetry:orders",
        title: "Execution quality degrading",
        explanation: `${resources.telemetry.order_failures_last_5m} failures and ${resources.telemetry.rejected_orders_last_5m} rejects in the last 5 minutes.`,
        whyItMatters: "Order-path instability can turn valid strategy behaviour into unintended exposure drift.",
        affects: ["Execution path"],
        tone: resources.telemetry.order_failures_last_5m > 0 ? "negative" : "warning",
        severityRank: resources.telemetry.order_failures_last_5m > 0 ? 4 : 3,
        timestamp: resources.telemetry.last_heartbeat,
        source: "Operational telemetry",
        entityType: "system",
        entityId: "system",
      });
    }
  }

  for (const readiness of resources.coverage.streaming.execution_readiness.filter((row) => !row.is_ok).slice(0, 4)) {
    items.push({
      id: `anomaly:readiness:${readiness.instrument}`,
      title: `${formatInstrumentLabel(readiness.instrument)} is blocked`,
      explanation: summarizeReason(readiness.reason) ?? "Execution readiness checks are not passing.",
      whyItMatters: "The system can still be watching an instrument whose execution path is no longer safe or complete.",
      affects: [formatInstrumentLabel(readiness.instrument)],
      tone: readiness.market_open && readiness.tradable ? "warning" : "negative",
      severityRank: readiness.market_open && readiness.tradable ? 3 : 4,
      timestamp: resources.refreshedAt,
      source: "Coverage readiness",
      entityType: "instrument",
      entityId: readiness.instrument,
    });
  }

  for (const hotspot of resources.exposure.hotspots.filter((item) => item.utilization_percent >= 80).slice(0, 4)) {
    items.push({
      id: `anomaly:hotspot:${hotspot.bucket_type}:${hotspot.name}`,
      title: `${formatInstrumentLabel(hotspot.name)} concentration building`,
      explanation: `${hotspot.utilization_percent.toFixed(0)}% of budget is already utilised in this bucket.`,
      whyItMatters: "Concentration reduces diversification and makes behaviour less resilient to one market regime.",
      affects: [formatInstrumentLabel(hotspot.name)],
      tone: hotspot.utilization_percent >= 95 ? "negative" : "warning",
      severityRank: hotspot.utilization_percent >= 95 ? 4 : 3,
      timestamp: resources.refreshedAt,
      source: "Allocation exposure",
      entityType: hotspot.bucket_type === "strategy" ? "strategy" : "instrument",
      entityId: hotspot.name,
    });
  }

  for (const strategy of resources.strategies.filter((item) => item.warning_message).slice(0, 4)) {
    items.push({
      id: `anomaly:strategy:${strategy.name}`,
      title: `${strategy.name} is behaving outside normal bounds`,
      explanation: strategy.warning_message ?? "Runtime warnings are active.",
      whyItMatters: "Repeated strategy degradation can distort portfolio behaviour even when the system is still technically running.",
      affects: uniqueStrings([strategy.name, ...(strategy.active_instruments ?? []).map((instrument) => formatInstrumentLabel(instrument))]),
      tone: "warning",
      severityRank: 3,
      timestamp: strategy.last_price_updated_at ?? resources.refreshedAt,
      source: "Strategy runtime",
      entityType: "strategy",
      entityId: strategy.name,
    });
  }

  if (!resources.errors.controlPlane && resources.controlPlane.misaligned_count > 0) {
    items.push({
      id: "anomaly:control-plane:misalignment",
      title: "Strategy control state is misaligned",
      explanation: `${resources.controlPlane.misaligned_count} family${resources.controlPlane.misaligned_count === 1 ? "" : "ies"} disagree with intended deployment state.`,
      whyItMatters: "Autonomy state can look nominal while individual families remain blocked, stale, or partially deployed.",
      affects: ["Strategy runtime governance"],
      tone: "warning",
      severityRank: 3,
      timestamp: resources.controlPlane.autonomy_updated_at ?? resources.refreshedAt,
      source: "Control plane",
      entityType: "system",
      entityId: "system",
    });
  }

  return items
    .sort((left, right) => {
      if (left.severityRank !== right.severityRank) {
        return right.severityRank - left.severityRank;
      }
      return new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
    })
    .slice(0, 12);
}

function buildActivity(resources: LiveDataResources) {
  const items: LiveActivityItem[] = [];
  const now = Date.now();

  for (const execution of resources.executions.slice(0, 24)) {
    items.push({
      id: `activity:execution:${execution.id}`,
      title: executionMessage(execution),
      detail:
        summarizeReason(execution.reason) ??
        summarizeReason(execution.error_message) ??
        `${execution.phase.toLowerCase()} flow · ${toTitleCase(execution.status)}`,
      tone: executionTone(execution),
      timestamp: execution.last_transition_at,
      relativeTime: formatRelativeTime(execution.last_transition_at, now),
      entityType: execution.instrument ? "instrument" : "system",
      entityId: execution.instrument ?? execution.strategy_name,
      groupCount: 1,
      source: "Execution feed",
      relatedStrategy: execution.strategy_name,
      relatedInstrument: execution.instrument,
    });
  }

  for (const decision of resources.coverage.trade_allocator.recent_decisions.slice(0, 16)) {
    items.push({
      id: `activity:allocator:${decision.id ?? decision.created_at}`,
      title: decision.selected
        ? `Allocator approved ${decision.strategy_name ?? "a strategy"} on ${formatInstrumentLabel(decision.instrument ?? "market")}`
        : `Allocator rejected ${decision.strategy_name ?? "a strategy"} on ${formatInstrumentLabel(decision.instrument ?? "market")}`,
      detail: summarizeReason(decision.reason) ?? summarizeReason(decision.reason_code) ?? "Allocator decision recorded",
      tone: decision.selected ? "positive" : "warning",
      timestamp: decision.created_at,
      relativeTime: formatRelativeTime(decision.created_at, now),
      entityType: decision.instrument ? "instrument" : decision.strategy_name ? "strategy" : "system",
      entityId: decision.instrument ?? decision.strategy_name ?? "system",
      groupCount: 1,
      source: "Trade allocator",
      relatedStrategy: decision.strategy_name ?? null,
      relatedInstrument: decision.instrument ?? null,
    });
  }

  for (const event of resources.events.filter((item) => item.category !== "execution").slice(0, 24)) {
    items.push({
      id: `activity:event:${event.id}`,
      title: eventMessage(event),
      detail: event.message ?? `${toTitleCase(event.category)} event · ${event.source}`,
      tone: eventTone(event),
      timestamp: event.created_at,
      relativeTime: formatRelativeTime(event.created_at, now),
      entityType: event.instrument ? "instrument" : event.strategy_name ? "strategy" : "system",
      entityId: event.instrument ?? event.strategy_name ?? "system",
      groupCount: 1,
      source: "Domain events",
      relatedStrategy: event.strategy_name ?? null,
      relatedInstrument: event.instrument ?? null,
    });
  }

  for (const alert of resources.alerts.filter((item) => item.state !== "RESOLVED").slice(0, 12)) {
    items.push({
      id: `activity:alert:${alert.id}`,
      title: alert.title,
      detail: alert.message,
      tone: alertTone(alert),
      timestamp: alert.last_seen_at,
      relativeTime: formatRelativeTime(alert.last_seen_at, now),
      entityType: "anomaly",
      entityId: `anomaly:alert:${alert.id}`,
      groupCount: 1,
      source: "Allocator alert",
    });
  }

  return aggregateActivity(
    items.sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()),
  );
}

function buildTrustRail(resources: LiveDataResources, anomalies: LiveAnomalyItem[]) {
  const tickAge = resources.errors.streamHealth ? null : ageMs(resources.streamHealth.last_tick_at);
  const liveFreshness =
    tickAge == null
      ? "UNKNOWN"
      : !resources.streamHealth.connected
        ? "STALE"
        : tickAge <= 15_000
          ? "LIVE"
          : tickAge <= 60_000
            ? "DELAYED"
            : "STALE";

  const freshnessTone: LiveTone =
    liveFreshness === "LIVE" ? "positive" : liveFreshness === "DELAYED" ? "warning" : liveFreshness === "STALE" ? "negative" : "inactive";

  let executionIntegrity = "UNKNOWN";
  let executionToneValue: LiveTone = "inactive";
  if (!resources.errors.telemetry && !resources.errors.executions) {
    const manualReviewCount = resources.executions.filter((item) => item.requires_manual_review).length;
    if (resources.telemetry.reconciliation_mismatches > 0 || manualReviewCount > 0 || resources.telemetry.order_failures_last_5m > 0) {
      executionIntegrity = resources.telemetry.reconciliation_mismatches > 0 || resources.telemetry.order_failures_last_5m > 0 ? "FAILING" : "DRIFT";
      executionToneValue = executionIntegrity === "FAILING" ? "negative" : "warning";
    } else {
      executionIntegrity = "OK";
      executionToneValue = "positive";
    }
  }

  let confidence = "UNKNOWN";
  let confidenceTone: LiveTone = "inactive";
  const missingSourceCount = Object.values(resources.errors).filter(Boolean).length;
  if (missingSourceCount <= 1 && liveFreshness === "LIVE" && executionIntegrity === "OK") {
    confidence = "HIGH";
    confidenceTone = "positive";
  } else if (missingSourceCount <= 3 && liveFreshness !== "STALE") {
    confidence = "MEDIUM";
    confidenceTone = "warning";
  } else if (missingSourceCount < Object.keys(resources.errors).length) {
    confidence = "LOW";
    confidenceTone = "warning";
  }

  let systemState = "UNAVAILABLE";
  let systemTone: LiveTone = "inactive";
  if (!resources.errors.controlPlane && !resources.errors.streamHealth && !resources.errors.telemetry) {
    if (!resources.controlPlane.effective_autonomous_control_enabled) {
      systemState = "PAUSED";
      systemTone = "warning";
    } else if (anomalies.some((item) => item.severityRank >= 4)) {
      systemState = "AT RISK";
      systemTone = "negative";
    } else if (anomalies.some((item) => item.severityRank === 3) || liveFreshness === "DELAYED") {
      systemState = "DEGRADED";
      systemTone = "warning";
    } else {
      systemState = "ACTIVE";
      systemTone = "positive";
    }
  }

  const brokerValue = resources.errors.brokerAuth
    ? "UNAVAILABLE"
    : resources.brokerAuth.state === "connected"
      ? "CONNECTED"
      : resources.brokerAuth.state === "disconnected"
        ? "DISCONNECTED"
        : "UNAVAILABLE";

  const streamValue = resources.errors.streamHealth
    ? "UNKNOWN"
    : !resources.streamHealth.enabled
      ? "DISABLED"
      : resources.streamHealth.connected
        ? resources.controlPlane.feed_source_state === "POLLING_FALLBACK"
          ? "POLLING"
          : "CONNECTED"
        : "INTERRUPTED";

  const actionRequired =
    systemState === "AT RISK" ||
    executionIntegrity === "FAILING" ||
    anomalies.some((item) => item.severityRank >= 4)
      ? "YES"
      : "NO";

  return [
    {
      id: "system-state",
      label: "System State",
      value: systemState,
      tone: systemTone,
      meta: systemState === "ACTIVE" ? "Autonomous system within expected envelope" : "Derived from control, freshness, and anomaly state",
      source: "Derived",
    },
    {
      id: "confidence",
      label: "Confidence",
      value: confidence,
      tone: confidenceTone,
      meta: missingSourceCount ? `${missingSourceCount} source${missingSourceCount === 1 ? "" : "s"} degraded or unavailable` : "Source coverage is intact",
      source: "Derived",
    },
    {
      id: "freshness",
      label: "Data Freshness",
      value: liveFreshness,
      tone: freshnessTone,
      meta: resources.errors.streamHealth ? resources.errors.streamHealth : `Last tick ${tickAge == null ? UNKNOWN_LABEL : `${formatAgeMs(tickAge)} ago`}`,
      source: "Backend stream health",
    },
    {
      id: "execution",
      label: "Execution Integrity",
      value: executionIntegrity,
      tone: executionToneValue,
      meta:
        resources.errors.telemetry ?? (executionIntegrity === "OK" ? "No active drift or failing order-path signals" : "Derived from reconciliation and execution-path telemetry"),
      source: "Backend telemetry",
    },
    {
      id: "broker",
      label: "Broker State",
      value: brokerValue,
      tone: brokerValue === "CONNECTED" ? "positive" : brokerValue === "DISCONNECTED" ? "warning" : "inactive",
      meta: resources.errors.brokerAuth ?? resources.brokerAuth.detail,
      source: "Telemetry-derived broker state",
    },
    {
      id: "stream",
      label: "Stream State",
      value: streamValue,
      tone: streamValue === "CONNECTED" ? "positive" : streamValue === "POLLING" || streamValue === "INTERRUPTED" ? "warning" : "inactive",
      meta: resources.errors.streamHealth ?? (resources.streamHealth.last_status || "Streaming status"),
      source: "Backend stream health",
    },
    {
      id: "updated",
      label: "Last Updated",
      value: formatShortTime(resources.refreshedAt),
      tone: "neutral",
      meta: `Screen refresh completed ${formatRelativeTime(resources.refreshedAt)} ago`,
      source: "Frontend",
    },
    {
      id: "action",
      label: "Action Required",
      value: actionRequired,
      tone: actionRequired === "YES" ? "negative" : "positive",
      meta: actionRequired === "YES" ? "A high-severity anomaly or failing execution signal is active" : "Observation only",
      source: "Derived",
    },
  ] satisfies LiveStatusChip[];
}

function buildInspectionModel(
  resources: LiveDataResources,
  activity: LiveActivityItem[],
  instruments: LiveInstrumentItem[],
  strategies: LiveStrategyItem[],
  anomalies: LiveAnomalyItem[],
) {
  const inspection: Record<string, LiveInspectionModel> = {};

  for (const instrument of instruments) {
    const recentActivity = activity.filter((item) => item.relatedInstrument === instrument.id || item.entityId === instrument.id).slice(0, 4);
    const relatedAnomalies = anomalies.filter((item) => item.entityType === "instrument" && item.entityId === instrument.id).slice(0, 3);
    inspection[`instrument:${instrument.id}`] = {
      title: instrument.label,
      subtitle: `${instrument.assetClass} · ${instrument.state}`,
      tone: instrument.tone,
      kicker: "Instrument inspection",
      status: toTitleCase(instrument.state),
      freshness:
        resources.coverage.streaming.execution_readiness.find((row) => row.instrument === instrument.id)?.last_price_age_ms != null
          ? formatAgeMs(resources.coverage.streaming.execution_readiness.find((row) => row.instrument === instrument.id)?.last_price_age_ms)
          : UNKNOWN_LABEL,
      source: resources.errors.coverage ? "Unavailable" : "Coverage + exposure + position state",
      sections: [
        { label: "Bias", value: toTitleCase(instrument.bias) },
        { label: "Live risk", value: instrument.riskPercent == null ? UNKNOWN_LABEL : `${instrument.riskPercent.toFixed(2)}%` },
        { label: "Strategies", value: instrument.activeStrategyCount ? instrument.activeStrategies.join(", ") : "None engaged" },
        { label: "Constraint", value: instrument.constraint ?? "No current hard block" },
      ],
      related: instrument.activeStrategies.map((strategy) => `Strategy · ${strategy}`),
      recentNotes: [...recentActivity.map((item) => item.title), ...relatedAnomalies.map((item) => item.title)].slice(0, 5),
      identifiers: instrument.canonicalIds,
      links: [
        { label: "Investigate markets", href: "/markets" },
        { label: "Related events", href: `/events?instrument=${encodeURIComponent(instrument.id)}` },
        { label: "Coverage diagnostics", href: "/coverage" },
      ],
    };
  }

  for (const strategy of strategies) {
    const family = resources.controlPlane.families.find((item) => item.strategy_name === strategy.id);
    const runtime = resources.strategies.find((item) => item.name === strategy.id);
    const relatedAnomalies = anomalies.filter((item) => item.entityType === "strategy" && item.entityId === strategy.id).slice(0, 3);
    inspection[`strategy:${strategy.id}`] = {
      title: strategy.name,
      subtitle: `${toTitleCase(strategy.mode)} mode`,
      tone: strategy.tone,
      kicker: "Strategy inspection",
      status: toTitleCase(strategy.mode),
      freshness: runtime?.last_price_updated_at ? formatRelativeTime(runtime.last_price_updated_at) : UNKNOWN_LABEL,
      source: resources.errors.strategies ? "Unavailable" : "Strategy runtime + control plane",
      sections: [
        { label: "Current posture", value: strategy.summary },
        { label: "Active instruments", value: strategy.activeInstruments.length ? strategy.activeInstruments.map((instrument) => formatInstrumentLabel(instrument)).join(", ") : "None" },
        { label: "Runtime count", value: String(strategy.runtimeCount) },
        { label: "Open positions", value: String(strategy.openPositionCount) },
      ],
      related: uniqueStrings([
        family?.deployment?.selected_profile ? `Profile · ${family.deployment.selected_profile}` : null,
        family?.runtime.active_instrument ? `Instrument · ${formatInstrumentLabel(family.runtime.active_instrument)}` : null,
        ...strategy.warnings.map((warning) => `Constraint · ${warning}`),
      ]),
      recentNotes: [
        ...relatedAnomalies.map((item) => item.title),
        ...(family?.recent_events.slice(0, 3).map((event) => event.title) ?? []),
      ].slice(0, 5),
      identifiers: uniqueStrings([strategy.id, family?.runtime.active_runtime_id ?? null]),
      links: [
        { label: "Strategy diagnostics", href: "/strategies" },
        { label: "Control-plane state", href: "/control-plane" },
        { label: "Related events", href: `/events?strategy_name=${encodeURIComponent(strategy.id)}` },
      ],
    };
  }

  for (const anomaly of anomalies) {
    inspection[anomaly.id] = {
      title: anomaly.title,
      subtitle: anomaly.explanation,
      tone: anomaly.tone,
      kicker: "Unusual activity",
      status: anomaly.tone === "negative" ? "Critical" : anomaly.tone === "warning" ? "Watch closely" : "Informational",
      freshness: formatRelativeTime(anomaly.timestamp),
      source: anomaly.source,
      sections: [
        { label: "Why it matters", value: anomaly.whyItMatters },
        { label: "Affects", value: anomaly.affects.length ? anomaly.affects.join(", ") : "System-wide" },
      ],
      related: uniqueStrings([
        anomaly.entityType === "instrument" ? `Instrument · ${formatInstrumentLabel(anomaly.entityId)}` : null,
        anomaly.entityType === "strategy" ? `Strategy · ${anomaly.entityId}` : null,
      ]),
      recentNotes: activity
        .filter((item) => item.entityId === anomaly.entityId || item.relatedInstrument === anomaly.entityId || item.relatedStrategy === anomaly.entityId)
        .slice(0, 4)
        .map((item) => item.title),
      identifiers: [anomaly.id, anomaly.entityId],
      links:
        anomaly.entityType === "instrument"
          ? [
              { label: "Related events", href: `/events?instrument=${encodeURIComponent(anomaly.entityId)}` },
              { label: "Coverage diagnostics", href: "/coverage" },
            ]
          : anomaly.entityType === "strategy"
            ? [
                { label: "Related events", href: `/events?strategy_name=${encodeURIComponent(anomaly.entityId)}` },
                { label: "Strategy diagnostics", href: "/strategies" },
              ]
            : [
                { label: "Event diagnostics", href: "/events?severity=error" },
                { label: "Control plane", href: "/control-plane" },
              ],
    };
  }

  for (const item of activity) {
    inspection[`activity:${item.id}`] = {
      title: item.title,
      subtitle: item.detail,
      tone: item.tone,
      kicker: "Activity detail",
      status: item.tone === "negative" ? "Anomalous" : item.tone === "warning" ? "Watch" : "Normal",
      freshness: formatShortTime(item.timestamp),
      source: item.source,
      sections: [
        { label: "Observed", value: item.relativeTime ? `${item.relativeTime} ago` : formatShortTime(item.timestamp) },
        { label: "Entity", value: item.relatedInstrument ? formatInstrumentLabel(item.relatedInstrument) : item.relatedStrategy ?? item.entityId },
      ],
      related: uniqueStrings([
        item.relatedStrategy ? `Strategy · ${item.relatedStrategy}` : null,
        item.relatedInstrument ? `Instrument · ${formatInstrumentLabel(item.relatedInstrument)}` : null,
      ]),
      recentNotes: [],
      identifiers: uniqueStrings([item.id, item.relatedInstrument ?? null, item.relatedStrategy ?? null]),
      links: item.relatedInstrument
        ? [{ label: "Related events", href: `/events?instrument=${encodeURIComponent(item.relatedInstrument)}` }]
        : item.relatedStrategy
          ? [{ label: "Related events", href: `/events?strategy_name=${encodeURIComponent(item.relatedStrategy)}` }]
          : [{ label: "Event diagnostics", href: "/events" }],
    };
  }

  inspection.system = {
    title: "Live system state",
    subtitle: "Unified observation across control, coverage, execution, and exposure",
    tone: "neutral",
    kicker: "System inspection",
    status: "Observation-first",
    freshness: formatShortTime(resources.refreshedAt),
    source: "Derived from multiple backend endpoints",
    sections: [
      { label: "Active instruments", value: String(instruments.filter((item) => item.state === "active").length) },
      { label: "Strategies engaged", value: String(strategies.filter((item) => item.mode !== "idle").length) },
      { label: "Unusual signals", value: String(anomalies.length) },
    ],
    related: resources.errors.positions || resources.errors.coverage || resources.errors.telemetry ? ["Some source feeds are degraded"] : ["Source coverage intact"],
    recentNotes: activity.slice(0, 4).map((item) => item.title),
    identifiers: ["system"],
    links: [
      { label: "Overview", href: "/" },
      { label: "Risk diagnostics", href: "/risk" },
      { label: "Event diagnostics", href: "/events" },
    ],
  };

  return inspection;
}

export function buildLiveSystemViewModel(resources: LiveDataResources): LiveSystemViewModel {
  const anomalies = buildAnomalies(resources);
  const anomalyEntityIds = new Set(
    anomalies
      .filter((item) => item.entityType !== "system")
      .map((item) => `${item.entityType}:${item.entityId}`),
  );
  const activity = buildActivity(resources);
  const instruments = buildInstrumentItems(resources, anomalyEntityIds);
  const strategies = buildStrategyItems(resources, anomalyEntityIds);
  const trustRail = buildTrustRail(resources, anomalies);
  const inspection = buildInspectionModel(resources, activity, instruments, strategies, anomalies);
  const assetClasses = [...new Set(instruments.map((instrument) => instrument.assetClass))];
  const dataWarnings = Object.entries(resources.errors)
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => `${toTitleCase(key)} unavailable: ${value}`);

  const defaultSelection: LiveSelection =
    anomalies[0]
      ? { type: "anomaly", id: anomalies[0].id }
      : instruments[0]
        ? { type: "instrument", id: instruments[0].id }
        : strategies[0]
          ? { type: "strategy", id: strategies[0].id }
          : activity[0]
            ? { type: "activity", id: activity[0].id }
            : null;

  return {
    trustRail,
    activity,
    instruments,
    strategies,
    anomalies,
    assetClasses,
    inspection,
    defaultSelection,
    dataWarnings,
  };
}
