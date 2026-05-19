"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CompactTable,
  DataIndicator,
  ExceptionList,
  InspectorDrawer,
  Panel,
  StatusPill,
  StatusStrip,
} from "@/components/console/primitives";
import { RiskAllocationPanel } from "@/components/dashboard/risk-allocation-panel";
import { RiskPanel } from "@/components/dashboard/risk-panel";
import { RiskInspectorDrawer } from "@/components/risk/risk-inspector-drawer";
import { RiskStatusBlock } from "@/components/risk/risk-status-block";
import {
  getAllocationAlerts,
  getAllocationCycles,
  getAllocationDriftSummary,
  getAllocationExposureSummary,
  getAllocationIntents,
  getBrokerAuthStatus,
  getControlPlaneSummary,
  getCoverageSummary,
  getDashboardSnapshot,
  getExecutions,
  getOpenPositions,
  getStreamHealth,
  getSystemOperatingLimits,
  getTrades,
} from "@/lib/api";
import {
  formatCurrency,
  formatInstrumentLabel,
  formatPercent,
  formatRelativeDuration,
  formatSignedCurrency,
  formatSignedPercent,
} from "@/lib/format";
import {
  AllocationAlert,
  AllocationCycle,
  AllocationDriftSummary,
  AllocationExposureSummary,
  AllocationIntent,
  BrokerAuthStatus,
  ControlPlaneSummary,
  CoverageSummary,
  DashboardSnapshot,
  Execution,
  Position,
  StreamHealthStatus,
  SystemOperatingLimits,
  Trade,
} from "@/lib/types";
import { buildRiskConsoleSummary } from "@/lib/risk-allocation";

type DashboardLiveProps = {
  initialPositions: Position[];
  initialTrades: Trade[];
  initialExecutions: Execution[];
  initialBrokerAuth: BrokerAuthStatus;
  initialDashboard: DashboardSnapshot;
  initialStreamHealth: StreamHealthStatus;
  initialCoverage: CoverageSummary;
  initialControlPlane: ControlPlaneSummary;
  initialOperatingLimits: SystemOperatingLimits;
  initialAllocationExposure: AllocationExposureSummary;
  initialAllocationAlerts: AllocationAlert[];
  initialAllocationDrift: AllocationDriftSummary;
  initialAllocationCycles: AllocationCycle[];
  initialAllocationIntents: AllocationIntent[];
  initialErrors: {
    positions: string | null;
    trades: string | null;
    executions: string | null;
    brokerAuth: string | null;
    dashboard: string | null;
    streamHealth: string | null;
    coverage: string | null;
    controlPlane: string | null;
    operatingLimits: string | null;
    allocationExposure: string | null;
    allocationAlerts: string | null;
    allocationDrift: string | null;
    allocationCycles: string | null;
    allocationIntents: string | null;
  };
};

type InspectorMode = "positions" | "trades" | "activity" | "risk" | null;

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "n/a";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function closeSourceLabel(source?: string | null) {
  if (source === "SIMULATED_LOCAL_CLOSE") {
    return "Simulated local close";
  }
  if (source === "BROKER_CONFIRMED") {
    return "Broker confirmed";
  }
  return "Close source unknown";
}

function renderMetricOrUnavailable(
  value: string,
  unavailable: boolean,
  message: string,
) {
  if (!unavailable) {
    return value;
  }
  return (
    <>
      -<DataIndicator state="unavailable" message={message} />
    </>
  );
}

function dashboardStreamStatus(controlPlane: ControlPlaneSummary, streamHealth: StreamHealthStatus) {
  if (controlPlane.feed_source_state === "STALE") {
    return {
      value: "Stale",
      tone: "warning" as const,
      meta: "Feed stale. Price freshness is below the current execution threshold.",
    };
  }
  if (controlPlane.feed_source_state === "POLLING_FALLBACK") {
    return {
      value: "Polling",
      tone: "warning" as const,
      meta: "Polling fallback is active; live streaming is not the entry source.",
    };
  }
  if (controlPlane.feed_source_state === "DISCONNECTED") {
    return {
      value: "Disconnected",
      tone: "negative" as const,
      meta: "Feed disconnected. Live streaming and fallback freshness are unavailable.",
    };
  }
  if (streamHealth.connected) {
    return {
      value: "Live",
      tone: "positive" as const,
      meta: streamHealth.last_status ?? "Streaming market data is connected.",
    };
  }
  if (streamHealth.enabled) {
    return {
      value: "Interrupted",
      tone: "negative" as const,
      meta: streamHealth.last_status ?? "Streaming market data is interrupted.",
    };
  }
  return {
    value: "Unavailable",
    tone: "inactive" as const,
    meta: streamHealth.last_status ?? "Stream health is unavailable.",
  };
}

export function DashboardLive({
  initialPositions,
  initialTrades,
  initialExecutions,
  initialBrokerAuth,
  initialDashboard,
  initialStreamHealth,
  initialCoverage,
  initialControlPlane,
  initialOperatingLimits,
  initialAllocationExposure,
  initialAllocationAlerts,
  initialAllocationDrift,
  initialAllocationCycles,
  initialAllocationIntents,
  initialErrors,
}: DashboardLiveProps) {
  const [positions, setPositions] = useState(initialPositions);
  const [trades, setTrades] = useState(initialTrades);
  const [executions, setExecutions] = useState(initialExecutions);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);
  const [coverage, setCoverage] = useState(initialCoverage);
  const [controlPlane, setControlPlane] = useState(initialControlPlane);
  const [operatingLimits, setOperatingLimits] = useState(initialOperatingLimits);
  const [allocationExposure, setAllocationExposure] = useState(initialAllocationExposure);
  const [allocationAlerts, setAllocationAlerts] = useState(initialAllocationAlerts);
  const [allocationDrift, setAllocationDrift] = useState(initialAllocationDrift);
  const [allocationCycles, setAllocationCycles] = useState(initialAllocationCycles);
  const [allocationIntents, setAllocationIntents] = useState(initialAllocationIntents);
  const [errors, setErrors] = useState(initialErrors);
  const [inspectorMode, setInspectorMode] = useState<InspectorMode>(null);

  useEffect(() => {
    setPositions(initialPositions);
    setTrades(initialTrades);
    setExecutions(initialExecutions);
    setBrokerAuth(initialBrokerAuth);
    setDashboard(initialDashboard);
    setStreamHealth(initialStreamHealth);
    setCoverage(initialCoverage);
    setControlPlane(initialControlPlane);
    setOperatingLimits(initialOperatingLimits);
    setAllocationExposure(initialAllocationExposure);
    setAllocationAlerts(initialAllocationAlerts);
    setAllocationDrift(initialAllocationDrift);
    setAllocationCycles(initialAllocationCycles);
    setAllocationIntents(initialAllocationIntents);
    setErrors(initialErrors);
  }, [
    initialPositions,
    initialTrades,
    initialExecutions,
    initialBrokerAuth,
    initialDashboard,
    initialStreamHealth,
    initialCoverage,
    initialControlPlane,
    initialOperatingLimits,
    initialAllocationExposure,
    initialAllocationAlerts,
    initialAllocationDrift,
    initialAllocationCycles,
    initialAllocationIntents,
    initialErrors,
  ]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      const [
        nextPositions,
        nextTrades,
        nextExecutions,
        nextBrokerAuth,
        nextDashboard,
        nextStreamHealth,
        nextCoverage,
        nextControlPlane,
        nextOperatingLimits,
        nextAllocationExposure,
        nextAllocationAlerts,
        nextAllocationDrift,
        nextAllocationCycles,
        nextAllocationIntents,
      ] = await Promise.allSettled([
          getOpenPositions(),
          getTrades(),
          getExecutions(),
          getBrokerAuthStatus(),
          getDashboardSnapshot(),
          getStreamHealth(),
          getCoverageSummary(),
          getControlPlaneSummary(),
          getSystemOperatingLimits(),
          getAllocationExposureSummary(),
          getAllocationAlerts({ limit: 40 }),
          getAllocationDriftSummary({ limit: 20, windowMinutes: 720 }),
          getAllocationCycles(12),
          getAllocationIntents({ limit: 40 }),
        ]);
      if (cancelled) {
        return;
      }
      if (nextPositions.status === "fulfilled") {
        setPositions(nextPositions.value);
      }
      if (nextTrades.status === "fulfilled") {
        setTrades(nextTrades.value);
      }
      if (nextExecutions.status === "fulfilled") {
        setExecutions(nextExecutions.value);
      }
      if (nextBrokerAuth.status === "fulfilled") {
        setBrokerAuth(nextBrokerAuth.value);
      }
      if (nextDashboard.status === "fulfilled") {
        setDashboard(nextDashboard.value);
      }
      if (nextStreamHealth.status === "fulfilled") {
        setStreamHealth(nextStreamHealth.value);
      }
      if (nextCoverage.status === "fulfilled") {
        setCoverage(nextCoverage.value);
      }
      if (nextControlPlane.status === "fulfilled") {
        setControlPlane(nextControlPlane.value);
      }
      if (nextOperatingLimits.status === "fulfilled") {
        setOperatingLimits(nextOperatingLimits.value);
      }
      if (nextAllocationExposure.status === "fulfilled") {
        setAllocationExposure(nextAllocationExposure.value);
      }
      if (nextAllocationAlerts.status === "fulfilled") {
        setAllocationAlerts(nextAllocationAlerts.value);
      }
      if (nextAllocationDrift.status === "fulfilled") {
        setAllocationDrift(nextAllocationDrift.value);
      }
      if (nextAllocationCycles.status === "fulfilled") {
        setAllocationCycles(nextAllocationCycles.value);
      }
      if (nextAllocationIntents.status === "fulfilled") {
        setAllocationIntents(nextAllocationIntents.value);
      }
      setErrors({
        positions: nextPositions.status === "rejected" ? (nextPositions.reason instanceof Error ? nextPositions.reason.message : "Failed to load positions.") : null,
        trades: nextTrades.status === "rejected" ? (nextTrades.reason instanceof Error ? nextTrades.reason.message : "Failed to load trades.") : null,
        executions: nextExecutions.status === "rejected" ? (nextExecutions.reason instanceof Error ? nextExecutions.reason.message : "Failed to load executions.") : null,
        brokerAuth: nextBrokerAuth.status === "rejected" ? (nextBrokerAuth.reason instanceof Error ? nextBrokerAuth.reason.message : "Failed to load broker status.") : null,
        dashboard: nextDashboard.status === "rejected" ? (nextDashboard.reason instanceof Error ? nextDashboard.reason.message : "Failed to load dashboard KPIs.") : null,
        streamHealth: nextStreamHealth.status === "rejected" ? (nextStreamHealth.reason instanceof Error ? nextStreamHealth.reason.message : "Failed to load stream health.") : null,
        coverage: nextCoverage.status === "rejected" ? (nextCoverage.reason instanceof Error ? nextCoverage.reason.message : "Failed to load coverage.") : null,
        controlPlane: nextControlPlane.status === "rejected" ? (nextControlPlane.reason instanceof Error ? nextControlPlane.reason.message : "Failed to load control plane.") : null,
        operatingLimits: nextOperatingLimits.status === "rejected" ? (nextOperatingLimits.reason instanceof Error ? nextOperatingLimits.reason.message : "Failed to load operating limits.") : null,
        allocationExposure: nextAllocationExposure.status === "rejected" ? (nextAllocationExposure.reason instanceof Error ? nextAllocationExposure.reason.message : "Failed to load allocation exposure.") : null,
        allocationAlerts: nextAllocationAlerts.status === "rejected" ? (nextAllocationAlerts.reason instanceof Error ? nextAllocationAlerts.reason.message : "Failed to load allocation alerts.") : null,
        allocationDrift: nextAllocationDrift.status === "rejected" ? (nextAllocationDrift.reason instanceof Error ? nextAllocationDrift.reason.message : "Failed to load drift summary.") : null,
        allocationCycles: nextAllocationCycles.status === "rejected" ? (nextAllocationCycles.reason instanceof Error ? nextAllocationCycles.reason.message : "Failed to load allocation cycles.") : null,
        allocationIntents: nextAllocationIntents.status === "rejected" ? (nextAllocationIntents.reason instanceof Error ? nextAllocationIntents.reason.message : "Failed to load allocation intents.") : null,
      });
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const sortedTrades = useMemo(
    () =>
      trades
        .slice()
        .sort((left, right) => new Date(right.close_time).getTime() - new Date(left.close_time).getTime()),
    [trades],
  );

  const recentExecutions = useMemo(
    () =>
      executions
        .slice()
        .sort((left, right) => new Date(right.last_transition_at).getTime() - new Date(left.last_transition_at).getTime()),
    [executions],
  );

  const exposureRows = positions.map((position) => ({
    ...position,
    notional: position.open_price * position.size,
  }));

  const manualReviewExecutions = recentExecutions.filter(
    (execution) =>
      execution.requires_manual_review ||
      execution.status === "FAILED" ||
      execution.status === "NEEDS_MANUAL_REVIEW" ||
      execution.status === "RISK_REJECTED",
  );

  const staleCoverage = coverage.streaming.execution_readiness.filter(
    (item) => !item.is_ok || item.last_price_age_ms > operatingLimits.execution.max_price_age_ms,
  );

  const strategyExceptions = controlPlane.families.filter((family) => {
    const deploymentState = family.deployment?.state;
    return (
      family.alignment.status !== "ALIGNED" ||
      family.governance.emergency_stop ||
      deploymentState === "BLOCKED" ||
      deploymentState === "DEGRADED" ||
      deploymentState === "EMERGENCY_STOPPED"
    );
  });

  const exceptionItems = [
    ...manualReviewExecutions.slice(0, 3).map((execution) => ({
      id: `execution-${execution.id}`,
      title: `${execution.strategy_name} ${execution.status.toLowerCase().replaceAll("_", " ")}`,
      detail: execution.error_message || execution.reason || "Execution path requires review.",
      tone:
        execution.status === "FAILED" || execution.status === "NEEDS_MANUAL_REVIEW"
          ? ("negative" as const)
          : ("warning" as const),
      meta: `${formatInstrumentLabel(execution.instrument)} · ${formatRelativeDuration(execution.last_transition_at)} ago`,
    })),
    ...strategyExceptions.slice(0, 3).map((family) => ({
      id: `family-${family.strategy_name}`,
      title: `${family.strategy_name} ${family.alignment.status.toLowerCase()}`,
      detail:
        family.deployment?.blocked_reason ||
        family.deployment?.degraded_reason ||
        family.alignment.reason ||
        "Strategy family requires intervention.",
      tone:
        family.deployment?.state === "BLOCKED" || family.deployment?.state === "EMERGENCY_STOPPED"
          ? ("negative" as const)
          : ("warning" as const),
      meta: family.deployment?.state ?? "Unassigned",
    })),
    ...staleCoverage.slice(0, 2).map((item) => ({
      id: `coverage-${item.instrument}`,
      title: `${formatInstrumentLabel(item.instrument)} blocked`,
      detail: item.reason || "Readiness gates are preventing action.",
      tone: "warning" as const,
      meta: `${item.last_price_age_ms.toFixed(0)}ms age`,
    })),
  ].slice(0, 6);

  const runtimeRows = dashboard.runningStrategies ?? [];
  const runningCount = runtimeRows.length;
  const degradedCount = strategyExceptions.length;
  const pausedCount = Math.max(controlPlane.families.length - runningCount - degradedCount, 0);
  const openRiskState = controlPlane.open_risk_management_state;
  const openRiskUnavailable = openRiskState == null || openRiskState === "UNAVAILABLE" || openRiskState === "UNKNOWN";
  const streamStatus = dashboardStreamStatus(controlPlane, streamHealth);
  const healthTone =
    errors.controlPlane || errors.brokerAuth
      ? "inactive"
      : !controlPlane.effective_autonomous_control_enabled || brokerAuth.state === "unavailable"
      ? "negative"
      : manualReviewExecutions.length || staleCoverage.length || strategyExceptions.length
        ? "warning"
        : "positive";

  const riskSummary = useMemo(
    () =>
      buildRiskConsoleSummary({
        exposure: allocationExposure,
        alerts: allocationAlerts,
        drift: allocationDrift,
        cycles: allocationCycles,
        intents: allocationIntents,
      }),
    [allocationExposure, allocationAlerts, allocationDrift, allocationCycles, allocationIntents],
  );

  const drawerTitle =
    inspectorMode === "positions"
      ? "Positions"
      : inspectorMode === "trades"
        ? "Trades"
        : inspectorMode === "activity"
          ? "Recent Activity"
          : inspectorMode === "risk"
            ? "Risk / Allocation Briefing"
          : "";

  return (
    <>
      <main className="console-page console-page--board">
        <section className="dashboard-status-strip">
          <StatusStrip
            items={[
              {
                label: "Autonomy",
                value: errors.controlPlane ? (
                  <>
                    -<DataIndicator state="error" message={errors.controlPlane} />
                  </>
                ) : controlPlane.effective_autonomous_control_enabled && controlPlane.entry_eligible === false ? (
                  "Authorized"
                ) : controlPlane.effective_autonomous_control_enabled ? (
                  "Running"
                ) : (
                  "Stopped"
                ),
                tone: errors.controlPlane ? "inactive" : healthTone,
                meta:
                  errors.controlPlane ??
                  (controlPlane.effective_autonomous_control_enabled && controlPlane.entry_eligible === false
                    ? "permission on; new entries blocked"
                    : `${runningCount} runtimes active`),
                emphasis: "strong",
              },
              {
                label: "Alerts",
                value: errors.executions || errors.controlPlane ? "-" : manualReviewExecutions.length + strategyExceptions.length,
                tone: errors.executions || errors.controlPlane ? "inactive" : manualReviewExecutions.length ? "negative" : strategyExceptions.length ? "warning" : "positive",
                meta: errors.executions ?? errors.controlPlane ?? (manualReviewExecutions.length ? "intervention likely" : "none urgent"),
                emphasis: "strong",
              },
              {
                label: "Broker",
                value: errors.brokerAuth ? (
                  <>
                    -<DataIndicator state="error" message={errors.brokerAuth} />
                  </>
                ) : brokerAuth.state === "connected" ? (
                  "Connected"
                ) : (
                  brokerAuth.label
                ),
                tone: errors.brokerAuth
                  ? "inactive"
                  : brokerAuth.state === "connected"
                    ? "positive"
                    : brokerAuth.state === "disconnected"
                      ? "warning"
                      : "inactive",
                meta: errors.brokerAuth ?? brokerAuth.detail,
              },
              {
                label: "Stream",
                value: errors.streamHealth ? (
                  <>
                    -<DataIndicator state="error" message={errors.streamHealth} />
                  </>
                ) : (
                  streamStatus.value
                ),
                tone: errors.streamHealth ? "inactive" : streamStatus.tone,
                meta: errors.streamHealth ?? streamStatus.meta,
              },
              {
                label: "Coverage",
                value: errors.coverage ? "-" : `${coverage.streaming.active_instruments.length}/${coverage.streaming.desired_instruments.length}`,
                tone: errors.coverage ? "inactive" : staleCoverage.length ? "warning" : "neutral",
                meta: errors.coverage ?? (staleCoverage.length ? `${staleCoverage.length} blocked` : "ready"),
              },
              {
                label: "Open Risk",
                value: errors.dashboard || errors.operatingLimits ? "-" : openRiskState ?? formatPercent(dashboard.openRisk),
                tone:
                  errors.dashboard || errors.operatingLimits
                    ? "inactive"
                    : openRiskUnavailable
                      ? "inactive"
                    : openRiskState === "UNMANAGED_OPEN_RISK"
                      ? "negative"
                      : openRiskState === "EXITS_ONLY"
                        ? "warning"
                        : dashboard.openRisk > operatingLimits.risk.max_open_risk_percent
                          ? "negative"
                          : "neutral",
                meta:
                  errors.dashboard ??
                  errors.operatingLimits ??
                  controlPlane.open_risk_management_reason ??
                  `limit ${formatPercent(operatingLimits.risk.max_open_risk_percent)}`,
              },
            ]}
          />
        </section>

        <section className="dashboard-main-layout">
          <div className="dashboard-main-layout__sidebar">
            <ExceptionList
              title="Exceptions"
              subtitle="Anything here deserves attention before normal monitoring."
              items={exceptionItems}
              emptyLabel={
                errors.executions || errors.controlPlane || errors.coverage
                  ? "Exceptions are unavailable while one or more monitoring feeds are offline."
                  : "No active exceptions. System behavior is nominal."
              }
              priority="critical"
            />

            <Panel title="Inspect" priority="passive" tone="inactive" compact>
              <div className="console-inline-actions">
                <button type="button" className="console-button console-button--ghost" onClick={() => setInspectorMode("positions")}>
                  Positions
                </button>
                <button type="button" className="console-button console-button--ghost" onClick={() => setInspectorMode("trades")}>
                  Trades
                </button>
                <button type="button" className="console-button console-button--ghost" onClick={() => setInspectorMode("activity")}>
                  Activity
                </button>
              </div>
            </Panel>
          </div>

          <div className="dashboard-main-layout__content">
            <Panel title="Operational Overview" priority="primary" tone={healthTone}>
              <div className="dashboard-overview-grid">
                <section className="dashboard-overview-section">
                  <div className="dashboard-overview-section__header">
                    <span className="console-kicker">System Health</span>
                    <div className="console-inline-actions">
                      <StatusPill
                        label="Autonomy"
                        tone={errors.controlPlane ? "inactive" : controlPlane.effective_autonomous_control_enabled ? "positive" : "negative"}
                        title={
                          errors.controlPlane
                            ? `Autonomy unknown. ${errors.controlPlane}`
                            : controlPlane.effective_autonomous_control_enabled && controlPlane.entry_eligible === false
                              ? "Autonomy authorized. This is permission only; new entries are currently blocked by operational policy."
                              : controlPlane.effective_autonomous_control_enabled
                              ? "Autonomy authorized. Governed autonomous control is enabled, but execution still depends on feed, broker, and risk state."
                              : "Autonomy stopped. Governed autonomous control is paused."
                        }
                      />
                      <StatusPill
                        label="Feed"
                        tone={
                          errors.streamHealth
                            ? "inactive"
                            : controlPlane.feed_source_state === "LIVE"
                              ? "positive"
                              : controlPlane.feed_source_state === "POLLING_FALLBACK" || controlPlane.feed_source_state === "STALE"
                                ? "warning"
                                : streamHealth.connected
                                  ? "positive"
                                  : "negative"
                        }
                        title={
                          errors.streamHealth
                            ? `Feed unknown. ${errors.streamHealth}`
                            : controlPlane.feed_source_state === "POLLING_FALLBACK"
                              ? "Feed degraded. Polling fallback is active and new entries are blocked."
                              : controlPlane.feed_source_state === "STALE"
                                ? "Feed stale. Price freshness is below the current execution threshold."
                                : controlPlane.feed_source_state === "DISCONNECTED"
                                  ? "Feed disconnected. Live streaming and fallback freshness are unavailable."
                                  : streamHealth.connected
                              ? "Feed live. Streaming market data is connected."
                              : `Feed degraded. ${streamHealth.last_status ?? "Streaming market data is interrupted."}`
                        }
                      />
                      <StatusPill
                        label="Broker"
                        tone={errors.brokerAuth ? "inactive" : brokerAuth.state === "connected" ? "positive" : "inactive"}
                        title={
                          errors.brokerAuth
                            ? `Broker unknown. ${errors.brokerAuth}`
                            : brokerAuth.state === "connected"
                              ? `Broker ready. ${brokerAuth.detail}`
                              : `Broker unavailable. ${brokerAuth.detail}`
                        }
                      />
                      <StatusPill
                        label="Execution"
                        tone={
                          errors.controlPlane
                            ? "inactive"
                            : controlPlane.entry_eligible
                              ? "positive"
                              : controlPlane.exit_eligible
                                ? "warning"
                                : "negative"
                        }
                        title={
                          errors.controlPlane
                            ? `Execution eligibility unknown. ${errors.controlPlane}`
                            : controlPlane.entry_eligible
                              ? "Execution ready. New entries and exits are currently eligible."
                              : controlPlane.exit_eligible
                                ? `Entries blocked, exits allowed. ${controlPlane.entry_block_reason?.replaceAll("_", " ") ?? "Operational policy is suppressing new entries."}`
                                : `Execution blocked. ${controlPlane.entry_block_reason?.replaceAll("_", " ") ?? controlPlane.exit_block_reason?.replaceAll("_", " ") ?? "Feed, broker, or freshness conditions are preventing execution."}`
                        }
                      />
                      <StatusPill
                        label="Open Risk"
                        tone={
                          errors.controlPlane
                            ? "inactive"
                            : openRiskUnavailable
                              ? "inactive"
                            : openRiskState === "UNMANAGED_OPEN_RISK"
                              ? "negative"
                              : openRiskState === "EXITS_ONLY"
                                ? "warning"
                                : "positive"
                        }
                        title={
                          errors.controlPlane
                            ? `Open-risk state unknown. ${errors.controlPlane}`
                            : openRiskUnavailable
                              ? `Open-risk state unavailable. ${controlPlane.open_risk_management_reason ?? "Control-plane state did not provide open-risk truth."}`
                            : openRiskState === "UNMANAGED_OPEN_RISK"
                              ? `Unmanaged open risk. ${controlPlane.open_risk_management_reason ?? "Open positions are no longer under active automated exit management."}`
                              : openRiskState === "EXITS_ONLY"
                                ? `Exit-only management. ${controlPlane.open_risk_management_reason ?? "Existing positions remain managed while new entries stay suppressed."}`
                                : `Open-risk state: ${openRiskState}.`
                        }
                      />
                    </div>
                  </div>
                  <div className="summary-bar">
                    <div className="summary-bar__item">
                      <span>System P/L</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.dailyPnl != null
                            ? formatSignedCurrency(dashboard.dailyPnl)
                            : renderMetricOrUnavailable("-", true, "System daily P/L is unavailable.")}
                      </strong>
                      <em>
                        {errors.dashboard
                          ? errors.dashboard
                          : dashboard.dailyPnlPercent != null
                            ? formatSignedPercent(dashboard.dailyPnlPercent)
                            : "derived from local trades and open positions"}
                      </em>
                    </div>
                    <div className="summary-bar__item">
                      <span>Win Rate</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.winRate != null
                            ? formatPercent(dashboard.winRate)
                            : renderMetricOrUnavailable("-", true, "Win rate is unavailable.")}
                      </strong>
                      <em>{errors.dashboard ? "unavailable" : "recent closed trades"}</em>
                    </div>
                    <div className="summary-bar__item">
                      <span>Risk / Reward</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.riskReward != null
                            ? `${dashboard.riskReward.toFixed(2)}R`
                            : renderMetricOrUnavailable("-", true, "Risk / reward is unavailable.")}
                      </strong>
                      <em>{errors.dashboard ? "KPI feed unavailable" : "recent closed trades"}</em>
                    </div>
                  </div>
                </section>

                <section className="dashboard-overview-section">
                  <div className="dashboard-overview-section__header">
                    <span className="console-kicker">Broker Info</span>
                  </div>
                  <div className="metric-matrix">
                    <div className="metric-matrix__item">
                      <span>Equity</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.brokerInfo
                            ? formatCurrency(dashboard.brokerInfo.equity)
                            : renderMetricOrUnavailable("-", true, "Broker equity is unavailable.")}
                      </strong>
                      <em>{dashboard.brokerInfo ? `${dashboard.brokerInfo.accountType} account` : "broker metrics unavailable"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Available</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.brokerInfo
                            ? formatCurrency(dashboard.brokerInfo.available)
                            : renderMetricOrUnavailable("-", true, "Broker available funds are unavailable.")}
                      </strong>
                      <em>{dashboard.brokerInfo ? "available to deal" : "broker metrics unavailable"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Balance</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.brokerInfo
                            ? formatCurrency(dashboard.brokerInfo.balance)
                            : renderMetricOrUnavailable("-", true, "Broker balance is unavailable.")}
                      </strong>
                      <em>{dashboard.brokerInfo ? "cash balance" : "broker metrics unavailable"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Account Id</span>
                      <strong>
                        {errors.dashboard
                          ? "-"
                          : dashboard.brokerInfo
                            ? dashboard.brokerInfo.accountId
                            : renderMetricOrUnavailable("-", true, "Broker account id is unavailable.")}
                      </strong>
                      <em>{dashboard.brokerInfo ? formatSignedCurrency(dashboard.brokerInfo.profitLoss) : "broker metrics unavailable"}</em>
                    </div>
                  </div>
                </section>

                <section className="dashboard-overview-section">
                  <div className="dashboard-overview-section__header">
                    <span className="console-kicker">Runtime Summary</span>
                  </div>
                  <div className="metric-matrix">
                    <div className="metric-matrix__item">
                      <span>Running</span>
                      <strong>{errors.dashboard ? "-" : runningCount}</strong>
                      <em>{errors.dashboard ? "runtime summary unavailable" : "active runtimes"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Degraded</span>
                      <strong>{errors.controlPlane ? "-" : degradedCount}</strong>
                      <em>{errors.controlPlane ? "control plane unavailable" : "families mismatched"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Paused</span>
                      <strong>{errors.controlPlane || errors.dashboard ? "-" : pausedCount}</strong>
                      <em>{errors.controlPlane || errors.dashboard ? "runtime summary unavailable" : "idle or stopped"}</em>
                    </div>
                    <div className="metric-matrix__item">
                      <span>Last trade</span>
                      <strong>{errors.trades ? "-" : sortedTrades[0] ? formatTimestamp(sortedTrades[0].close_time) : "none"}</strong>
                      <em>{errors.trades ? errors.trades : sortedTrades[0] ? formatInstrumentLabel(sortedTrades[0].instrument) : "no closes yet"}</em>
                    </div>
                  </div>
                </section>

                <section className="dashboard-overview-section">
                  <div className="dashboard-overview-section__header">
                    <span className="console-kicker">Risk</span>
                    <div className="console-inline-actions">
                      <StatusPill label={riskSummary.lastCycleStatus.label} tone={riskSummary.lastCycleStatus.tone} />
                      {riskSummary.degradedSizingOrTruth ? <StatusPill label="Degraded" tone="warning" /> : null}
                    </div>
                  </div>
                  <RiskStatusBlock summary={riskSummary} onOpenDrawer={() => setInspectorMode("risk")} />
                  <div className="risk-budget-grid">
                    <RiskPanel summary={riskSummary} />
                    <RiskAllocationPanel exposure={allocationExposure} summary={riskSummary} />
                  </div>
                </section>
              </div>
            </Panel>
          </div>
        </section>
      </main>

      {inspectorMode === "risk" ? (
        <RiskInspectorDrawer
          open
          onClose={() => setInspectorMode(null)}
          exposure={allocationExposure}
          alerts={allocationAlerts}
          drift={allocationDrift}
          cycles={allocationCycles}
          intents={allocationIntents}
        />
      ) : null}

      <InspectorDrawer
        title={drawerTitle}
        subtitle={
          inspectorMode === "positions"
            ? "Detailed book view."
            : inspectorMode === "trades"
              ? "Recent closed trades."
              : inspectorMode === "activity"
                ? "Recent execution and system transitions."
                : inspectorMode === "risk"
                  ? "Current allocation briefing."
                : undefined
        }
        open={inspectorMode !== null && inspectorMode !== "risk"}
        onClose={() => setInspectorMode(null)}
      >
        {inspectorMode === "positions" ? (
          <CompactTable
            rows={exposureRows}
            emptyLabel={errors.positions ? "Positions unavailable." : "No open positions."}
            getRowTone={(row) => ((row.risk_percent ?? 0) > 1 ? "warning" : "neutral")}
            columns={[
              {
                key: "instrument",
                header: "Instrument",
                render: (row) => (
                  <div className="cell-stack">
                    <strong>{formatInstrumentLabel(row.instrument)}</strong>
                    <span className="console-subtle">{row.strategy_name}</span>
                  </div>
                ),
              },
              {
                key: "side",
                header: "Side",
                render: (row) => <StatusPill label={row.direction} tone={row.direction === "BUY" ? "positive" : "warning"} />,
              },
              {
                key: "risk",
                header: "Risk",
                render: (row) => (row.risk_percent != null ? formatPercent(row.risk_percent) : "n/a"),
              },
              {
                key: "pnl",
                header: "Unrealized",
                render: (row) => (row.unrealized_pnl != null ? formatSignedCurrency(row.unrealized_pnl) : "n/a"),
              },
            ]}
          />
        ) : null}
        {inspectorMode === "trades" ? (
          <CompactTable
            rows={sortedTrades.slice(0, 30)}
            emptyLabel={errors.trades ? "Trades unavailable." : "No trades recorded."}
            getRowTone={(row) => (row.pnl < 0 ? "warning" : "neutral")}
            columns={[
              {
                key: "trade",
                header: "Trade",
                render: (row) => (
                  <div className="cell-stack">
                    <strong>{row.strategy_name}</strong>
                    <span className="console-subtle">{formatInstrumentLabel(row.instrument)}</span>
                  </div>
                ),
              },
              { key: "side", header: "Side", render: (row) => row.direction },
              { key: "closed", header: "Closed", render: (row) => formatTimestamp(row.close_time) },
              { key: "source", header: "Source", render: (row) => closeSourceLabel(row.close_execution_source) },
              { key: "pnl", header: "PnL", render: (row) => formatSignedCurrency(row.pnl) },
            ]}
          />
        ) : null}
        {inspectorMode === "activity" ? (
          <CompactTable
            rows={recentExecutions.slice(0, 20)}
            emptyLabel={errors.executions ? "Activity feed unavailable." : "No recent activity."}
            getRowTone={(row) =>
              row.status === "FAILED" || row.status === "NEEDS_MANUAL_REVIEW"
                ? "negative"
                : row.status === "RISK_REJECTED"
                  ? "warning"
                  : "neutral"
            }
            columns={[
              { key: "time", header: "Age", render: (row) => formatRelativeDuration(row.last_transition_at) },
              { key: "strategy", header: "Strategy", render: (row) => row.strategy_name },
              { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
              { key: "status", header: "Status", render: (row) => row.status.replaceAll("_", " ") },
              { key: "request", header: "Request", render: (row) => row.client_request_id ?? "n/a" },
              { key: "broker", header: "Broker Ref", render: (row) => row.broker_reference ?? "n/a" },
            ]}
          />
        ) : null}
      </InspectorDrawer>
    </>
  );
}
