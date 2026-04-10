"use client";

import { useEffect, useState } from "react";

import { CoverageControlPanel } from "@/components/dashboard/coverage-control-panel";
import { Card } from "@/components/ui/card";
import { getCoverageSummary, getOperationalTelemetry, getSystemOperatingLimits } from "@/lib/api";
import { CoverageSummary, OperationalTelemetry, SystemOperatingLimits } from "@/lib/types";

type CoverageLiveProps = {
  initialCoverage: CoverageSummary;
  initialTelemetry: OperationalTelemetry;
  initialOperatingLimits: SystemOperatingLimits;
};

function formatAge(ms?: number | null) {
  if (ms === null || ms === undefined) {
    return "n/a";
  }
  if (ms < 1000) {
    return `${ms.toFixed(0)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

export function CoverageLive({ initialCoverage, initialTelemetry, initialOperatingLimits }: CoverageLiveProps) {
  const [coverage, setCoverage] = useState(initialCoverage);
  const [telemetry, setTelemetry] = useState(initialTelemetry);
  const [operatingLimits, setOperatingLimits] = useState(initialOperatingLimits);

  useEffect(() => {
    setCoverage(initialCoverage);
    setTelemetry(initialTelemetry);
    setOperatingLimits(initialOperatingLimits);
  }, [initialCoverage, initialTelemetry, initialOperatingLimits]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const [nextCoverage, nextTelemetry, nextOperatingLimits] = await Promise.all([getCoverageSummary(), getOperationalTelemetry(), getSystemOperatingLimits()]);
        if (cancelled) {
          return;
        }
        setCoverage(nextCoverage);
        setTelemetry(nextTelemetry);
        setOperatingLimits(nextOperatingLimits);
      } catch {
        // Keep the last successful snapshot visible if refresh fails.
      }
    };
    const intervalId = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  return (
    <main className="page-grid">
      <CoverageControlPanel coverage={coverage} operatingLimits={operatingLimits} />

      <section className="page-grid">
        <Card title="Operating Limits" subtitle="Backend config that currently shapes promotion, risk, and execution decisions.">
          <div className="summary-grid">
            <div className="summary-grid__item">
              <span className="eyebrow">Risk Budget</span>
              <strong>{operatingLimits.risk.max_open_risk_percent.toFixed(1)}%</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Tier 1 Cap</span>
              <strong>{operatingLimits.coverage.max_instruments}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Quote Freshness</span>
              <strong>{operatingLimits.execution.max_price_age_ms.toFixed(0)}ms</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Max Spread</span>
              <strong>{operatingLimits.execution.max_spread_pips.toFixed(1)} pips</strong>
            </div>
          </div>
          <div className="review-stack">
            <div className="status-note status-note--inline">
              Runtime policy: {operatingLimits.risk.max_open_positions} total positions, {operatingLimits.risk.max_positions_per_strategy} per strategy, daily loss guard at {operatingLimits.risk.daily_loss_limit.toFixed(0)}, kill switch {operatingLimits.risk.global_entry_kill_switch ? "on" : "off"}.
            </div>
            <div className="status-note status-note--inline">
              Execution policy: allocator {operatingLimits.execution.allocator_enabled ? "enabled" : "disabled"}, {operatingLimits.execution.allocator_max_decisions_per_cycle} decisions per cycle, stale signal cutoff {operatingLimits.execution.allocator_signal_stale_after_seconds.toFixed(0)}s, burst limit {operatingLimits.execution.entry_burst_limit} in {operatingLimits.execution.entry_burst_window_seconds}s.
            </div>
            <div className="status-note status-note--inline">
              Coverage policy: Tier 2 refresh {operatingLimits.coverage.tier2_refresh_batch_size} instruments every {operatingLimits.coverage.tier2_refresh_interval_seconds.toFixed(0)}s, promotion threshold {operatingLimits.coverage.tier2_promotion_score_threshold.toFixed(2)}, promotion TTL {operatingLimits.coverage.tier2_promotion_ttl_seconds}s, churn cap {operatingLimits.coverage.max_subscription_churn_per_minute}/min.
            </div>
            <div className="status-note status-note--inline">
              Screeners: {operatingLimits.screening.length ? operatingLimits.screening.map((screening) => `${screening.name} -> ${screening.refresh_tier} at ${screening.promotion_threshold.toFixed(2)}+`).join(" | ") : "No screening thresholds published."}
            </div>
          </div>
        </Card>
      </section>

      <section className="page-grid">
        <Card title="Trade Allocator" subtitle="What advanced toward risk and execution, and what was filtered first.">
          <div className="summary-grid">
            <div className="summary-grid__item">
              <span className="eyebrow">Selected</span>
              <strong>{coverage.trade_allocator.selected_count}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Rejected</span>
              <strong>{coverage.trade_allocator.rejected_count}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Top Filter</span>
              <strong>
                {Object.entries(coverage.trade_allocator.reason_counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "n/a"}
              </strong>
            </div>
          </div>
          <div className="review-stack">
            {coverage.trade_allocator.recent_decisions.length ? (
              coverage.trade_allocator.recent_decisions.map((decision) => (
                <div className="status-note status-note--inline" key={`${decision.event_type}-${decision.id ?? decision.created_at}`}>
                  {decision.selected ? "selected" : "rejected"} · {decision.strategy_name ?? "unknown strategy"} · {decision.instrument ?? "unknown instrument"}
                  {decision.direction ? ` · ${decision.direction}` : ""}
                  {decision.score !== null && decision.score !== undefined ? ` · score ${decision.score.toFixed(3)}` : ""}
                  {decision.reason_code ? ` · ${decision.reason_code}` : ""}
                  {decision.reason ? ` · ${decision.reason}` : ""}
                </div>
              ))
            ) : (
              <div className="status-note status-note--inline">No allocator decisions have been recorded yet.</div>
            )}
          </div>
        </Card>
      </section>

      <section className="page-grid">
        <Card title="Execution Readiness" subtitle="Deep market-status checks used by runtime entry and execution gates.">
          <div className="review-stack">
            {coverage.streaming.execution_readiness.length ? (
              coverage.streaming.execution_readiness.map((item) => (
                <div className="status-note status-note--inline" key={item.instrument}>
                  {item.instrument} · {item.is_ok ? "ready" : "blocked"} · open {String(item.market_open)} · tradable {String(item.tradable)} · fresh {String(item.quote_fresh)} · spread {String(item.spread_ok)} · session {String(item.session_valid)} · dealing {String(item.dealing_allowed)}
                  {item.reason ? ` · ${item.reason}` : ""}
                </div>
              ))
            ) : (
              <div className="status-note status-note--inline">No Tier 1 instruments are currently being checked for execution readiness.</div>
            )}
          </div>
        </Card>
      </section>

      <section className="page-grid">
        <Card title="Operational Telemetry" subtitle="Runtime, stream, broker, reconciliation, and order-path health.">
          <div className="summary-grid">
            <div className="summary-grid__item">
              <span className="eyebrow">Health</span>
              <strong>{telemetry.status}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Runtimes</span>
              <strong>{telemetry.active_runtime_count}/{telemetry.runtime_count}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Stream</span>
              <strong>{telemetry.stream_connected ? "connected" : "down"}</strong>
            </div>
            <div className="summary-grid__item">
              <span className="eyebrow">Broker Latency</span>
              <strong>{telemetry.broker_latency_ms?.toFixed(1) ?? "n/a"}ms</strong>
            </div>
          </div>
          <div className="review-stack">
            <div className="status-note status-note--inline">Heartbeat age: {formatAge(telemetry.heartbeat_age_ms)} · Last price age: {formatAge(telemetry.last_price_age_ms)} · Stream tick age: {formatAge(telemetry.stream_last_tick_age_ms)}</div>
            <div className="status-note status-note--inline">Stale runtimes: {telemetry.stale_runtime_count} · Stale price runtimes: {telemetry.stale_price_runtime_count} · Paused by health: {telemetry.strategies_paused_by_health}</div>
            <div className="status-note status-note--inline">Reconciliation mismatches: {telemetry.reconciliation_mismatches} · Order failures 5m: {telemetry.order_failures_last_5m} · Risk rejections 5m: {telemetry.rejected_orders_last_5m}</div>
            <div className="status-note status-note--inline">Desired streams: {telemetry.desired_instrument_count} · Subscribed: {telemetry.subscribed_instrument_count} · Broker connected: {String(telemetry.broker_connected)}</div>
          </div>
        </Card>
      </section>
    </main>
  );
}
