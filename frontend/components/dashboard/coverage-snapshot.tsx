"use client";

import Link from "next/link";

import { Card } from "@/components/ui/card";
import { CoverageSummary } from "@/lib/types";

type CoverageSnapshotProps = {
  coverage: CoverageSummary;
};

export function CoverageSnapshot({ coverage }: CoverageSnapshotProps) {
  const blockedReadinessCount = coverage.streaming.execution_readiness.filter((item) => !item.is_ok).length;
  const topBlocked = coverage.streaming.execution_readiness.filter((item) => !item.is_ok).slice(0, 3);

  return (
    <Card
      title="Coverage Snapshot"
      subtitle="How the watched universe is feeding autonomous deployment right now."
      className="card--compact board-surface board-surface--rail"
      action={
        <Link href="/coverage" className="nav-link">
          Open Coverage
        </Link>
      }
    >
      <div className="summary-grid">
        <div className="summary-grid__item">
          <span className="eyebrow">Tier 1 Live</span>
          <strong>{coverage.streaming.desired_instruments.length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Tier 2 Queue</span>
          <strong>{coverage.tier2.refresh_queue.length}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Pending Promotions</span>
          <strong>{coverage.promotions.pending_count}</strong>
        </div>
        <div className="summary-grid__item">
          <span className="eyebrow">Readiness Blocked</span>
          <strong>{blockedReadinessCount}</strong>
        </div>
      </div>

      <div className="review-stack">
        {topBlocked.length ? (
          topBlocked.map((item) => (
            <div className="status-note status-note--inline" key={item.instrument}>
              {item.instrument} · blocked · {item.reason ?? "execution readiness check failed"}
            </div>
          ))
        ) : (
          <div className="status-note status-note--inline">No Tier 1 instruments are currently blocked by execution-readiness checks.</div>
        )}
      </div>
    </Card>
  );
}
