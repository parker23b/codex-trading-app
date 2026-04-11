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
import {
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
  };
};

type InspectorMode = "positions" | "trades" | "activity" | null;

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
  const longExposure = exposureRows
    .filter((position) => position.direction === "BUY")
    .reduce((sum, position) => sum + position.notional, 0);
  const shortExposure = exposureRows
    .filter((position) => position.direction === "SELL")
    .reduce((sum, position) => sum + position.notional, 0);
  const grossExposure = longExposure + shortExposure;
  const netExposure = longExposure - shortExposure;
  const largestPositionNotional = exposureRows.length ? Math.max(...exposureRows.map((position) => position.notional)) : 0;
  const concentrationPercent = grossExposure > 0 ? (largestPositionNotional / grossExposure) * 100 : 0;
  const topExposure = exposureRows.slice().sort((left, right) => right.notional - left.notional)[0];

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
  const healthTone =
    errors.controlPlane || errors.brokerAuth
      ? "inactive"
      : !controlPlane.effective_autonomous_control_enabled || brokerAuth.state === "unavailable"
      ? "negative"
      : manualReviewExecutions.length || staleCoverage.length || strategyExceptions.length
        ? "warning"
        : "positive";

  const drawerTitle =
    inspectorMode === "positions"
      ? "Positions"
      : inspectorMode === "trades"
        ? "Trades"
        : inspectorMode === "activity"
          ? "Recent Activity"
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
                ) : controlPlane.effective_autonomous_control_enabled ? (
                  "Running"
                ) : (
                  "Stopped"
                ),
                tone: errors.controlPlane ? "inactive" : healthTone,
                meta: errors.controlPlane ?? `${runningCount} runtimes active`,
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
                ) : streamHealth.connected ? (
                  "Live"
                ) : streamHealth.enabled ? (
                  "Interrupted"
                ) : (
                  "Unavailable"
                ),
                tone: errors.streamHealth ? "inactive" : streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "inactive",
                meta: errors.streamHealth ?? streamHealth.last_status ?? "no status",
              },
              {
                label: "Coverage",
                value: errors.coverage ? "-" : `${coverage.streaming.active_instruments.length}/${coverage.streaming.desired_instruments.length}`,
                tone: errors.coverage ? "inactive" : staleCoverage.length ? "warning" : "neutral",
                meta: errors.coverage ?? (staleCoverage.length ? `${staleCoverage.length} blocked` : "ready"),
              },
              {
                label: "Open Risk",
                value: errors.dashboard || errors.operatingLimits ? "-" : formatPercent(dashboard.openRisk),
                tone: errors.dashboard || errors.operatingLimits ? "inactive" : dashboard.openRisk > operatingLimits.risk.max_open_risk_percent ? "negative" : "neutral",
                meta: errors.dashboard ?? errors.operatingLimits ?? `limit ${formatPercent(operatingLimits.risk.max_open_risk_percent)}`,
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
                            : controlPlane.effective_autonomous_control_enabled
                              ? "Autonomy armed. Governed autonomous control is enabled."
                              : "Autonomy stopped. Governed autonomous control is paused."
                        }
                      />
                      <StatusPill
                        label="Feed"
                        tone={errors.streamHealth ? "inactive" : streamHealth.connected ? "positive" : "warning"}
                        title={
                          errors.streamHealth
                            ? `Feed unknown. ${errors.streamHealth}`
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
                    <span className="console-kicker">Exposure</span>
                  </div>
                  <div className="summary-cluster">
                    <div className="summary-cluster__row">
                      <span>Gross</span>
                      <strong>{errors.positions ? "-" : formatCurrency(grossExposure)}</strong>
                    </div>
                    <div className="summary-cluster__row">
                      <span>Bias</span>
                      <strong>{errors.positions ? "-" : `${netExposure >= 0 ? "Long" : "Short"} ${formatCurrency(Math.abs(netExposure))}`}</strong>
                    </div>
                    <div className="summary-cluster__row">
                      <span>Concentration</span>
                      <strong>{errors.positions ? "-" : formatPercent(concentrationPercent)}</strong>
                    </div>
                    <div className="summary-cluster__row">
                      <span>Top line</span>
                      <strong>{errors.positions ? "-" : topExposure ? formatInstrumentLabel(topExposure.instrument) : "none"}</strong>
                    </div>
                  </div>
                </section>
              </div>
            </Panel>
          </div>
        </section>
      </main>

      <InspectorDrawer
        title={drawerTitle}
        subtitle={
          inspectorMode === "positions"
            ? "Detailed book view."
            : inspectorMode === "trades"
              ? "Recent closed trades."
              : inspectorMode === "activity"
                ? "Recent execution and system transitions."
                : undefined
        }
        open={inspectorMode !== null}
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
            ]}
          />
        ) : null}
      </InspectorDrawer>
    </>
  );
}
