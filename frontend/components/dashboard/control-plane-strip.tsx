"use client";

import Link from "next/link";

import { Card } from "@/components/ui/card";
import { ControlPlaneSummary } from "@/lib/types";

type ControlPlaneStripProps = {
  summary: ControlPlaneSummary;
};

function formatTime(value?: string | null) {
  if (!value) {
    return "n/a";
  }
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  }).format(new Date(value));
}

export function ControlPlaneStrip({ summary }: ControlPlaneStripProps) {
  const mismatches = summary.families.filter((family) => family.alignment.status === "MISMATCH").slice(0, 4);
  const stressedFamilies = summary.families
    .filter((family) => {
      const state = family.deployment?.state;
      return state === "BLOCKED" || state === "DEGRADED" || state === "EMERGENCY_STOPPED";
    })
    .slice(0, 4);
  const recentRestarts = summary.families
    .filter((family) => family.deployment?.last_restart_reason)
    .sort((left, right) => {
      const leftTime = new Date(left.deployment?.updated_at ?? 0).getTime();
      const rightTime = new Date(right.deployment?.updated_at ?? 0).getTime();
      return rightTime - leftTime;
    })
    .slice(0, 3);
  const recentProfileChanges = summary.families
    .filter((family) => family.deployment?.profile_change_reason)
    .sort((left, right) => {
      const leftTime = new Date(left.deployment?.profile_selected_at ?? 0).getTime();
      const rightTime = new Date(right.deployment?.profile_selected_at ?? 0).getTime();
      return rightTime - leftTime;
    })
    .slice(0, 3);

  return (
    <Card
      title="Autonomy Exceptions"
      subtitle="Only the exception path lives here on the dashboard. Use the control plane for deeper inspection and guarded intervention."
      className="board-surface board-surface--primary"
      action={<Link href="/control-plane" className="nav-link">Open Control Plane</Link>}
    >
      <div className="summary-grid">
        <div className="summary-grid__item">
          <span className="eyebrow">Autonomy</span>
          <strong>{summary.effective_autonomous_control_enabled ? "enabled" : "disabled"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Aligned</span>
          <strong>{summary.families.filter((family) => family.alignment.status === "ALIGNED").length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Mismatch</span>
          <strong>{summary.misaligned_count}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Blocked / Degraded</span>
          <strong>{(summary.counts.BLOCKED ?? 0) + (summary.counts.DEGRADED ?? 0)}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Auto Deployed</span>
          <strong>{summary.counts.AUTO_DEPLOYED ?? 0}</strong>
        </div>
        {(summary.counts.EMERGENCY_STOPPED ?? 0) > 0 ? (
          <div className="summary-grid__item">
            <span className="eyebrow">Emergency Stopped</span>
            <strong>{summary.counts.EMERGENCY_STOPPED}</strong>
          </div>
        ) : null}
      </div>

      <section className="review-panel__split">
        <div>
          <div className="review-panel__label">Needs Attention</div>
          <div className="review-stack">
            {!summary.effective_autonomous_control_enabled ? (
              <div className="status-note status-note--inline">
                Global autonomy is disabled, so the system is not auto-deploying strategy families.
              </div>
            ) : null}
            {mismatches.length ? mismatches.map((family) => (
              <div className="status-note status-note--inline" key={`mismatch-${family.strategy_name}`}>
                {family.strategy_name} · mismatch · {family.alignment.reason}
              </div>
            )) : null}
            {stressedFamilies.length ? stressedFamilies.map((family) => (
              <div className="status-note status-note--inline" key={`stress-${family.strategy_name}`}>
                {family.strategy_name} · {family.deployment?.state?.toLowerCase() ?? "unknown"} · {family.deployment?.blocked_reason ?? family.deployment?.degraded_reason ?? family.deployment?.suitability_reason ?? "state transition recorded"}
              </div>
            )) : null}
            {!mismatches.length && !stressedFamilies.length ? (
              <div className="status-note status-note--inline">No current control-plane exceptions are visible.</div>
            ) : null}
          </div>
        </div>
        <div>
          <div className="review-panel__label">Recent Autonomous Changes</div>
          <div className="review-stack">
            {recentRestarts.map((family) => (
              <div className="status-note status-note--inline" key={`restart-${family.strategy_name}`}>
                {family.strategy_name} · restart · {family.deployment?.last_restart_reason} · {formatTime(family.deployment?.updated_at)}
              </div>
            ))}
            {recentProfileChanges.map((family) => (
              <div className="status-note status-note--inline" key={`profile-${family.strategy_name}`}>
                {family.strategy_name} · profile {family.deployment?.selected_profile ?? "n/a"} · {family.deployment?.profile_change_reason} · {formatTime(family.deployment?.profile_selected_at)}
              </div>
            ))}
            {!recentRestarts.length && !recentProfileChanges.length ? (
              <div className="status-note status-note--inline">No recent autonomous restarts or profile changes recorded.</div>
            ) : null}
          </div>
        </div>
      </section>
    </Card>
  );
}
