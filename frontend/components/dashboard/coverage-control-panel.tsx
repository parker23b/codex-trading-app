"use client";

import { Card } from "@/components/ui/card";
import { CoverageSummary, SystemOperatingLimits } from "@/lib/types";

type CoverageControlPanelProps = {
  coverage: CoverageSummary;
  operatingLimits?: SystemOperatingLimits;
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

export function CoverageControlPanel({ coverage, operatingLimits }: CoverageControlPanelProps) {
  const tier1 = coverage.streaming.active_instruments.slice(0, 6);
  const tier2 = coverage.tier2.active_candidates.slice(0, 6);
  const promotions = coverage.promotions.recent_requests.slice(0, 5);
  const streamCap = operatingLimits?.coverage.max_instruments ?? 0;
  const promotionThreshold = operatingLimits?.coverage.tier2_promotion_score_threshold ?? 0;
  const refreshBatchSize = operatingLimits?.coverage.tier2_refresh_batch_size ?? 0;
  const refreshInterval = operatingLimits?.coverage.tier2_refresh_interval_seconds ?? 0;
  const openRiskLimit = operatingLimits?.risk.max_open_risk_percent ?? 0;

  return (
    <Card title="Coverage Monitor" subtitle="Tier 1 streaming ownership, Tier 2 promotion flow, and the backend policy currently governing both.">
      <div className="summary-grid">
        <div className="summary-grid__item">
          <span className="eyebrow">Tier 1 Live</span>
          <strong>{coverage.streaming.desired_instruments.length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Pinned</span>
          <strong>{coverage.streaming.pinned_instruments.length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Tier 2 Queue</span>
          <strong>{coverage.tier2.refresh_queue.length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Pending</span>
          <strong>{coverage.promotions.pending_count}</strong>
        </div>
      </div>

      {operatingLimits ? (
        <div className="review-stack">
          <div className="status-note status-note--inline">
            Backend policy: stream cap {streamCap} instruments, promote at score {promotionThreshold.toFixed(2)}+, refresh Tier 2 in batches of {refreshBatchSize} every {refreshInterval.toFixed(0)}s.
          </div>
          <div className="status-note status-note--inline">
            Portfolio guardrail: total open risk targets {openRiskLimit.toFixed(1)}% max before new entries are blocked.
          </div>
        </div>
      ) : null}

      <section className="review-panel__split">
        <div>
          <div className="review-panel__label">Tier 1 Watchlist</div>
          <div className="review-stack">
            {tier1.length ? (
              tier1.map((entry) => (
                <div className="status-note status-note--inline" key={entry.instrument}>
                  {entry.instrument} · {entry.reason ?? "watchlist"} · {entry.pinned ? "pinned" : "ranked"} · refreshed {formatTime(entry.last_streamed_at)}
                </div>
              ))
            ) : (
              <div className="status-note status-note--inline">No active Tier 1 coverage assignments.</div>
            )}
          </div>
        </div>
        <div>
          <div className="review-panel__label">Tier 2 Candidates</div>
          <div className="review-stack">
            {tier2.length ? (
              tier2.map((entry) => (
                <div className="status-note status-note--inline" key={entry.instrument}>
                  {entry.instrument} · score {entry.priority_score.toFixed(1)} · refreshed {formatTime(entry.last_refreshed_at)}
                </div>
              ))
            ) : (
              <div className="status-note status-note--inline">No Tier 2 candidates are waiting for refresh.</div>
            )}
          </div>
        </div>
      </section>

      <section className="review-panel__section">
        <div className="review-panel__label">Recent Promotion Decisions</div>
        <div className="review-stack">
          {promotions.length ? (
            promotions.map((request) => (
              <div className="status-note status-note--inline" key={`${request.instrument}-${request.updated_at}`}>
                {request.instrument} · {request.status.toLowerCase()} · {request.source} · score {request.score.toFixed(2)}
              </div>
            ))
          ) : (
            <div className="status-note status-note--inline">No promotion decisions have been recorded yet.</div>
          )}
        </div>
      </section>
    </Card>
  );
}
