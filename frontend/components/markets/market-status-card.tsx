"use client";

import { StatusBadge } from "@/components/ui/status-badge";
import { Card } from "@/components/ui/card";
import { MarketSummary } from "@/lib/types";

type MarketStatusCardProps = {
  summary: MarketSummary;
  countdownLabel: string;
};

function getTone(status: MarketSummary["status"]) {
  if (status === "OPEN") {
    return "positive" as const;
  }
  if (status === "LIMITED") {
    return "warning" as const;
  }
  return "negative" as const;
}

export function MarketStatusCard({ summary, countdownLabel }: MarketStatusCardProps) {
  return (
    <Card
      title={`${summary.label} Market Status`}
      subtitle={summary.description}
      className="market-status-card"
      action={<StatusBadge label={summary.status} tone={getTone(summary.status)} />}
    >
      {/* Oversized status text is intentional: the open/closed decision should resolve before the user scans any row-level detail. */}
      <div className="market-status-card__hero">
        <div>
          <div className={`market-status-card__headline market-status-card__headline--${summary.status.toLowerCase()}`}>
            {summary.status}
          </div>
          <p className="market-status-card__countdown">{countdownLabel}</p>
        </div>
        <div className="market-status-card__metrics">
          <div className="summary-grid__item">
            <span className="eyebrow">Tradable</span>
            <strong>
              {summary.tradableCount}/{summary.totalCount}
            </strong>
          </div>
          <div className="summary-grid__item">
            <span className="eyebrow">Active</span>
            <strong>{summary.activeCount}</strong>
          </div>
        </div>
      </div>
      <div className="status-note status-note--inline">{summary.detail}</div>
    </Card>
  );
}
