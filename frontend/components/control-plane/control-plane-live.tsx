"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import { getControlPlaneSummary, updateOperatorControlState, updateStrategyGovernance } from "@/lib/api";
import { ControlPlaneSummary } from "@/lib/types";

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

  return (
    <main className="page-grid">
      <Card title="Control Plane" subtitle="Governance, deployment intent, active runtime truth, and whether the autonomous system is actually aligned.">
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
            <span className="eyebrow">Misaligned</span>
            <strong>{summary.misaligned_count}</strong>
          </div>
          <div className="summary-grid__item">
            <span className="eyebrow">Auto Deployed</span>
            <strong>{summary.counts.AUTO_DEPLOYED ?? 0}</strong>
          </div>
        </div>
        <div className="review-stack">
          <div className="status-note status-note--inline">
            This view shows governance approval, deployment target, active runtime truth, and explicit alignment checks for each strategy family.
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

      {summary.families.map((family) => {
        const deployment = family.deployment;
        const runtime = family.runtime;
        const alignment = family.alignment;
        const operatorReason =
          deployment?.blocked_reason ||
          deployment?.degraded_reason ||
          deployment?.suitability_reason ||
          alignment.reason;

        return (
          <Card
            key={family.strategy_name}
            title={family.strategy_name}
            subtitle={family.description}
          >
            <div className="summary-grid">
              <div className="summary-grid__item">
                <span className="eyebrow">Governance</span>
                <strong>{family.governance.approval_state}</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Deployment</span>
                <strong>{deployment?.state ?? "UNASSIGNED"}</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Runtime</span>
                <strong>{runtime.is_running ? `${runtime.control_mode ?? "UNKNOWN"} running` : "not running"}</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Alignment</span>
                <strong>{alignment.status}</strong>
              </div>
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

            <section className="review-panel__split">
              <div>
                <div className="review-panel__label">Selected Intent</div>
                <div className="review-stack">
                  <div className="status-note status-note--inline">Instrument: {deployment?.selected_instrument ?? "n/a"}</div>
                  <div className="status-note status-note--inline">Profile: {deployment?.selected_profile ?? "n/a"}</div>
                  <div className="status-note status-note--inline">
                    Parameters: {Object.keys(deployment?.selected_profile_parameters ?? {}).length ? JSON.stringify(deployment?.selected_profile_parameters) : "n/a"}
                  </div>
                  <div className="status-note status-note--inline">Profile selected: {formatTime(deployment?.profile_selected_at)}</div>
                  <div className="status-note status-note--inline">Profile change reason: {deployment?.profile_change_reason ?? "n/a"}</div>
                </div>
              </div>
              <div>
                <div className="review-panel__label">Runtime Truth</div>
                <div className="review-stack">
                  <div className="status-note status-note--inline">Instrument: {runtime.active_instrument ?? "n/a"}</div>
                  <div className="status-note status-note--inline">Profile: {runtime.active_profile_name ?? "n/a"}</div>
                  <div className="status-note status-note--inline">
                    Parameters: {Object.keys(runtime.active_parameters ?? {}).length ? JSON.stringify(runtime.active_parameters) : "n/a"}
                  </div>
                  <div className="status-note status-note--inline">Recovery state: {runtime.recovery_state ?? "n/a"}</div>
                  <div className="status-note status-note--inline">Runtime updated: {formatTime(runtime.updated_at)}</div>
                </div>
              </div>
            </section>

            <section className="review-panel__section">
              <div className="review-panel__label">Operational Reasoning</div>
              <div className="review-stack">
                <div className="status-note status-note--inline">Alignment: {alignment.reason}</div>
                <div className="status-note status-note--inline">Deployment reason: {operatorReason ?? "n/a"}</div>
                <div className="status-note status-note--inline">Last restart reason: {deployment?.last_restart_reason ?? "n/a"}</div>
                <div className="status-note status-note--inline">Last evaluated: {formatTime(deployment?.last_evaluated_at)}</div>
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
          </Card>
        );
      })}
    </main>
  );
}
