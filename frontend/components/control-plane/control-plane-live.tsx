"use client";

import { useEffect, useMemo, useState } from "react";

import { CompactTable, Panel, SplitPanel, StatusPill, StatusStrip } from "@/components/console/primitives";
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
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function familyTone(summary: ControlPlaneSummary, family: ControlPlaneFamily) {
  const deploymentState = family.deployment?.state;
  if (!summary.effective_autonomous_control_enabled || family.governance.emergency_stop || deploymentState === "BLOCKED" || deploymentState === "EMERGENCY_STOPPED") {
    return "negative" as const;
  }
  if (family.alignment.status !== "ALIGNED" || deploymentState === "DEGRADED") {
    return "warning" as const;
  }
  return "positive" as const;
}

export function ControlPlaneLive({ initialSummary }: ControlPlaneLiveProps) {
  const [summary, setSummary] = useState(initialSummary);
  const [selectedStrategyName, setSelectedStrategyName] = useState<string | null>(null);
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
        if (!cancelled) {
          setSummary(nextSummary);
        }
      } catch {
        // Keep last snapshot visible.
      }
    };
    const intervalId = window.setInterval(refresh, 5000);
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

  const refreshSummary = async () => {
    const nextSummary = await getControlPlaneSummary();
    setSummary(nextSummary);
  };

  const handleGlobalAutonomy = async (enabled: boolean) => {
    try {
      setPendingGlobalAction(enabled ? "enable" : "disable");
      await updateOperatorControlState({
        autonomous_control_enabled: enabled,
        reason: enabled
          ? "Operator re-armed governed autonomy from the control plane."
          : "Operator paused governed autonomy from the control plane.",
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
    <main className="console-page">
      <StatusStrip
        items={[
          {
            label: "Autonomy",
            value: summary.effective_autonomous_control_enabled ? "Armed" : "Paused",
            tone: summary.effective_autonomous_control_enabled ? "positive" : "negative",
            emphasis: "strong",
          },
          {
            label: "Issues",
            value: exceptionFamilies.length,
            tone: exceptionFamilies.length ? "warning" : "positive",
            meta: exceptionFamilies.length ? "families need action" : "all aligned",
            emphasis: "strong",
          },
          {
            label: "Emergency Stops",
            value: summary.families.filter((family) => family.governance.emergency_stop).length,
            tone: summary.families.some((family) => family.governance.emergency_stop) ? "negative" : "positive",
          },
          {
            label: "Auto Deployed",
            value: summary.counts.AUTO_DEPLOYED ?? 0,
            tone: "neutral",
          },
        ]}
      />

      <SplitPanel
        left={
          <Panel
            title="Intervention Queue"
            subtitle="Highest-priority families first."
            priority="critical"
            tone={exceptionFamilies.length ? "warning" : "positive"}
            actions={
              <div className="console-inline-actions">
                <button
                  type="button"
                  className="console-button"
                  disabled={pendingGlobalAction !== null || summary.effective_autonomous_control_enabled}
                  onClick={() => handleGlobalAutonomy(true)}
                >
                  {pendingGlobalAction === "enable" ? "Arming..." : "Arm"}
                </button>
                <button
                  type="button"
                  className="console-button console-button--ghost"
                  disabled={pendingGlobalAction !== null || !summary.effective_autonomous_control_enabled}
                  onClick={() => handleGlobalAutonomy(false)}
                >
                  {pendingGlobalAction === "disable" ? "Pausing..." : "Pause"}
                </button>
              </div>
            }
          >
            <CompactTable
              rows={exceptionFamilies}
              emptyLabel="No intervention-required families."
              getRowTone={(family) => familyTone(summary, family)}
              getRowActive={(family) => family.strategy_name === selectedStrategyName}
              columns={[
                {
                  key: "family",
                  header: "Family",
                  render: (family) => (
                    <button
                      type="button"
                      className={`console-link-button${family.strategy_name === selectedStrategyName ? " is-active" : ""}`}
                      onClick={() => setSelectedStrategyName(family.strategy_name)}
                    >
                      {family.strategy_name}
                    </button>
                  ),
                },
                {
                  key: "alignment",
                  header: "Alignment",
                  render: (family) => <StatusPill label={family.alignment.status} tone={familyTone(summary, family)} />,
                },
                {
                  key: "state",
                  header: "State",
                  render: (family) => family.deployment?.state ?? "UNASSIGNED",
                },
              ]}
            />
          </Panel>
        }
        center={
          <Panel title="Alignment Matrix" subtitle="Full family comparison." priority="primary" tone={exceptionFamilies.length ? "warning" : "neutral"}>
            <CompactTable
              rows={summary.families}
              emptyLabel="No families configured."
              getRowTone={(family) => familyTone(summary, family)}
              getRowActive={(family) => family.strategy_name === selectedStrategyName}
              columns={[
                {
                  key: "family",
                  header: "Family",
                  render: (family) => (
                    <button
                      type="button"
                      className={`console-link-button${family.strategy_name === selectedStrategyName ? " is-active" : ""}`}
                      onClick={() => setSelectedStrategyName(family.strategy_name)}
                    >
                      {family.strategy_name}
                    </button>
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
                      ? `${family.runtime.active_profile_name ?? "n/a"} · ${family.runtime.active_instrument ?? "n/a"}`
                      : "not running",
                },
                {
                  key: "state",
                  header: "Deploy",
                  render: (family) => family.deployment?.state ?? "UNASSIGNED",
                },
              ]}
            />
          </Panel>
        }
        right={
          <Panel title="Lead Inspection" subtitle="Current highest-priority target." priority="critical" tone={selectedTone}>
            {selectedFamily ? (
              <div className="detail-stack">
                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>Family</span>
                    <strong>{selectedFamily.strategy_name}</strong>
                    <em>{selectedFamily.description}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Status</span>
                    <strong>{selectedFamily.deployment?.state ?? "UNASSIGNED"}</strong>
                    <em>{selectedFamily.alignment.status}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Updated</span>
                    <strong>{formatTime(selectedFamily.deployment?.last_evaluated_at)}</strong>
                    <em>last evaluation</em>
                  </div>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Why This Is Priority</span>
                  <p>{selectedFamily.deployment?.blocked_reason || selectedFamily.deployment?.degraded_reason || selectedFamily.alignment.reason}</p>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Observed State</span>
                  <p>Governance: {selectedFamily.governance.approval_state}</p>
                  <p>Runtime: {selectedFamily.runtime.is_running ? `${selectedFamily.runtime.control_mode ?? "UNKNOWN"} active` : "not running"}</p>
                  <p>Instrument: {selectedFamily.runtime.active_instrument ?? selectedFamily.deployment?.selected_instrument ?? "n/a"}</p>
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
        }
      />

      <Panel title="Stable Families" priority="passive" tone="inactive" compact>
        <CompactTable
          dense
          rows={healthyFamilies}
          emptyLabel="No stable families."
          columns={[
            { key: "family", header: "Family", render: (family) => family.strategy_name },
            { key: "profile", header: "Profile", render: (family) => family.deployment?.selected_profile ?? "n/a" },
            { key: "instrument", header: "Instrument", render: (family) => family.runtime.active_instrument ?? family.deployment?.selected_instrument ?? "n/a" },
          ]}
        />
      </Panel>
    </main>
  );
}
