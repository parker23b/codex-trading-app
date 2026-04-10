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

  if (!summary.effective_autonomous_control_enabled) {
    return "Autonomous deployment is paused. The system can observe state, but it is not auto-deploying new strategy families.";
  }
  if ((summary.counts.EMERGENCY_STOPPED ?? 0) > 0) {
    return "Emergency-stopped families are present. Review control-plane exceptions before trusting automated deployment to resume normally.";
  }
  if (summary.misaligned_count > 0) {
    return "The system is running, but intent and runtime truth are misaligned for at least one strategy family.";
  }
  if (blockedOrDegraded > 0) {
    return "Autonomy is enabled, but some families are blocked or degraded by suitability, governance, or runtime conditions.";
  }
  if (!streamHealth.connected || brokerAuth.state !== "connected") {
    return "Autonomy is armed, but external dependencies are degraded. Deployment confidence is reduced until stream and broker health recover.";
  }
  return "Autonomy is enabled and the system is scanning and deploying within current governance, market, and health constraints.";
}

export function AutonomyOverview({
  summary,
  brokerAuth,
  streamHealth,
  activeRuntimeCount,
  positionCount,
}: AutonomyOverviewProps) {
  const blockedOrDegraded = (summary.counts.BLOCKED ?? 0) + (summary.counts.DEGRADED ?? 0);
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
          <span className="eyebrow">Autonomy</span>
          <strong>{summary.effective_autonomous_control_enabled ? "Enabled" : "Paused"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Live Runtimes</span>
          <strong>{activeRuntimeCount}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Open Positions</span>
          <strong>{positionCount}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Exceptions</span>
          <strong>{summary.misaligned_count + blockedOrDegraded + (summary.counts.EMERGENCY_STOPPED ?? 0)}</strong>
        </div>
      </div>

      <div className="status-note status-note--inline">{narrative}</div>

      <div className="autonomy-overview__checks">
        <div className="status-note status-note--inline">
          Broker: {brokerAuth.label} · {brokerAuth.detail}
        </div>
        <div className="status-note status-note--inline">
          Stream: {streamHealth.connected ? "connected" : "disconnected"} · {streamHealth.last_status ?? "status unavailable"}
        </div>
        <div className="status-note status-note--inline">
          Families aligned: {summary.families.filter((family) => family.alignment.status === "ALIGNED").length}/{summary.families.length}
        </div>
        <div className="status-note status-note--inline">
          Blocked or degraded: {blockedOrDegraded} · Emergency stopped: {summary.counts.EMERGENCY_STOPPED ?? 0}
        </div>
      </div>
    </Card>
  );
}
