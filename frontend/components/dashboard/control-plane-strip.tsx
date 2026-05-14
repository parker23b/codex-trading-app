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
  const openRiskState = summary.open_risk_management_state ?? "UNAVAILABLE";
  const openRiskUnavailable = openRiskState === "UNAVAILABLE" || openRiskState === "UNKNOWN";
  const openRiskFamilies = summary.families
    .filter((family) => family.deployment?.open_risk_management_state === "UNMANAGED_OPEN_RISK")
    .slice(0, 4);
  const exitsOnlyFamilies = summary.families
    .filter((family) => family.deployment?.open_risk_management_state === "EXITS_ONLY")
    .slice(0, 4);
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
      title="Control-Plane Exceptions"
      subtitle="Permission, execution eligibility, and open-risk management are shown separately so deployment state is not mistaken for trading readiness."
      className="board-surface board-surface--primary"
      action={<Link href="/control-plane" className="nav-link">Open Control Plane</Link>}
    >
      <div className="summary-grid">
        <div className="summary-grid__item">
          <span className="eyebrow">Permission</span>
          <strong>{summary.effective_autonomous_control_enabled ? "authorized" : "paused"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Entries</span>
          <strong>{summary.entry_eligible ? "allowed" : "blocked"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Exits</span>
          <strong>{summary.exit_eligible ? "allowed" : "blocked"}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Open Risk</span>
          <strong>{openRiskState}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Full AUTO</span>
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
                Autonomy permission is paused, so the system is not permitted to auto-deploy strategy families.
              </div>
            ) : null}
            {summary.entry_eligible === false ? (
              <div className="status-note status-note--inline">
                New entries are blocked{summary.entry_block_reason ? ` · ${summary.entry_block_reason.replaceAll("_", " ")}` : ""}.
              </div>
            ) : null}
            {summary.exit_eligible === false ? (
              <div className="status-note status-note--inline">
                Exits are blocked{summary.exit_block_reason ? ` · ${summary.exit_block_reason.replaceAll("_", " ")}` : ""}.
              </div>
            ) : null}
            {openRiskUnavailable ? (
              <div className="status-note status-note--inline">
                Open-risk management state is unavailable; do not treat this summary as no open risk.
              </div>
            ) : null}
            {openRiskFamilies.length ? openRiskFamilies.map((family) => (
              <div className="status-note status-note--inline" key={`open-risk-${family.strategy_name}`}>
                {family.strategy_name} · unmanaged open risk · {family.deployment?.open_risk_management_reason ?? "positions are no longer under active automated exit management"}
              </div>
            )) : null}
            {exitsOnlyFamilies.length ? exitsOnlyFamilies.map((family) => (
              <div className="status-note status-note--inline" key={`exits-only-${family.strategy_name}`}>
                {family.strategy_name} · exits only · {family.deployment?.open_risk_management_reason ?? "new entries suppressed while existing positions remain managed"}
              </div>
            )) : null}
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
            {!mismatches.length && !stressedFamilies.length && !openRiskFamilies.length && !exitsOnlyFamilies.length && !openRiskUnavailable && summary.entry_eligible !== false && summary.exit_eligible !== false ? (
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
