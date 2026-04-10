"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import { getControlPlaneSummary, updateOperatorControlState, updateStrategyGovernance } from "@/lib/api";
import { ControlPlaneFamily, ControlPlaneSummary } from "@/lib/types";

type ControlPlaneLiveProps = {
  initialSummary: ControlPlaneSummary;
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

function needsAttention(summary: ControlPlaneSummary, family: ControlPlaneFamily) {
  const state = family.deployment?.state;
  return (
    !summary.effective_autonomous_control_enabled ||
    family.alignment.status !== "ALIGNED" ||
    family.governance.emergency_stop ||
    state === "BLOCKED" ||
    state === "DEGRADED" ||
    state === "EMERGENCY_STOPPED"
  );
}

export function ControlPlaneLive({ initialSummary }: ControlPlaneLiveProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [pendingGlobalAction, setPendingGlobalAction] = useState<"enable" | "disable" | null>(null);
  const [pendingFamily, setPendingFamily] = useState<string | null>(null);

  useEffect(() => {
    setSummary(initialSummary);
  }, [initialSummary]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const nextSummary = await getControlPlaneSummary();
        if (cancelled) {
          return;
        }
        setSummary(nextSummary);
      } catch {
        // Keep last good snapshot.
      }
    };
    const intervalId = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const refreshSummary = async () => {
    const nextSummary = await getControlPlaneSummary();
    setSummary(nextSummary);
  };

  const handleGlobalAutonomy = async (enabled: boolean) => {
    try {
      setPendingGlobalAction(enabled ? "enable" : "disable");
      await updateOperatorControlState({
        autonomous_control_enabled: enabled,
        reason: enabled ? "Operator armed governed autonomy from control-plane UI." : "Operator paused governed autonomy from control-plane UI.",
      });
      await refreshSummary();
    } finally {
      setPendingGlobalAction(null);
    }
  };

  const handleFamilyAutonomy = async (strategyName: string, enabled: boolean) => {
    try {
      setPendingFamily(strategyName);
      await updateStrategyGovernance(strategyName, {
        autonomous_operation_allowed: enabled,
      });
      await refreshSummary();
    } finally {
      setPendingFamily(null);
    }
  };

  const exceptionFamilies = summary.families.filter((family) => needsAttention(summary, family));
  const stableFamilies = summary.families.filter((family) => !needsAttention(summary, family));

  return (
    <main className="page-grid">
      <Card title="Control Plane Oversight" subtitle="Exception-first view of governed autonomy, with intervention kept secondary to context and reasoning.">
        <div className="summary-grid">
          <div className="summary-grid__item">
            <span className="eyebrow">Autonomy</span>
            <strong>{summary.effective_autonomous_control_enabled ? "enabled" : "disabled"}</strong>
          </div>
          <div className="summary-grid__item">
            <span className="eyebrow">Families</span>
            <strong>{summary.families.length}</strong>
          </div>
          <div className="summary-grid__item">
            <span className="eyebrow">Needs Attention</span>
            <strong>{exceptionFamilies.length}</strong>
          </div>
          <div className="summary-grid__item">
            <span className="eyebrow">Auto Deployed</span>
            <strong>{summary.counts.AUTO_DEPLOYED ?? 0}</strong>
          </div>
        </div>
        <div className="review-stack">
          <div className="status-note status-note--inline">
            Use this page to understand why autonomous behavior is normal or abnormal before deciding whether human intervention is justified.
          </div>
          <div className="status-note status-note--inline">
            Configured autonomy: {summary.configured_autonomous_control_enabled ? "enabled" : "disabled"} · effective autonomy: {summary.effective_autonomous_control_enabled ? "enabled" : "disabled"}{summary.autonomy_override_active ? ` · operator override ${summary.autonomy_override_value ? "enabled" : "disabled"}` : ""}
          </div>
          {summary.autonomy_override_reason ? (
            <div className="status-note status-note--inline">
              Override reason: {summary.autonomy_override_reason}
            </div>
          ) : null}
          <div className="review-panel__actions">
            <button
              type="button"
              className="button"
              disabled={pendingGlobalAction !== null || summary.effective_autonomous_control_enabled}
              onClick={() => handleGlobalAutonomy(true)}
            >
              {pendingGlobalAction === "enable" ? "Enabling..." : "Enable Autonomy"}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={pendingGlobalAction !== null || !summary.effective_autonomous_control_enabled}
              onClick={() => handleGlobalAutonomy(false)}
            >
              {pendingGlobalAction === "disable" ? "Disabling..." : "Disable Autonomy"}
            </button>
          </div>
        </div>
      </Card>

      <Card title="Attention Queue" subtitle="Families that are blocked, degraded, misaligned, emergency stopped, or otherwise need explanation.">
        {exceptionFamilies.length ? (
          <div className="control-plane-family-list">
            {exceptionFamilies.map((family) => {
              const deployment = family.deployment;
              const runtime = family.runtime;
              const alignment = family.alignment;
              const operatorReason =
                deployment?.blocked_reason ||
                deployment?.degraded_reason ||
                deployment?.suitability_reason ||
                alignment.reason;

              return (
                <details key={family.strategy_name} className="control-plane-family" open={family.alignment.status !== "ALIGNED"}>
                  <summary className="control-plane-family__summary">
                    <div className="cell-stack">
                      <strong>{family.strategy_name}</strong>
                      <span className="muted">{family.description}</span>
                    </div>
                    <div className="control-plane-family__badges">
                      <span className="status-badge warning">{deployment?.state ?? "UNASSIGNED"}</span>
                      <span className={`status-badge ${alignment.status === "ALIGNED" ? "positive" : "warning"}`}>{alignment.status}</span>
                    </div>
                  </summary>

                  <div className="control-plane-family__body">
                    <section className="review-panel__split">
                      <div>
                        <div className="review-panel__label">Observed State</div>
                        <div className="review-stack">
                          <div className="status-note status-note--inline">Governance: {family.governance.approval_state}</div>
                          <div className="status-note status-note--inline">Deployment: {deployment?.state ?? "UNASSIGNED"}</div>
                          <div className="status-note status-note--inline">Runtime: {runtime.is_running ? `${runtime.control_mode ?? "UNKNOWN"} running` : "not running"}</div>
                          <div className="status-note status-note--inline">Selected intent: {deployment?.selected_instrument ?? "n/a"} · {deployment?.selected_profile ?? "n/a"}</div>
                          <div className="status-note status-note--inline">Runtime truth: {runtime.active_instrument ?? "n/a"} · {runtime.active_profile_name ?? "n/a"}</div>
                        </div>
                      </div>
                      <div>
                        <div className="review-panel__label">Why It Needs Attention</div>
                        <div className="review-stack">
                          <div className="status-note status-note--inline">Alignment: {alignment.reason}</div>
                          <div className="status-note status-note--inline">Deployment reason: {operatorReason ?? "n/a"}</div>
                          <div className="status-note status-note--inline">Last restart reason: {deployment?.last_restart_reason ?? "n/a"}</div>
                          <div className="status-note status-note--inline">Last evaluated: {formatTime(deployment?.last_evaluated_at)}</div>
                        </div>
                      </div>
                    </section>

                    {alignment.checks.length ? (
                      <section className="review-panel__section">
                        <div className="review-panel__label">Alignment Checks</div>
                        <div className="review-stack">
                          {alignment.checks.map((check) => (
                            <div className="status-note status-note--inline" key={`${family.strategy_name}-${check.code}`}>
                              {check.code} · {check.passed ? "pass" : "fail"}
                              {"expected" in check && check.expected !== undefined ? ` · expected ${JSON.stringify(check.expected)}` : ""}
                              {"actual" in check && check.actual !== undefined ? ` · actual ${JSON.stringify(check.actual)}` : ""}
                            </div>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    <section className="review-panel__section">
                      <div className="review-panel__label">Guarded Intervention</div>
                      <div className="review-stack">
                        <div className="status-note status-note--inline">
                          Intervene only if the family is persistently blocked, misaligned, or unsafe and the autonomous system is unlikely to recover by itself.
                        </div>
                        <div className="review-panel__actions">
                          <button
                            type="button"
                            className="button"
                            disabled={pendingFamily === family.strategy_name || family.governance.autonomous_operation_allowed}
                            onClick={() => handleFamilyAutonomy(family.strategy_name, true)}
                          >
                            {pendingFamily === family.strategy_name && !family.governance.autonomous_operation_allowed ? "Updating..." : "Allow Autonomous Deployment"}
                          </button>
                          <button
                            type="button"
                            className="button secondary"
                            disabled={pendingFamily === family.strategy_name || !family.governance.autonomous_operation_allowed}
                            onClick={() => handleFamilyAutonomy(family.strategy_name, false)}
                          >
                            {pendingFamily === family.strategy_name && family.governance.autonomous_operation_allowed ? "Updating..." : "Disallow Autonomous Deployment"}
                          </button>
                        </div>
                      </div>
                    </section>

                    <section className="review-panel__section">
                      <div className="review-panel__label">Recent Lifecycle Events</div>
                      <div className="review-stack">
                        {family.recent_events.length ? (
                          family.recent_events.map((event) => (
                            <div className="status-note status-note--inline" key={`${family.strategy_name}-${event.id ?? event.created_at}`}>
                              {formatTime(event.created_at)} · {event.event_type} · {event.title}
                              {event.message ? ` · ${event.message}` : ""}
                            </div>
                          ))
                        ) : (
                          <div className="status-note status-note--inline">No recent lifecycle events recorded for this family.</div>
                        )}
                      </div>
                    </section>
                  </div>
                </details>
              );
            })}
          </div>
        ) : (
          <div className="status-note status-note--inline">No families currently require intervention. Autonomous behavior appears aligned with governance and runtime truth.</div>
        )}
      </Card>

      <Card title="Stable Families" subtitle="Healthy families remain visible, but collapsed so the page prioritizes anomalies over routine autonomous behavior.">
        {stableFamilies.length ? (
          <div className="control-plane-family-list">
            {stableFamilies.map((family) => (
              <details key={family.strategy_name} className="control-plane-family">
                <summary className="control-plane-family__summary">
                  <div className="cell-stack">
                    <strong>{family.strategy_name}</strong>
                    <span className="muted">{family.description}</span>
                  </div>
                  <div className="control-plane-family__badges">
                    <span className="status-badge positive">{family.deployment?.state ?? "UNASSIGNED"}</span>
                    <span className="status-badge positive">{family.alignment.status}</span>
                  </div>
                </summary>
                <div className="control-plane-family__body">
                  <div className="review-stack">
                    <div className="status-note status-note--inline">Selected intent: {family.deployment?.selected_instrument ?? "n/a"} · {family.deployment?.selected_profile ?? "n/a"}</div>
                    <div className="status-note status-note--inline">Runtime truth: {family.runtime.active_instrument ?? "n/a"} · {family.runtime.active_profile_name ?? "n/a"}</div>
                    <div className="status-note status-note--inline">Last evaluated: {formatTime(family.deployment?.last_evaluated_at)}</div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="status-note status-note--inline">No stable families are visible right now.</div>
        )}
      </Card>
    </main>
  );
}
