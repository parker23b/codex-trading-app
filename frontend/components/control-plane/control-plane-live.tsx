"use client";

import { useEffect, useMemo, useState } from "react";

import { CompactTable, DataIndicator, Panel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getControlPlaneSummary, updateOperatorControlState, updateStrategyGovernance } from "@/lib/api";
import { ControlPlaneFamily, ControlPlaneSummary } from "@/lib/types";

type ControlPlaneLiveProps = {
  initialSummary: ControlPlaneSummary;
  initialSummaryError: string | null;
};

function formatTime(value?: string | null) {
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

function familyTone(summary: ControlPlaneSummary, family: ControlPlaneFamily) {
  const deploymentState = family.deployment?.state;
  const openRiskState = familyOpenRiskState(family);
  if (openRiskState === "UNMANAGED_OPEN_RISK") {
    return "negative" as const;
  }
  if (familyOpenRiskUnavailable(family)) {
    return "warning" as const;
  }
  if (!summary.effective_autonomous_control_enabled || family.governance.emergency_stop || deploymentState === "BLOCKED" || deploymentState === "EMERGENCY_STOPPED") {
    return "negative" as const;
  }
  if (openRiskState === "EXITS_ONLY") {
    return "warning" as const;
  }
  if (family.alignment.status !== "ALIGNED" || deploymentState === "DEGRADED") {
    return "warning" as const;
  }
  return "positive" as const;
}

function familyOpenRiskState(family: ControlPlaneFamily) {
  return family.deployment?.open_risk_management_state ?? "UNAVAILABLE";
}

function familyOpenRiskUnavailable(family: ControlPlaneFamily) {
  const state = familyOpenRiskState(family);
  return state === "UNAVAILABLE" || state === "UNKNOWN";
}

function familyOpenRiskReason(family: ControlPlaneFamily) {
  if (!familyOpenRiskUnavailable(family)) {
    return family.deployment?.open_risk_management_reason ?? null;
  }
  return family.deployment?.open_risk_management_reason ?? "Open-risk state unavailable; do not treat this family as having no open risk.";
}

function familyOpenRiskLabel(family: ControlPlaneFamily) {
  return familyOpenRiskUnavailable(family) ? "Open-risk state unavailable" : familyOpenRiskState(family);
}

export function ControlPlaneLive({ initialSummary, initialSummaryError }: ControlPlaneLiveProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [summaryError, setSummaryError] = useState(initialSummaryError);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [selectedStrategyName, setSelectedStrategyName] = useState<string | null>(null);
  const [pendingGlobalAction, setPendingGlobalAction] = useState<"enable" | "disable" | null>(null);
  const [pendingFamily, setPendingFamily] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<{
    tone: "neutral" | "warning";
    message: string;
  } | null>(null);

  useEffect(() => {
    setSummary(initialSummary);
    setSummaryError(initialSummaryError);
  }, [initialSummary, initialSummaryError]);

  const loadSummary = async (options?: { markLoading?: boolean }) => {
    if (options?.markLoading) {
      setSummaryLoading(true);
    }
    try {
      const nextSummary = await getControlPlaneSummary();
      setSummary(nextSummary);
      setSummaryError(null);
      return {
        failureDetail: null,
        summary: nextSummary,
      };
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Failed to load control plane.";
      setSummaryError(detail);
      return {
        failureDetail: detail,
        summary: null,
      };
    } finally {
      if (options?.markLoading) {
        setSummaryLoading(false);
      }
    }
  };

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      if (cancelled) {
        return;
      }
      setSummaryLoading(true);
      const nextSummary = await getControlPlaneSummary();
      if (cancelled) {
        setSummaryLoading(false);
        return;
      }
      setSummary(nextSummary);
      setSummaryError(null);
      setSummaryLoading(false);
    };
    const guardedRefresh = async () => {
      try {
        await refresh();
      } catch (error) {
        if (!cancelled) {
          setSummaryError(error instanceof Error ? error.message : "Failed to load control plane.");
          setSummaryLoading(false);
        }
      }
    };
    void guardedRefresh();
    const intervalId = window.setInterval(guardedRefresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const exceptionFamilies = useMemo(
    () => summary.families.filter((family) => familyTone(summary, family) !== "positive"),
    [summary],
  );
  const healthyFamilies = useMemo(
    () => summary.families.filter((family) => familyTone(summary, family) === "positive"),
    [summary],
  );

  useEffect(() => {
    const selectedStillExists = summary.families.some((family) => family.strategy_name === selectedStrategyName);
    if (selectedStrategyName && selectedStillExists) {
      return;
    }
    setSelectedStrategyName((exceptionFamilies[0] ?? summary.families[0])?.strategy_name ?? null);
  }, [exceptionFamilies, selectedStrategyName, summary.families]);

  const selectedFamily =
    summary.families.find((family) => family.strategy_name === selectedStrategyName) ?? exceptionFamilies[0] ?? null;
  const selectedTone = selectedFamily ? familyTone(summary, selectedFamily) : "inactive";
  const openRiskState = summary.open_risk_management_state;
  const openRiskUnavailable = openRiskState == null || openRiskState === "UNAVAILABLE" || openRiskState === "UNKNOWN";

  const handleGlobalAutonomy = async (enabled: boolean) => {
    try {
      setPendingGlobalAction(enabled ? "enable" : "disable");
      setStatusNotice(null);
      await updateOperatorControlState({
        autonomous_control_enabled: enabled,
        reason: enabled
          ? "Operator re-armed governed autonomy from the control plane."
          : "Operator paused governed autonomy from the control plane.",
      });
      const refreshed = await loadSummary();
      if (refreshed.failureDetail) {
        setStatusNotice({
          tone: "warning",
          message: `Operator control mutation succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
        });
      } else if (refreshed.summary?.effective_autonomous_control_enabled !== enabled) {
        setStatusNotice({
          tone: "warning",
          message: `Operator control mutation route succeeded, but refreshed backend truth still shows governed autonomy ${enabled ? "paused" : "authorized"}.`,
        });
      } else {
        setStatusNotice({
          tone: "neutral",
          message: `Operator control mutation confirmed after backend truth refreshed: governed autonomy ${enabled ? "armed" : "paused"}.`,
        });
      }
    } catch (error) {
      setStatusNotice({
        tone: "warning",
        message: `Operator control mutation failed: ${error instanceof Error ? error.message : "backend operator control truth could not be updated."}`,
      });
    } finally {
      setPendingGlobalAction(null);
    }
  };

  const handleFamilyAutonomy = async (strategyName: string, enabled: boolean) => {
    try {
      setPendingFamily(strategyName);
      setStatusNotice(null);
      await updateStrategyGovernance(strategyName, {
        autonomous_operation_allowed: enabled,
      });
      const refreshed = await loadSummary();
      const refreshedFamily = refreshed.summary?.families.find((family) => family.strategy_name === strategyName);
      if (refreshed.failureDetail) {
        setStatusNotice({
          tone: "warning",
          message: `Governance mutation succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
        });
      } else if (!refreshedFamily || refreshedFamily.governance.autonomous_operation_allowed !== enabled) {
        setStatusNotice({
          tone: "warning",
          message: `Governance mutation route succeeded, but refreshed backend truth still shows ${strategyName} auto deploy ${enabled ? "disallowed" : "allowed"}.`,
        });
      } else {
        setStatusNotice({
          tone: "neutral",
          message: `Governance mutation confirmed after backend truth refreshed: ${enabled ? `${strategyName} can auto deploy.` : `${strategyName} auto deploy disallowed.`}`,
        });
      }
    } catch (error) {
      setStatusNotice({
        tone: "warning",
        message: `Governance mutation failed: ${error instanceof Error ? error.message : "backend governance truth could not be updated."}`,
      });
    } finally {
      setPendingFamily(null);
    }
  };

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          {
            label: "Autonomy",
            value: summaryError ? (
              <>
                -<DataIndicator state={summaryLoading ? "loading" : "error"} message={summaryError} />
              </>
            ) : summary.effective_autonomous_control_enabled ? (
              "Authorized"
            ) : (
              "Paused"
            ),
            tone: summaryError ? "inactive" : summary.effective_autonomous_control_enabled ? "positive" : "negative",
            meta: summaryError ?? "permission only",
            emphasis: "strong",
          },
          {
            label: "Issues",
            value: summaryError ? "-" : exceptionFamilies.length,
            tone: summaryError ? "inactive" : exceptionFamilies.length ? "warning" : "positive",
            meta: summaryError ?? (exceptionFamilies.length ? "families need action" : "all aligned"),
            emphasis: "strong",
          },
          {
            label: "Emergency Stops",
            value: summaryError ? "-" : summary.families.filter((family) => family.governance.emergency_stop).length,
            tone: summaryError ? "inactive" : summary.families.some((family) => family.governance.emergency_stop) ? "negative" : "positive",
          },
          {
            label: "Entries",
            value: summaryError ? "-" : summary.entry_eligible ? "Allowed" : "Blocked",
            tone:
              summaryError
                ? "inactive"
                : summary.entry_eligible
                  ? "positive"
                  : "warning",
            meta: summaryError ?? (summary.entry_block_reason ? summary.entry_block_reason.replaceAll("_", " ") : "live execution allowed"),
          },
          {
            label: "Exits",
            value: summaryError ? "-" : summary.exit_eligible ? "Allowed" : "Blocked",
            tone:
              summaryError
                ? "inactive"
                : summary.exit_eligible
                  ? "positive"
                  : "negative",
            meta: summaryError ?? (summary.exit_block_reason ? summary.exit_block_reason.replaceAll("_", " ") : "existing risk can still be managed"),
          },
          {
            label: "Open Risk",
            value: summaryError ? "-" : openRiskState ?? "UNAVAILABLE",
            tone:
              summaryError
                ? "inactive"
                : openRiskUnavailable
                  ? "inactive"
                : openRiskState === "UNMANAGED_OPEN_RISK"
                  ? "negative"
                  : openRiskState === "EXITS_ONLY"
                    ? "warning"
                    : "positive",
          },
        ]}
      />

      <section className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.95fr)]">
        <Panel
          title="Family Alignment"
          subtitle="Permission, deployment, runtime mode, and open-risk management are separated so full AUTO is not mistaken for immediate entry readiness."
          priority="primary"
          tone={exceptionFamilies.length ? "warning" : "neutral"}
          actions={
            <div className="console-inline-actions">
              <button
                type="button"
                className="console-button"
                disabled={summaryError !== null || pendingGlobalAction !== null || summary.effective_autonomous_control_enabled}
                onClick={() => handleGlobalAutonomy(true)}
              >
                {pendingGlobalAction === "enable" ? "Arming..." : "Arm"}
              </button>
              <button
                type="button"
                className="console-button console-button--ghost"
                disabled={summaryError !== null || pendingGlobalAction !== null || !summary.effective_autonomous_control_enabled}
                onClick={() => handleGlobalAutonomy(false)}
              >
                {pendingGlobalAction === "disable" ? "Pausing..." : "Pause"}
              </button>
            </div>
          }
        >
          <CompactTable
            rows={[...exceptionFamilies, ...healthyFamilies]}
            emptyLabel={summaryError ? "Control plane unavailable." : "No families configured."}
            getRowTone={(family) => familyTone(summary, family)}
            getRowActive={(family) => family.strategy_name === selectedStrategyName}
            columns={[
              {
                key: "family",
                header: "Strategy",
                className: "w-[24%]",
                render: (family) => (
                  <button
                    type="button"
                    className={`console-link-button${family.strategy_name === selectedStrategyName ? " is-active" : ""}`}
                    onClick={() => setSelectedStrategyName(family.strategy_name)}
                    title={family.strategy_name}
                  >
                    <span className="block truncate">{family.strategy_name}</span>
                  </button>
                ),
              },
              {
                key: "alignment",
                header: "Alignment",
                render: (family) => (
                  <StatusPill
                    label={family.alignment.status}
                    tone={familyTone(summary, family)}
                    title={family.alignment.reason ?? undefined}
                  />
                ),
              },
              {
                key: "intent",
                header: "Selected",
                render: (family) => `${family.deployment?.selected_profile ?? "n/a"} · ${family.deployment?.selected_instrument ?? "n/a"}`,
              },
              {
                key: "runtime",
                header: "Runtime",
                render: (family) =>
                  family.runtime.is_running
                    ? `${family.runtime.runtime_mode ?? "NORMAL"} · ${family.runtime.active_instrument ?? "n/a"}`
                    : "not running",
              },
              {
                key: "state",
                header: "Deploy",
                render: (family) => family.deployment?.state ?? "UNASSIGNED",
              },
              {
                key: "open-risk",
                header: "Risk",
                render: (family) => (
                  <span title={familyOpenRiskReason(family) ?? undefined}>
                    {familyOpenRiskLabel(family)}
                  </span>
                ),
              },
            ]}
          />
        </Panel>

        <Panel title="Lead Inspection" subtitle="Selected family details and intervention controls." priority="critical" tone={selectedTone}>
            {selectedFamily ? (
              <div className="detail-stack">
                <div className="status-note status-note--inline">
                  {exceptionFamilies.length
                    ? `${exceptionFamilies.length} family${exceptionFamilies.length === 1 ? "" : "ies"} currently need intervention.`
                    : "No families currently need intervention."}
                </div>

                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>Family</span>
                    <strong>{selectedFamily.strategy_name}</strong>
                    <em>{selectedFamily.description}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Control</span>
                    <strong>{familyOpenRiskLabel(selectedFamily)}</strong>
                    <em>{selectedFamily.deployment?.state ?? selectedFamily.alignment.status}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Updated</span>
                    <strong>{formatTime(selectedFamily.deployment?.last_evaluated_at)}</strong>
                    <em>last evaluation</em>
                  </div>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Why This Is Priority</span>
                  <p>{familyOpenRiskReason(selectedFamily) || selectedFamily.deployment?.blocked_reason || selectedFamily.deployment?.degraded_reason || selectedFamily.alignment.reason}</p>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Observed State</span>
                  <p>Permission: {selectedFamily.governance.autonomous_operation_allowed ? "authorized for autonomous deployment" : "not authorized for autonomous deployment"}</p>
                  <p>Governance: {selectedFamily.governance.approval_state}</p>
                  <p>Runtime: {selectedFamily.runtime.is_running ? `${selectedFamily.runtime.control_mode ?? "UNKNOWN"} / ${selectedFamily.runtime.runtime_mode ?? "NORMAL"} active` : "not running"}</p>
                  <p>Instrument: {selectedFamily.runtime.active_instrument ?? selectedFamily.deployment?.selected_instrument ?? "n/a"}</p>
                  <p>Open risk: {familyOpenRiskLabel(selectedFamily)}</p>
                  <p>Deployment: {selectedFamily.deployment?.state ?? "UNASSIGNED"}</p>
                </div>

                <div className="console-inline-actions">
                  <button
                    type="button"
                    className="console-button"
                    disabled={pendingFamily === selectedFamily.strategy_name || selectedFamily.governance.autonomous_operation_allowed}
                    onClick={() => handleFamilyAutonomy(selectedFamily.strategy_name, true)}
                  >
                    {pendingFamily === selectedFamily.strategy_name ? "Updating..." : "Allow Auto Deploy"}
                  </button>
                  <button
                    type="button"
                    className="console-button console-button--ghost"
                    disabled={pendingFamily === selectedFamily.strategy_name || !selectedFamily.governance.autonomous_operation_allowed}
                    onClick={() => handleFamilyAutonomy(selectedFamily.strategy_name, false)}
                  >
                    {pendingFamily === selectedFamily.strategy_name ? "Updating..." : "Disallow"}
                  </button>
                </div>

                <CompactTable
                  dense
                  rows={selectedFamily.recent_events.slice(0, 5)}
                  emptyLabel="No recent lifecycle events."
                  columns={[
                    { key: "time", header: "Time", render: (event) => formatTime(event.created_at) },
                    { key: "event", header: "Event", render: (event) => event.event_type },
                    { key: "title", header: "Title", render: (event) => event.title },
                  ]}
                />
              </div>
            ) : (
              <div className="console-empty">No family selected.</div>
            )}
        </Panel>
      </section>
      {statusNotice ? <div className={`console-alert console-alert--${statusNotice.tone}`}>{statusNotice.message}</div> : null}
    </main>
  );
}
