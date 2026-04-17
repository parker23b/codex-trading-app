"use client";

import Link from "next/link";

import { Panel, StatusPill } from "@/components/console/primitives";
import { formatDirectionalBias, formatHotspotLabel, type RiskConsoleSummary } from "@/lib/risk-allocation";

type RiskStatusBlockProps = {
  summary: RiskConsoleSummary;
  onOpenDrawer: () => void;
};

export function RiskStatusBlock({ summary, onOpenDrawer }: RiskStatusBlockProps) {
  const panelTone =
    summary.criticalAlertCount > 0
      ? "negative"
      : summary.degradedSizingOrTruth || summary.materialDriftCount > 0
        ? "warning"
        : "positive";

  return (
    <Panel
      title="Risk Status"
      subtitle="Allocation and execution truth, reduced to what matters right now."
      priority="primary"
      tone={panelTone}
      actions={
        <div className="console-inline-actions">
          <StatusPill label={summary.lastCycleStatus.label} tone={summary.lastCycleStatus.tone} />
          {summary.degradedSizingOrTruth ? <StatusPill label="Degraded" tone="warning" /> : null}
        </div>
      }
      className="risk-command-panel"
    >
      <div className="risk-command-panel__grid">
        {summary.metrics.map((metric) => (
          <article key={metric.label} className={`risk-command-metric risk-command-metric--${metric.tone}`}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <em>{metric.meta}</em>
          </article>
        ))}
      </div>

      <div className="risk-command-panel__briefing">
        <div className="risk-command-panel__briefing-item">
          <span>Concentration hotspot</span>
          <strong>{formatHotspotLabel(summary.topHotspot)}</strong>
        </div>
        <div className="risk-command-panel__briefing-item">
          <span>Dominant net bias</span>
          <strong>{formatDirectionalBias(summary.dominantNetCurrency)}</strong>
        </div>
        <div className="risk-command-panel__briefing-item">
          <span>Last allocation cycle</span>
          <strong>{summary.lastCycleStatus.meta}</strong>
        </div>
      </div>

      <div className="risk-command-panel__actions">
        <button type="button" className="console-button console-button--ghost" onClick={onOpenDrawer}>
          Open Risk Briefing
        </button>
        <Link href="/risk" className="console-button">
          Full Risk / Allocation
        </Link>
      </div>
    </Panel>
  );
}
