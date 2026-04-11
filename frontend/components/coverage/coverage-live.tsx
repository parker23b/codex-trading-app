"use client";

import { useEffect, useMemo, useState } from "react";

import { CompactTable, DataIndicator, Panel, SplitPanel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getCoverageSummary, getOperationalTelemetry, getSystemOperatingLimits } from "@/lib/api";
import { formatRelativeDuration } from "@/lib/format";
import { CoverageSummary, OperationalTelemetry, SystemOperatingLimits } from "@/lib/types";

type CoverageResourceErrors = {
  coverage: string | null;
  telemetry: string | null;
  operatingLimits: string | null;
};

type CoverageLiveProps = {
  initialCoverage: CoverageSummary;
  initialTelemetry: OperationalTelemetry;
  initialOperatingLimits: SystemOperatingLimits;
  initialErrors: CoverageResourceErrors;
};

function formatAge(ms?: number | null) {
  if (ms == null) {
    return "n/a";
  }
  if (ms < 1000) {
    return `${ms.toFixed(0)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

export function CoverageLive({ initialCoverage, initialTelemetry, initialOperatingLimits, initialErrors }: CoverageLiveProps) {
  const [coverage, setCoverage] = useState(initialCoverage);
  const [telemetry, setTelemetry] = useState(initialTelemetry);
  const [operatingLimits, setOperatingLimits] = useState(initialOperatingLimits);
  const [errors, setErrors] = useState(initialErrors);

  useEffect(() => {
    setCoverage(initialCoverage);
    setTelemetry(initialTelemetry);
    setOperatingLimits(initialOperatingLimits);
    setErrors(initialErrors);
  }, [initialCoverage, initialErrors, initialOperatingLimits, initialTelemetry]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const [nextCoverage, nextTelemetry, nextOperatingLimits] = await Promise.allSettled([
          getCoverageSummary(),
          getOperationalTelemetry(),
          getSystemOperatingLimits(),
        ]);
      if (!cancelled) {
        if (nextCoverage.status === "fulfilled") {
          setCoverage(nextCoverage.value);
        }
        if (nextTelemetry.status === "fulfilled") {
          setTelemetry(nextTelemetry.value);
        }
        if (nextOperatingLimits.status === "fulfilled") {
          setOperatingLimits(nextOperatingLimits.value);
        }
        setErrors({
          coverage: nextCoverage.status === "rejected" ? (nextCoverage.reason instanceof Error ? nextCoverage.reason.message : "Failed to load coverage.") : null,
          telemetry: nextTelemetry.status === "rejected" ? (nextTelemetry.reason instanceof Error ? nextTelemetry.reason.message : "Failed to load telemetry.") : null,
          operatingLimits: nextOperatingLimits.status === "rejected" ? (nextOperatingLimits.reason instanceof Error ? nextOperatingLimits.reason.message : "Failed to load limits.") : null,
        });
      }
    };
    void refresh();
    const intervalId = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const blockedReadiness = coverage.streaming.execution_readiness.filter((row) => !row.is_ok);
  const topRejectionReason = useMemo(
    () => Object.entries(coverage.trade_allocator.reason_counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "n/a",
    [coverage.trade_allocator.reason_counts],
  );
  const activeUniverseRows = coverage.streaming.active_instruments.slice().sort((a, b) => {
    if (a.streamed !== b.streamed) {
      return Number(b.streamed) - Number(a.streamed);
    }
    return a.instrument.localeCompare(b.instrument);
  });

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          {
            label: "Tier 1 Live",
            value: errors.coverage ? (
              <>
                -<DataIndicator state="error" message={errors.coverage} />
              </>
            ) : (
              coverage.streaming.active_instruments.length
            ),
            tone: errors.coverage ? "inactive" : "positive",
            emphasis: "strong",
          },
          {
            label: "Readiness Blocked",
            value: errors.coverage ? "-" : blockedReadiness.length,
            tone: errors.coverage ? "inactive" : blockedReadiness.length ? "warning" : "positive",
            emphasis: "strong",
          },
          {
            label: "Promotions",
            value: errors.coverage ? "-" : coverage.promotions.pending_count,
            tone: errors.coverage ? "inactive" : coverage.promotions.pending_count ? "warning" : "neutral",
            meta: errors.coverage ?? "pending",
          },
          {
            label: "Allocator",
            value: errors.coverage ? "-" : coverage.trade_allocator.rejected_count,
            tone: errors.coverage ? "inactive" : coverage.trade_allocator.rejected_count ? "warning" : "positive",
            meta: errors.coverage ?? "recent rejects",
          },
          {
            label: "Telemetry",
            value: errors.telemetry ? (
              <>
                -<DataIndicator state="error" message={errors.telemetry} />
              </>
            ) : (
              telemetry.status
            ),
            tone: errors.telemetry ? "inactive" : telemetry.status === "healthy" ? "positive" : "warning",
          },
        ]}
      />

      <SplitPanel
        className="layout-coverage"
        left={
          <Panel title="Monitored Universe" subtitle="Primary watch state." priority="primary" tone={blockedReadiness.length ? "warning" : "positive"}>
            <CompactTable
              rows={activeUniverseRows}
              emptyLabel={errors.coverage ? "Coverage feed unavailable." : "No active Tier 1 instruments."}
              getRowTone={(row) => (!row.streamed ? "inactive" : row.status !== "ACTIVE" ? "warning" : "positive")}
              columns={[
                { key: "instrument", header: "Instrument", render: (row) => row.instrument },
                { key: "tier", header: "Tier", render: (row) => row.tier },
                {
                  key: "state",
                  header: "State",
                  render: (row) => (
                    <StatusPill
                      label={row.streamed ? row.status.toLowerCase() : "not streaming"}
                      tone={!row.streamed ? "inactive" : row.status !== "ACTIVE" ? "warning" : "positive"}
                    />
                  ),
                },
                {
                  key: "age",
                  header: "Last Stream",
                  render: (row) => (row.last_streamed_at ? `${formatRelativeDuration(row.last_streamed_at)} ago` : "never"),
                },
              ]}
            />
          </Panel>
        }
        center={
          <Panel title="Readiness" subtitle="What is blocked right now." priority="critical" tone={blockedReadiness.length ? "warning" : "positive"}>
            <CompactTable
              rows={coverage.streaming.execution_readiness}
              emptyLabel={errors.coverage ? "Coverage feed unavailable." : "No readiness records available."}
              getRowTone={(row) => (row.is_ok ? "positive" : "warning")}
              columns={[
                { key: "instrument", header: "Instrument", render: (row) => row.instrument },
                {
                  key: "ready",
                  header: "State",
                  render: (row) => <StatusPill label={row.is_ok ? "ready" : "blocked"} tone={row.is_ok ? "positive" : "warning"} />,
                },
                { key: "quote", header: "Quote", render: (row) => `${row.last_price_age_ms.toFixed(0)}ms` },
                { key: "reason", header: "Reason", render: (row) => row.reason ?? "All gates clear." },
              ]}
            />
          </Panel>
        }
        right={
          <div className="stack-layout">
            <Panel title="Promotions" priority="secondary" tone={coverage.promotions.pending_count ? "warning" : "neutral"} compact>
              <CompactTable
                dense
                rows={coverage.promotions.recent_requests.slice(0, 8)}
                emptyLabel={errors.coverage ? "Coverage feed unavailable." : "No recent promotions."}
                getRowTone={(row) => (row.status === "PENDING" ? "warning" : row.status === "ACCEPTED" ? "positive" : "inactive")}
                columns={[
                  { key: "instrument", header: "Instrument", render: (row) => row.instrument },
                  { key: "score", header: "Score", render: (row) => row.score.toFixed(2) },
                  { key: "status", header: "Status", render: (row) => row.status },
                ]}
              />
            </Panel>

            <Panel title="Telemetry" priority="passive" tone="inactive" compact>
              <div className="metric-stack">
                <div className="metric-stack__row">
                  <span>Heartbeat</span>
                  <strong>{errors.telemetry ? "-" : formatAge(telemetry.heartbeat_age_ms)}</strong>
                </div>
                <div className="metric-stack__row">
                  <span>Price age</span>
                  <strong>{errors.telemetry ? "-" : formatAge(telemetry.last_price_age_ms)}</strong>
                </div>
                <div className="metric-stack__row">
                  <span>Stale runtimes</span>
                  <strong>{errors.telemetry ? "-" : telemetry.stale_runtime_count}</strong>
                </div>
                <div className="metric-stack__row">
                  <span>Top reject</span>
                  <strong>{errors.coverage ? "-" : topRejectionReason}</strong>
                </div>
                <div className="metric-stack__row">
                  <span>Tier 1 cap</span>
                  <strong>{errors.operatingLimits ? "-" : operatingLimits.coverage.max_instruments}</strong>
                </div>
              </div>
            </Panel>
          </div>
        }
      />

      <Panel title="Allocator Decisions" priority="passive" tone="inactive" compact>
        <CompactTable
          dense
          rows={coverage.trade_allocator.recent_decisions.slice(0, 10)}
          emptyLabel={errors.coverage ? "Coverage feed unavailable." : "No allocator decisions recorded."}
          getRowTone={(row) => (row.selected ? "positive" : "warning")}
          columns={[
            { key: "age", header: "Age", render: (row) => formatRelativeDuration(row.created_at) },
            { key: "strategy", header: "Strategy", render: (row) => row.strategy_name ?? "unknown" },
            { key: "instrument", header: "Instrument", render: (row) => row.instrument ?? "unknown" },
            { key: "result", header: "Result", render: (row) => (row.selected ? "selected" : "rejected") },
            { key: "reason", header: "Reason", render: (row) => row.reason_code ?? row.reason ?? "n/a" },
          ]}
        />
      </Panel>
    </main>
  );
}
