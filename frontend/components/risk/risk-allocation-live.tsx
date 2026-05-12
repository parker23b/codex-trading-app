"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import {
  acknowledgeAllocationAlert,
  getAllocationAlerts,
  getAllocationCycle,
  getAllocationCycles,
  getAllocationDriftSummary,
  getAllocationExposureSummary,
  getAllocationIntents,
  resolveAllocationAlert,
} from "@/lib/api";
import { formatCurrency, formatDateTime, formatInstrumentLabel, formatPercent, formatPrice, formatRelativeDuration } from "@/lib/format";
import {
  alertSeverityTone,
  buildRiskLoadQuality,
  buildRiskConsoleSummary,
  cycleStatus,
  formatDirectionalBias,
  formatHotspotLabel,
  RiskLoadErrors,
  truthConfidenceMeta,
} from "@/lib/risk-allocation";
import type {
  AllocationAlert,
  AllocationCycle,
  AllocationDriftSummary,
  AllocationExposureSummary,
  AllocationIntent,
  ExposureBucket,
} from "@/lib/types";
import { CompactTable, Panel, SplitPanel, StatusPill, StatusStrip } from "@/components/console/primitives";

type RiskAllocationLiveProps = {
  initialExposure: AllocationExposureSummary;
  initialAlerts: AllocationAlert[];
  initialDrift: AllocationDriftSummary;
  initialCycles: AllocationCycle[];
  initialIntents: AllocationIntent[];
  initialSelectedCycle: AllocationCycle | null;
  initialLoadErrors?: RiskLoadErrors;
};

function budgetTone(utilization?: number | null) {
  if (utilization == null) {
    return "inactive" as const;
  }
  if (utilization >= 100) {
    return "negative" as const;
  }
  if (utilization >= 80) {
    return "warning" as const;
  }
  return "positive" as const;
}

function metricDriftValue(value: unknown) {
  if (!value || typeof value !== "object") {
    return "n/a";
  }
  const metric = value as { expected?: number; actual?: number; percent_drift_abs?: number };
  if (typeof metric.expected !== "number" || typeof metric.actual !== "number") {
    return "n/a";
  }
  return `${metric.expected.toFixed(2)} → ${metric.actual.toFixed(2)} (${formatPercent(metric.percent_drift_abs ?? 0)})`;
}

function topBuckets(buckets: ExposureBucket[], limit = 5) {
  return buckets
    .slice()
    .sort((left, right) => (right.utilization_percent ?? 0) - (left.utilization_percent ?? 0))
    .slice(0, limit);
}

export function RiskAllocationLive({
  initialExposure,
  initialAlerts,
  initialDrift,
  initialCycles,
  initialIntents,
  initialSelectedCycle,
  initialLoadErrors = {},
}: RiskAllocationLiveProps) {
  const [exposure, setExposure] = useState(initialExposure);
  const [alerts, setAlerts] = useState(initialAlerts);
  const [drift, setDrift] = useState(initialDrift);
  const [cycles, setCycles] = useState(initialCycles);
  const [intents, setIntents] = useState(initialIntents);
  const [selectedCycleId, setSelectedCycleId] = useState<string | null>(initialSelectedCycle?.cycle_id ?? initialCycles[0]?.cycle_id ?? null);
  const [selectedCycle, setSelectedCycle] = useState<AllocationCycle | null>(initialSelectedCycle);
  const [alertSeverityFilter, setAlertSeverityFilter] = useState<"all" | "error" | "warning" | "info">("all");
  const [alertStateFilter, setAlertStateFilter] = useState<"all" | "OPEN" | "ACKNOWLEDGED" | "RESOLVED">("all");
  const [alertTypeFilter, setAlertTypeFilter] = useState("");
  const [loadErrors, setLoadErrors] = useState<RiskLoadErrors>(initialLoadErrors);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;

    const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : "Risk read failed";

    const refresh = async () => {
      const [nextExposure, nextAlerts, nextDrift, nextCycles, nextIntents, nextSelectedCycle] = await Promise.allSettled([
        getAllocationExposureSummary(),
        getAllocationAlerts({ limit: 60 }),
        getAllocationDriftSummary({ limit: 30, windowMinutes: 720 }),
        getAllocationCycles(24),
        getAllocationIntents({ limit: 60 }),
        selectedCycleId ? getAllocationCycle(selectedCycleId) : Promise.resolve(null),
      ]);

      if (cancelled) {
        return;
      }
      if (nextExposure.status === "fulfilled") {
        setExposure(nextExposure.value);
      }
      if (nextAlerts.status === "fulfilled") {
        setAlerts(nextAlerts.value);
      }
      if (nextDrift.status === "fulfilled") {
        setDrift(nextDrift.value);
      }
      if (nextCycles.status === "fulfilled") {
        setCycles(nextCycles.value);
      }
      if (nextIntents.status === "fulfilled") {
        setIntents(nextIntents.value);
      }
      if (nextSelectedCycle.status === "fulfilled") {
        setSelectedCycle(nextSelectedCycle.value);
      }
      setLoadErrors({
        exposure: nextExposure.status === "rejected" ? errorMessage(nextExposure.reason) : null,
        alerts: nextAlerts.status === "rejected" ? errorMessage(nextAlerts.reason) : null,
        drift: nextDrift.status === "rejected" ? errorMessage(nextDrift.reason) : null,
        cycles: nextCycles.status === "rejected" ? errorMessage(nextCycles.reason) : null,
        intents: nextIntents.status === "rejected" ? errorMessage(nextIntents.reason) : null,
        selectedCycle: nextSelectedCycle.status === "rejected" ? errorMessage(nextSelectedCycle.reason) : null,
      });
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 7000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedCycleId]);

  useEffect(() => {
    if (!selectedCycleId && cycles[0]) {
      setSelectedCycleId(cycles[0].cycle_id);
    }
  }, [cycles, selectedCycleId]);

  const summary = useMemo(
    () => buildRiskConsoleSummary({ exposure, alerts, drift, cycles, intents }),
    [exposure, alerts, drift, cycles, intents],
  );
  const loadQuality = useMemo(() => buildRiskLoadQuality(loadErrors), [loadErrors]);

  const unresolvedAlerts = alerts.filter((alert) => alert.state !== "RESOLVED");
  const criticalAlerts = unresolvedAlerts.filter((alert) => alert.severity === "error");
  const filteredAlerts = alerts
    .filter((alert) => (alertSeverityFilter === "all" ? true : alert.severity === alertSeverityFilter))
    .filter((alert) => (alertStateFilter === "all" ? true : alert.state === alertStateFilter))
    .filter((alert) => (alertTypeFilter.trim() ? alert.alert_type.toLowerCase().includes(alertTypeFilter.trim().toLowerCase()) : true))
    .sort((left, right) => {
      const stateRank = (value: string) => (value === "OPEN" ? 0 : value === "ACKNOWLEDGED" ? 1 : 2);
      return stateRank(left.state) - stateRank(right.state);
    });
  const hotspotBuckets = topBuckets(exposure.by_family, 4);
  const topStrategies = topBuckets(exposure.by_strategy, 5);
  const topInstruments = topBuckets(exposure.by_instrument, 5);
  const selectedCycleStatus = cycleStatus(selectedCycle);
  const exposureUnavailable = loadQuality.sectionUnavailable("exposure");
  const alertsUnavailable = loadQuality.sectionUnavailable("alerts");
  const driftUnavailable = loadQuality.sectionUnavailable("drift");
  const cyclesUnavailable = loadQuality.sectionUnavailable("cycles");
  const intentsUnavailable = loadQuality.sectionUnavailable("intents");

  async function mutateAlert(alertId: number, action: "acknowledge" | "resolve") {
    startTransition(async () => {
      if (action === "acknowledge") {
        await acknowledgeAllocationAlert(alertId);
      } else {
        await resolveAllocationAlert(alertId);
      }
      const nextAlerts = await getAllocationAlerts({ limit: 60, refresh: true });
      setAlerts(nextAlerts);
    });
  }

  return (
    <main className="console-page console-page--dense risk-page-shell">
      <section className="risk-page-hero">
        <div className="risk-page-hero__copy">
          <span className="console-kicker">Risk / Capital Allocation</span>
          <h1>Capital pressure, execution truth, and exposure concentration.</h1>
          <p>
            This page is the deep inspection surface for allocation decisions. Operate stays calm; this page shows the
            why behind pressure, drift, degraded truth, and intervention-worthy alerts.
          </p>
        </div>
        <div className="risk-page-hero__context">
          {loadQuality.degraded ? <StatusPill label={loadQuality.headline} tone="negative" title={loadQuality.detail} /> : null}
          <StatusPill
            label={
              alertsUnavailable
                ? "Alerts unavailable"
                : summary.criticalAlertCount > 0
                  ? `${summary.criticalAlertCount} critical alerts`
                  : "No critical alerts"
            }
            tone={alertsUnavailable || summary.criticalAlertCount > 0 ? "negative" : "positive"}
          />
          {summary.degradedSizingOrTruth ? <StatusPill label="Degraded sizing/truth" tone="warning" /> : null}
          <StatusPill
            label={cyclesUnavailable ? "Cycles unavailable" : summary.lastCycleStatus.label}
            tone={cyclesUnavailable ? "negative" : summary.lastCycleStatus.tone}
          />
        </div>
      </section>

      {loadQuality.degraded ? <div className="status-note status-note--inline">{loadQuality.detail}</div> : null}

      <StatusStrip
        items={[
          {
            label: "Open Risk",
            value: exposureUnavailable ? "Unavailable" : formatPercent(summary.openRiskPercent),
            tone: exposureUnavailable
              ? "negative"
              : budgetTone((summary.openRiskPercent / Math.max(summary.openRiskPercent + summary.remainingPortfolioRiskPercent, 0.0001)) * 100),
            meta: exposureUnavailable ? "Exposure read failed" : `${exposure.totals.open_position_count} live positions`,
          },
          {
            label: "Reserved Risk",
            value: exposureUnavailable ? "Unavailable" : formatPercent(summary.reservedRiskPercent),
            tone: exposureUnavailable ? "negative" : summary.reservedRiskPercent > 0 ? "warning" : "positive",
            meta: exposureUnavailable ? "Exposure read failed" : `${exposure.totals.reserved_intent_count} reserved intents`,
          },
          {
            label: "Active Risk",
            value: exposureUnavailable ? "Unavailable" : formatPercent(summary.totalActiveRiskPercent),
            tone: exposureUnavailable
              ? "negative"
              : summary.totalActiveRiskPercent > 4
                ? "negative"
                : summary.totalActiveRiskPercent > 2.5
                  ? "warning"
                  : "positive",
            meta: exposureUnavailable ? "Exposure read failed" : `${formatPercent(summary.remainingPortfolioRiskPercent)} remaining`,
          },
          {
            label: "Critical Alerts",
            value: alertsUnavailable ? "Unavailable" : String(summary.criticalAlertCount),
            tone: alertsUnavailable || summary.criticalAlertCount > 0 ? "negative" : "positive",
            meta: alertsUnavailable
              ? "Alert read failed"
              : summary.warningAlertCount > 0
                ? `${summary.warningAlertCount} warnings open`
                : "No warning backlog",
          },
          {
            label: "Material Drift",
            value: driftUnavailable ? "Unavailable" : String(summary.materialDriftCount),
            tone: driftUnavailable ? "negative" : summary.materialDriftCount > 0 ? "warning" : "positive",
            meta: driftUnavailable ? "Drift read failed" : `critical at ${formatPercent(drift.drift_critical_percent)}`,
          },
          {
            label: "Risk Truth",
            value: intentsUnavailable || exposureUnavailable
              ? "Unavailable"
              : summary.truthMix.degraded > 0
                ? `${summary.truthMix.degraded} degraded`
                : summary.truthMix.provisional > 0
                  ? `${summary.truthMix.provisional} provisional`
                  : `${summary.truthMix.exact} exact`,
            tone: intentsUnavailable || exposureUnavailable
              ? "negative"
              : summary.truthMix.degraded > 0
                ? "negative"
                : summary.truthMix.provisional > 0 || summary.truthMix.estimated > 0
                  ? "warning"
                  : "positive",
            meta: intentsUnavailable || exposureUnavailable
              ? "Risk truth read failed"
              : `${summary.truthMix.estimated} estimated · ${summary.truthMix.exact} exact`,
          },
        ]}
      />

      <SplitPanel
        left={(
          <>
            <Panel title="Budgets" subtitle="Where risk budget is actually being consumed." priority="primary" tone={exposureUnavailable ? "negative" : summary.topHotspot ? budgetTone(summary.topHotspot.utilization_percent) : "neutral"}>
              <div className="risk-budget-grid">
                <div className="risk-budget-card">
                  <span>Total portfolio risk</span>
                  <strong>{formatPercent(summary.totalActiveRiskPercent)}</strong>
                  <em>{`${formatPercent(summary.remainingPortfolioRiskPercent)} headroom remaining`}</em>
                </div>
                <div className="risk-budget-card">
                  <span>Reserved vs live</span>
                  <strong>{`${formatPercent(summary.reservedRiskPercent)} / ${formatPercent(summary.openRiskPercent)}`}</strong>
                  <em>{`${exposure.totals.reserved_intent_count} reserved intents · ${exposure.totals.open_position_count} positions`}</em>
                </div>
              </div>
              <CompactTable
                rows={hotspotBuckets}
                emptyLabel={exposureUnavailable ? "Risk exposure unavailable." : "No family budget hotspots."}
                getRowTone={(row) => budgetTone(row.utilization_percent)}
                columns={[
                  { key: "family", header: "Family", render: (row) => row.name },
                  { key: "risk", header: "Total Risk", render: (row) => formatPercent(row.total_risk_percent) },
                  { key: "util", header: "Utilization", render: (row) => row.utilization_percent != null ? formatPercent(row.utilization_percent) : "n/a" },
                  { key: "remaining", header: "Headroom", render: (row) => formatPercent(row.remaining_risk_percent) },
                ]}
              />
            </Panel>

            <Panel title="Exposure" subtitle="Live concentration by family, strategy, instrument, and FX direction." priority="secondary" tone={exposureUnavailable ? "negative" : summary.topHotspot ? budgetTone(summary.topHotspot.utilization_percent) : "neutral"}>
              <div className="risk-budget-grid">
                <div className="risk-budget-card">
                  <span>Top hotspot</span>
                  <strong>{formatHotspotLabel(summary.topHotspot)}</strong>
                  <em>Highest current budget pressure</em>
                </div>
                <div className="risk-budget-card">
                  <span>Directional net bias</span>
                  <strong>{formatDirectionalBias(summary.dominantNetCurrency)}</strong>
                  <em>Derived from pair direction and currency side</em>
                </div>
              </div>
              <CompactTable
                rows={exposure.currency_directional.slice().sort((a, b) => b.gross_utilization_percent - a.gross_utilization_percent).slice(0, 6)}
                emptyLabel="Directional FX exposure is unavailable."
                getRowTone={(row) => budgetTone(row.gross_utilization_percent)}
                columns={[
                  { key: "ccy", header: "Currency", render: (row) => row.currency },
                  { key: "gross", header: "Gross", render: (row) => formatPercent(row.gross_risk_percent) },
                  { key: "net", header: "Net", render: (row) => `${row.net_bias.toLowerCase()} ${formatPercent(Math.abs(row.net_risk_percent))}` },
                  { key: "basis", header: "Basis", render: (row) => row.risk_basis.join(", ") || "n/a" },
                ]}
              />
              <div className="status-note">
                {exposure.notes.currency_directional_exactness}. Currency exposure is more truthful than the old gross-only view,
                but it is still not institutional factor analytics.
              </div>
            </Panel>
          </>
        )}
        center={(
          <>
            <Panel title="Allocation Cycles" subtitle="Recent allocation batches, with constraint and degraded-state visibility." priority="primary" tone={cyclesUnavailable ? "negative" : summary.lastCycleStatus.tone}>
              <CompactTable
                rows={cycles}
                emptyLabel={cyclesUnavailable ? "Allocation cycles unavailable." : "No recent allocation cycles."}
                getRowTone={(row) => cycleStatus(row).tone}
                getRowActive={(row) => row.cycle_id === selectedCycleId}
                columns={[
                  {
                    key: "cycle",
                    header: "Cycle",
                    render: (row) => (
                      <button type="button" className="console-link-button" onClick={() => setSelectedCycleId(row.cycle_id)}>
                        <div className="cell-stack">
                          <strong>{row.cycle_id.slice(0, 12)}</strong>
                          <span className="console-subtle">{formatRelativeDuration(row.completed_at)} ago</span>
                        </div>
                      </button>
                    ),
                  },
                  { key: "counts", header: "Cand / App / Rej", render: (row) => `${row.candidate_count} / ${row.approved_count} / ${row.rejected_count}` },
                  { key: "risk", header: "Req / Alloc", render: (row) => `${formatPercent(row.total_requested_risk_percent)} / ${formatPercent(row.total_allocated_risk_percent)}` },
                  { key: "status", header: "Status", render: (row) => cycleStatus(row).label },
                ]}
              />
              <div className="risk-cycle-detail">
                <div className="risk-cycle-detail__header">
                  <span className="console-kicker">Selected cycle</span>
                  <StatusPill label={selectedCycleStatus.label} tone={selectedCycleStatus.tone} />
                </div>
                {selectedCycle ? (
                  <div className="risk-cycle-detail__grid">
                    <div className="risk-budget-card">
                      <span>When</span>
                      <strong>{formatDateTime(selectedCycle.completed_at)}</strong>
                      <em>{selectedCycleStatus.meta}</em>
                    </div>
                    <div className="risk-budget-card">
                      <span>Binding budget</span>
                      <strong>{Object.entries(selectedCycle.binding_budget_counts ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "none"}</strong>
                      <em>{selectedCycle.blocked_budget_count} budget blocks</em>
                    </div>
                    <div className="risk-budget-card">
                      <span>Degraded / resized</span>
                      <strong>{`${selectedCycle.degraded_candidate_count} / ${selectedCycle.resized_candidate_count}`}</strong>
                      <em>Candidates affected in this cycle</em>
                    </div>
                  </div>
                ) : null}
                {selectedCycle?.intents?.length ? (
                  <CompactTable
                    rows={selectedCycle.intents.slice(0, 8)}
                    emptyLabel="No cycle intents available."
                    dense
                    getRowTone={(row) => {
                      const stage = String(row.allocation_outcome?.stage ?? "");
                      return stage.includes("rejected") || stage.includes("failed")
                        ? "warning"
                        : row.state === "POSITION_OPENED"
                          ? "positive"
                          : "neutral";
                    }}
                    columns={[
                      {
                        key: "intent",
                        header: "Intent",
                        render: (row) => (
                          <div className="cell-stack">
                            <strong>{formatInstrumentLabel(row.instrument)}</strong>
                            <span className="console-subtle">{row.family_name ?? row.strategy_name}</span>
                          </div>
                        ),
                      },
                      { key: "state", header: "State", render: (row) => row.state.replaceAll("_", " ") },
                      { key: "risk", header: "Allocated Risk", render: (row) => row.allocated_risk_percent != null ? formatPercent(row.allocated_risk_percent) : "n/a" },
                      { key: "reason", header: "Reason", render: (row) => String(row.decision_reason ?? row.decision_reason_code ?? "none") },
                    ]}
                  />
                ) : (
                  <div className="console-empty">Select a cycle to inspect it.</div>
                )}
              </div>
            </Panel>

            <Panel title="Execution Drift" subtitle="Where broker normalization, submission, or fills changed the intended allocation." priority="secondary" tone={driftUnavailable ? "negative" : summary.materialDriftCount > 0 ? "warning" : "positive"}>
              <CompactTable
                rows={drift.worst_intents.slice(0, 8)}
                emptyLabel={driftUnavailable ? "Execution drift unavailable." : "No material drift cases within the current window."}
                getRowTone={(row) => row.max_percent_drift >= drift.drift_critical_percent ? "negative" : "warning"}
                columns={[
                  {
                    key: "intent",
                    header: "Intent",
                    render: (row) => (
                      <div className="cell-stack">
                        <strong>{formatInstrumentLabel(row.instrument)}</strong>
                        <span className="console-subtle">{row.family_name ?? row.strategy_name}</span>
                      </div>
                    ),
                  },
                  { key: "drift", header: "Max Drift", render: (row) => formatPercent(row.max_percent_drift) },
                  {
                    key: "worst-metric",
                    header: "Worst Metric",
                    render: (row) => {
                      const [metricName, metricValue] = Object.entries(row.drift_metrics ?? {}).find((entry) => {
                        const metric = entry[1] as { percent_drift_abs?: number } | undefined;
                        return typeof metric?.percent_drift_abs === "number";
                      }) ?? ["n/a", null];
                      return `${metricName}: ${metricDriftValue(metricValue)}`;
                    },
                  },
                ]}
              />
              <div className="risk-group-grid">
                <div className="risk-group-card">
                  <span>Worst families</span>
                  {drift.by_family.slice(0, 4).map((bucket) => (
                    <strong key={bucket.name}>{`${bucket.name}: ${formatPercent(bucket.max_percent_drift)}`}</strong>
                  ))}
                </div>
                <div className="risk-group-card">
                  <span>Worst instruments</span>
                  {drift.by_instrument.slice(0, 4).map((bucket) => (
                    <strong key={bucket.name}>{`${formatInstrumentLabel(bucket.name)}: ${formatPercent(bucket.max_percent_drift)}`}</strong>
                  ))}
                </div>
              </div>
            </Panel>
          </>
        )}
        right={(
          <>
            <Panel title="Alerts" subtitle="Unresolved allocation and execution-truth issues, with operator workflow." priority="critical" tone={alertsUnavailable ? "negative" : criticalAlerts.length ? "negative" : unresolvedAlerts.length ? "warning" : "positive"}>
              <div className="risk-alert-toolbar">
                <StatusPill label={`${criticalAlerts.length} critical`} tone={criticalAlerts.length ? "negative" : "positive"} />
                <StatusPill label={`${unresolvedAlerts.length} unresolved`} tone={unresolvedAlerts.length ? "warning" : "positive"} />
              </div>
              <div className="risk-alert-filters">
                <select className="console-select" value={alertSeverityFilter} onChange={(event) => setAlertSeverityFilter(event.target.value as typeof alertSeverityFilter)}>
                  <option value="all">All severities</option>
                  <option value="error">Critical only</option>
                  <option value="warning">Warnings only</option>
                  <option value="info">Info only</option>
                </select>
                <select className="console-select" value={alertStateFilter} onChange={(event) => setAlertStateFilter(event.target.value as typeof alertStateFilter)}>
                  <option value="all">All states</option>
                  <option value="OPEN">Open</option>
                  <option value="ACKNOWLEDGED">Acknowledged</option>
                  <option value="RESOLVED">Resolved</option>
                </select>
                <input
                  className="console-input"
                  value={alertTypeFilter}
                  onChange={(event) => setAlertTypeFilter(event.target.value)}
                  placeholder="Filter alert type"
                />
              </div>
              <div className="detail-stack">
                {filteredAlerts.map((alert) => (
                  <article key={alert.id} className={`risk-alert-card risk-alert-card--${alertSeverityTone(alert.severity)}`}>
                    <div className="risk-alert-card__title">
                      <div className="cell-stack">
                        <strong>{alert.title}</strong>
                        <span className="console-subtle">{alert.message}</span>
                      </div>
                      <StatusPill label={alert.state.toLowerCase()} tone={alertSeverityTone(alert.severity)} />
                    </div>
                    <div className="risk-alert-card__meta">
                      <span>{`${alert.severity} · recurrence ${alert.recurrence_count} · escalation ${alert.escalation_level}`}</span>
                      <span>{formatRelativeDuration(alert.last_seen_at)} ago</span>
                    </div>
                    <div className="risk-alert-card__meta">
                      <span>{`Intents ${alert.related_intent_ids.length} · Cycles ${alert.related_cycle_ids.length} · Executions ${alert.related_execution_ids.length}`}</span>
                    </div>
                    {alert.state !== "RESOLVED" ? (
                      <div className="console-inline-actions">
                        {alert.state === "OPEN" ? (
                          <button type="button" className="console-button console-button--ghost" disabled={isPending} onClick={() => void mutateAlert(alert.id, "acknowledge")}>
                            Acknowledge
                          </button>
                        ) : null}
                        <button type="button" className="console-button" disabled={isPending} onClick={() => void mutateAlert(alert.id, "resolve")}>
                          Resolve
                        </button>
                      </div>
                    ) : null}
                  </article>
                ))}
                {!filteredAlerts.length ? (
                  <div className={alertsUnavailable ? "console-empty" : "console-empty console-empty--positive"}>
                    {alertsUnavailable ? "Allocation alerts unavailable." : "No alerts match the current filters."}
                  </div>
                ) : null}
              </div>
            </Panel>

            <Panel title="Risk Truth" subtitle="Estimated vs submitted vs filled vs live-position risk, with confidence made explicit." priority="secondary" tone={intentsUnavailable || exposureUnavailable ? "negative" : summary.truthMix.degraded > 0 ? "negative" : summary.truthMix.provisional > 0 || summary.truthMix.estimated > 0 ? "warning" : "positive"}>
              <CompactTable
                rows={intents.slice(0, 10)}
                emptyLabel={intentsUnavailable ? "Risk truth unavailable." : "No allocation intents available."}
                getRowTone={(row) => truthConfidenceMeta(row.position?.risk_truth_confidence ?? row.risk_truth_confidence).tone}
                columns={[
                  {
                    key: "intent",
                    header: "Intent",
                    render: (row) => (
                      <div className="cell-stack">
                        <strong>{formatInstrumentLabel(row.instrument)}</strong>
                        <span className="console-subtle">{row.family_name ?? row.strategy_name}</span>
                      </div>
                    ),
                  },
                  {
                    key: "confidence",
                    header: "Truth",
                    render: (row) => {
                      const meta = truthConfidenceMeta(row.position?.risk_truth_confidence ?? row.risk_truth_confidence);
                      return <StatusPill label={meta.label} tone={meta.tone} title={meta.detail} />;
                    },
                  },
                  {
                    key: "risk-stages",
                    header: "Risk Stages",
                    render: (row) => {
                      const estimated = row.estimated_risk_amount != null ? formatCurrency(row.estimated_risk_amount) : "n/a";
                      const submitted = row.submitted_risk_amount != null ? formatCurrency(row.submitted_risk_amount) : "n/a";
                      const filled = row.fill_derived_risk_amount != null ? formatCurrency(row.fill_derived_risk_amount) : "n/a";
                      return `${estimated} / ${submitted} / ${filled}`;
                    },
                  },
                  {
                    key: "execution",
                    header: "Execution Truth",
                    render: (row) => {
                      const execution = row.latest_execution;
                      if (!execution) {
                        return "No execution";
                      }
                      return execution.average_fill_price != null
                        ? `${formatPrice(execution.average_fill_price, row.instrument)} · ${execution.filled_size ?? execution.requested_size ?? 0}`
                        : execution.status.replaceAll("_", " ");
                    },
                  },
                ]}
              />
            </Panel>

            <Panel title="Live Exposure Hotspots" subtitle="Which books are closest to their current risk budget." priority="passive" tone={summary.topHotspot ? budgetTone(summary.topHotspot.utilization_percent) : "neutral"}>
              <div className="risk-group-grid">
                <div className="risk-group-card">
                  <span>Strategy pressure</span>
                  {topStrategies.slice(0, 4).map((bucket) => (
                    <strong key={bucket.name}>{`${bucket.name}: ${formatPercent(bucket.total_risk_percent)} (${formatPercent(bucket.utilization_percent ?? 0)})`}</strong>
                  ))}
                </div>
                <div className="risk-group-card">
                  <span>Instrument pressure</span>
                  {topInstruments.slice(0, 4).map((bucket) => (
                    <strong key={bucket.name}>{`${formatInstrumentLabel(bucket.name)}: ${formatPercent(bucket.total_risk_percent)} (${formatPercent(bucket.utilization_percent ?? 0)})`}</strong>
                  ))}
                </div>
              </div>
            </Panel>
          </>
        )}
      />
    </main>
  );
}
