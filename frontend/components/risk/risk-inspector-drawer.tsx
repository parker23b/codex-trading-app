"use client";

import { InspectorDrawer, StatusPill } from "@/components/console/primitives";
import {
  alertSeverityTone,
  buildRiskConsoleSummary,
  formatDirectionalBias,
  formatHotspotLabel,
  truthConfidenceMeta,
} from "@/lib/risk-allocation";
import { formatDateTime, formatInstrumentLabel, formatPercent } from "@/lib/format";
import {
  AllocationAlert,
  AllocationCycle,
  AllocationDriftSummary,
  AllocationExposureSummary,
  AllocationIntent,
} from "@/lib/types";

type RiskInspectorDrawerProps = {
  open: boolean;
  onClose: () => void;
  exposure: AllocationExposureSummary;
  alerts: AllocationAlert[];
  drift: AllocationDriftSummary;
  cycles: AllocationCycle[];
  intents: AllocationIntent[];
};

export function RiskInspectorDrawer({
  open,
  onClose,
  exposure,
  alerts,
  drift,
  cycles,
  intents,
}: RiskInspectorDrawerProps) {
  const summary = buildRiskConsoleSummary({ exposure, alerts, drift, cycles, intents });
  const activeAlerts = alerts.filter((alert) => alert.state !== "RESOLVED").slice(0, 5);
  const lastCycle = cycles[0];
  const topDrift = drift.worst_intents[0];
  const recentTruth = intents
    .filter((intent) => intent.position?.is_open || intent.state === "PARTIALLY_FILLED")
    .slice(0, 4);

  return (
    <InspectorDrawer
      title="Risk / Allocation Briefing"
      subtitle="A quick operational briefing: what is risky now, what is constrained, and what deserves intervention."
      open={open}
      onClose={onClose}
    >
      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">Now</span>
          <StatusPill
            label={summary.criticalAlertCount > 0 ? "Action needed" : summary.degradedSizingOrTruth ? "Watch closely" : "Nominal"}
            tone={summary.criticalAlertCount > 0 ? "negative" : summary.degradedSizingOrTruth ? "warning" : "positive"}
          />
        </div>
        <div className="risk-briefing-grid">
          {summary.metrics.slice(0, 4).map((metric) => (
            <div key={metric.label} className={`risk-briefing-card risk-briefing-card--${metric.tone}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <em>{metric.meta}</em>
            </div>
          ))}
        </div>
      </section>

      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">Hotspots</span>
        </div>
        <div className="metric-stack">
          <div className="metric-stack__row">
            <span>Top concentration issue</span>
            <strong>{formatHotspotLabel(summary.topHotspot)}</strong>
          </div>
          <div className="metric-stack__row">
            <span>Budget pressure</span>
            <strong>{summary.lastCycleStatus.meta}</strong>
          </div>
          <div className="metric-stack__row">
            <span>Directional bias</span>
            <strong>{formatDirectionalBias(summary.dominantNetCurrency)}</strong>
          </div>
        </div>
      </section>

      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">Last cycle</span>
          {lastCycle ? <StatusPill label={summary.lastCycleStatus.label} tone={summary.lastCycleStatus.tone} /> : null}
        </div>
        {lastCycle ? (
          <div className="risk-briefing-grid risk-briefing-grid--compact">
            <div className="risk-briefing-card">
              <span>Candidates / approved / rejected</span>
              <strong>{`${lastCycle.candidate_count} / ${lastCycle.approved_count} / ${lastCycle.rejected_count}`}</strong>
              <em>{formatDateTime(lastCycle.completed_at)}</em>
            </div>
            <div className="risk-briefing-card">
              <span>Binding constraint</span>
              <strong>{Object.entries(lastCycle.binding_budget_counts ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "none"}</strong>
              <em>Most frequent constraint in the cycle</em>
            </div>
            <div className="risk-briefing-card">
              <span>Blocked reasons</span>
              <strong>
                {lastCycle.blocked_budget_count > 0
                  ? "Budget"
                  : lastCycle.blocked_conflict_count > 0
                    ? "Conflict"
                    : lastCycle.blocked_under_minimum_size_count > 0
                      ? "Under minimum"
                      : "None dominant"}
              </strong>
              <em>{`${lastCycle.blocked_budget_count + lastCycle.blocked_conflict_count + lastCycle.blocked_under_minimum_size_count} constrained`}</em>
            </div>
          </div>
        ) : (
          <div className="console-empty">No recent allocation cycle is available.</div>
        )}
      </section>

      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">Current alerts</span>
        </div>
        {activeAlerts.length ? (
          <div className="detail-stack">
            {activeAlerts.map((alert) => (
              <article key={alert.id} className={`risk-alert-mini risk-alert-mini--${alertSeverityTone(alert.severity)}`}>
                <div className="risk-alert-mini__title">
                  <strong>{alert.title}</strong>
                  <StatusPill label={alert.state.toLowerCase()} tone={alertSeverityTone(alert.severity)} />
                </div>
                <p>{alert.message}</p>
                <div className="risk-alert-mini__meta">
                  <span>{`Severity ${alert.severity} · recurrence ${alert.recurrence_count}`}</span>
                  <span>{formatDateTime(alert.last_seen_at)}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="console-empty console-empty--positive">No unresolved allocation alerts.</div>
        )}
      </section>

      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">Truth & drift</span>
        </div>
        <div className="risk-briefing-grid risk-briefing-grid--compact">
          <div className="risk-briefing-card">
            <span>Top drift issue</span>
            <strong>{topDrift ? `${formatInstrumentLabel(topDrift.instrument)} ${formatPercent(topDrift.max_percent_drift)}` : "None"}</strong>
            <em>{topDrift ? `${topDrift.family_name ?? topDrift.strategy_name} · ${topDrift.state}` : "No material execution drift detected."}</em>
          </div>
          <div className="risk-briefing-card">
            <span>Risk truth mix</span>
            <strong>{`${summary.truthMix.exact} exact · ${summary.truthMix.provisional} provisional`}</strong>
            <em>{`${summary.truthMix.estimated} estimated · ${summary.truthMix.degraded} degraded`}</em>
          </div>
        </div>
        {recentTruth.length ? (
          <div className="detail-stack">
            {recentTruth.map((intent) => {
              const confidence = truthConfidenceMeta(intent.position?.risk_truth_confidence ?? intent.risk_truth_confidence);
              return (
                <div key={intent.id} className="metric-stack__row">
                  <span>{`${formatInstrumentLabel(intent.instrument)} · ${intent.family_name ?? intent.strategy_name}`}</span>
                  <strong>{confidence.label}</strong>
                  <em>{confidence.detail}</em>
                </div>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className="risk-briefing-section">
        <div className="risk-briefing-section__header">
          <span className="console-kicker">AIMEE-ready context preview</span>
        </div>
        <pre className="risk-aimee-preview">{JSON.stringify(summary.aimeeContext, null, 2)}</pre>
      </section>
    </InspectorDrawer>
  );
}
