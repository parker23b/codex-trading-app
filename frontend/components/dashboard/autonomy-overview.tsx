"use client";

import Link from "next/link";

import { Card } from "@/components/ui/card";
import { BrokerAuthStatus, ControlPlaneSummary, StreamHealthStatus } from "@/lib/types";

type AutonomyOverviewProps = {
  summary: ControlPlaneSummary;
  brokerAuth: BrokerAuthStatus;
  streamHealth: StreamHealthStatus;
  activeRuntimeCount: number;
  positionCount: number;
};

function buildNarrative(summary: ControlPlaneSummary, streamHealth: StreamHealthStatus, brokerAuth: BrokerAuthStatus) {
  const blockedOrDegraded = (summary.counts.BLOCKED ?? 0) + (summary.counts.DEGRADED ?? 0);
  const openRiskState = summary.open_risk_management_state ?? "UNAVAILABLE";

  if (openRiskState === "UNMANAGED_OPEN_RISK") {
    return "Open positions are present without active automated exit management. Treat this as a control-plane priority ahead of generic autonomy or deployment labels.";
  }
  if (openRiskState === "EXITS_ONLY") {
    return "Open risk is still under automated management, but only for exits. New entries are intentionally suppressed while the runtime protects existing positions.";
  }
  if (openRiskState === "UNAVAILABLE" || openRiskState === "UNKNOWN") {
    return "Open-risk management state is unavailable. Treat risk status as unverified until backend control-plane truth is loaded.";
  }
  if (!summary.effective_autonomous_control_enabled) {
    return "Autonomy is authorized off. The system can still observe and reconcile state, but it is not permitted to auto-deploy new strategy families.";
  }
  if ((summary.counts.EMERGENCY_STOPPED ?? 0) > 0) {
    return "Emergency-stopped families are present. Review control-plane exceptions before assuming automated control can resume normally.";
  }
  if (summary.misaligned_count > 0) {
    return "The system is running, but intent and runtime truth are misaligned for at least one strategy family.";
  }
  if (summary.entry_eligible === false && summary.exit_eligible) {
    return "Autonomy is authorized, but new entries are blocked by current operating conditions while exits remain eligible.";
  }
  if (summary.entry_eligible === false) {
    return "Autonomy is authorized, but execution is currently blocked by feed, broker, or freshness constraints.";
  }
  if (blockedOrDegraded > 0) {
    return "Autonomy is authorized, but some families are blocked or degraded by suitability, governance, or runtime conditions.";
  }
  if (!streamHealth.connected || brokerAuth.state !== "connected") {
    return "External dependencies are degraded. Permission to operate remains on, but execution readiness is reduced until stream and broker health recover.";
  }
  return "Autonomy is authorized and execution conditions currently support normal governed operation.";
}

export function AutonomyOverview({
  summary,
  brokerAuth,
  streamHealth,
  activeRuntimeCount,
  positionCount,
}: AutonomyOverviewProps) {
  const blockedOrDegraded = (summary.counts.BLOCKED ?? 0) + (summary.counts.DEGRADED ?? 0);
  const openRiskState = summary.open_risk_management_state ?? "UNAVAILABLE";
  const narrative = buildNarrative(summary, streamHealth, brokerAuth);

  return (
    <Card
      title="Autonomy Snapshot"
      subtitle="What the system is doing now, whether that is normal, and where to inspect exceptions."
      className="card--compact autonomy-overview board-surface board-surface--hero"
      action={
        <div className="card-header__actions">
          <Link href="/control-plane" className="nav-link">
            Control Plane
          </Link>
          <Link href="/coverage" className="nav-link">
            Coverage
          </Link>
        </div>
      }
    >
      <div className="summary-grid">
        <div className="summary-grid__item">
          <span className="eyebrow">Permission</span>
          <strong>{summary.effective_autonomous_control_enabled ? "Authorized" : "Paused"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Entries</span>
          <strong>{summary.entry_eligible ? "Allowed" : "Blocked"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Exits</span>
          <strong>{summary.exit_eligible ? "Allowed" : "Blocked"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Open Risk</span>
          <strong>{openRiskState}</strong>
        </div>
      </div>

      <div className="status-note status-note--inline">{narrative}</div>

      <div className="autonomy-overview__checks">
        <div className="status-note status-note--inline">
          Live runtimes: {activeRuntimeCount} · Open positions: {positionCount}
        </div>
        <div className="status-note status-note--inline">
          Broker: {summary.broker_connectivity_state ?? brokerAuth.label} · {brokerAuth.detail}
        </div>
        <div className="status-note status-note--inline">
          Feed: {summary.feed_source_state ?? (streamHealth.connected ? "LIVE" : "DISCONNECTED")} · {streamHealth.last_status ?? "status unavailable"}
        </div>
        <div className="status-note status-note--inline">
          Families aligned: {summary.families.filter((family) => family.alignment.status === "ALIGNED").length}/{summary.families.length} · Exceptions: {summary.misaligned_count + blockedOrDegraded + (summary.counts.EMERGENCY_STOPPED ?? 0)}
        </div>
      </div>
    </Card>
  );
}
