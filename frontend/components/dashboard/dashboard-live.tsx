"use client";

import { useEffect, useMemo, useState } from "react";

import {
  BoardLayout,
  CompactTable,
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
  ]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
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
        ] = await Promise.all([
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

        setPositions(nextPositions);
        setTrades(nextTrades);
        setExecutions(nextExecutions);
        setBrokerAuth(nextBrokerAuth);
        setDashboard(nextDashboard);
        setStreamHealth(nextStreamHealth);
        setCoverage(nextCoverage);
        setControlPlane(nextControlPlane);
        setOperatingLimits(nextOperatingLimits);
      } catch {
        // Preserve last visible snapshot on transient failures.
      }
    };

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
  const lastTrade = sortedTrades[0];
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
    !controlPlane.effective_autonomous_control_enabled || brokerAuth.state === "unavailable"
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
        <StatusStrip
          items={[
            {
              label: "Autonomy",
              value: controlPlane.effective_autonomous_control_enabled ? "Running" : "Stopped",
              tone: healthTone,
              meta: `${runningCount} runtimes active`,
              emphasis: "strong",
            },
            {
              label: "Alerts",
              value: manualReviewExecutions.length + strategyExceptions.length,
              tone: manualReviewExecutions.length ? "negative" : strategyExceptions.length ? "warning" : "positive",
              meta: manualReviewExecutions.length ? "intervention likely" : "none urgent",
              emphasis: "strong",
            },
            {
              label: "Broker",
              value: brokerAuth.state === "connected" ? "Connected" : brokerAuth.label,
              tone:
                brokerAuth.state === "connected"
                  ? "positive"
                  : brokerAuth.state === "disconnected"
                    ? "warning"
                    : "inactive",
              meta: brokerAuth.detail,
            },
            {
              label: "Stream",
              value: streamHealth.connected ? "Live" : streamHealth.enabled ? "Interrupted" : "Unavailable",
              tone: streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "inactive",
              meta: streamHealth.last_status ?? "no status",
            },
            {
              label: "Coverage",
              value: `${coverage.streaming.active_instruments.length}/${coverage.streaming.desired_instruments.length}`,
              tone: staleCoverage.length ? "warning" : "neutral",
              meta: staleCoverage.length ? `${staleCoverage.length} blocked` : "ready",
            },
            {
              label: "Open Risk",
              value: formatPercent(dashboard.openRisk),
              tone: dashboard.openRisk > operatingLimits.risk.max_open_risk_percent ? "negative" : "neutral",
              meta: `limit ${formatPercent(operatingLimits.risk.max_open_risk_percent)}`,
            },
          ]}
        />

        <BoardLayout
          left={
            <ExceptionList
              title="Exceptions"
              subtitle="Anything here deserves attention before normal monitoring."
              items={exceptionItems}
              emptyLabel="No active exceptions. System behavior is nominal."
              priority="critical"
            />
          }
          center={
            <>
              <Panel title="System Health" priority="primary" tone={healthTone}>
                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>Account</span>
                    <strong>{formatCurrency(dashboard.accountValue)}</strong>
                    <em>{formatSignedPercent(dashboard.accountValuePercent)}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Daily PnL</span>
                    <strong>{formatSignedCurrency(dashboard.dailyPnl)}</strong>
                    <em>{formatSignedPercent(dashboard.dailyPnlPercent)}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Win / R:R</span>
                    <strong>{formatPercent(dashboard.winRate)} / {dashboard.riskReward.toFixed(2)}</strong>
                    <em>recent closed trades</em>
                  </div>
                </div>
                <div className="console-inline-actions">
                  <StatusPill
                    label={controlPlane.effective_autonomous_control_enabled ? "autonomy armed" : "autonomy stopped"}
                    tone={controlPlane.effective_autonomous_control_enabled ? "positive" : "negative"}
                  />
                  <StatusPill
                    label={streamHealth.connected ? "market data live" : "feed degraded"}
                    tone={streamHealth.connected ? "positive" : "warning"}
                  />
                  <StatusPill
                    label={brokerAuth.state === "connected" ? "broker ready" : "broker unavailable"}
                    tone={brokerAuth.state === "connected" ? "positive" : "inactive"}
                  />
                </div>
              </Panel>

              <Panel title="Runtime Summary" priority="secondary" tone={degradedCount ? "warning" : "neutral"} compact>
                <div className="metric-matrix">
                  <div className="metric-matrix__item">
                    <span>Running</span>
                    <strong>{runningCount}</strong>
                    <em>active runtimes</em>
                  </div>
                  <div className="metric-matrix__item">
                    <span>Degraded</span>
                    <strong>{degradedCount}</strong>
                    <em>families mismatched</em>
                  </div>
                  <div className="metric-matrix__item">
                    <span>Paused</span>
                    <strong>{pausedCount}</strong>
                    <em>idle or stopped</em>
                  </div>
                  <div className="metric-matrix__item">
                    <span>Last trade</span>
                    <strong>{lastTrade ? formatTimestamp(lastTrade.close_time) : "none"}</strong>
                    <em>{lastTrade ? formatInstrumentLabel(lastTrade.instrument) : "no closes yet"}</em>
                  </div>
                </div>
              </Panel>
            </>
          }
          right={
            <>
              <Panel title="Exposure" priority="secondary" tone={concentrationPercent > 45 ? "warning" : "neutral"} compact>
                <div className="summary-cluster">
                  <div className="summary-cluster__row">
                    <span>Gross</span>
                    <strong>{formatCurrency(grossExposure)}</strong>
                  </div>
                  <div className="summary-cluster__row">
                    <span>Bias</span>
                    <strong>{netExposure >= 0 ? "Long" : "Short"} {formatCurrency(Math.abs(netExposure))}</strong>
                  </div>
                  <div className="summary-cluster__row">
                    <span>Concentration</span>
                    <strong>{formatPercent(concentrationPercent)}</strong>
                  </div>
                  <div className="summary-cluster__row">
                    <span>Top line</span>
                    <strong>{topExposure ? formatInstrumentLabel(topExposure.instrument) : "none"}</strong>
                  </div>
                </div>
              </Panel>

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
            </>
          }
        />
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
            emptyLabel="No open positions."
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
            emptyLabel="No trades recorded."
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
            emptyLabel="No recent activity."
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
