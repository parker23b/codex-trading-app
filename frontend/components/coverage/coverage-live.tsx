"use client";

import { useEffect, useMemo, useState } from "react";

import { CompactTable, DataIndicator, InspectorDrawer, Panel, SplitPanel, StatusPill, StatusStrip, type ConsoleTone } from "@/components/console/primitives";
import { getCoverageSummary, getFeedState, getOperationalTelemetry, getSystemOperatingLimits } from "@/lib/api";
import { formatInstrumentLabel, formatRelativeDuration } from "@/lib/format";
import { CoverageSummary, CoverageWatchlistEntry, FeedState, FeedStateResponse, OperationalTelemetry, SystemOperatingLimits } from "@/lib/types";

type CoverageResourceErrors = {
  coverage: string | null;
  telemetry: string | null;
  operatingLimits: string | null;
  feedState: string | null;
};

type CoverageLiveProps = {
  initialCoverage: CoverageSummary;
  initialTelemetry: OperationalTelemetry;
  initialOperatingLimits: SystemOperatingLimits;
  initialFeedState: FeedStateResponse;
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

function feedValueIncludes(feed: FeedState, ...tokens: string[]) {
  const values = [
    feed.stream_status,
    feed.price_source,
    feed.stream_reason?.code,
    feed.stream_reason?.label,
  ]
    .filter(Boolean)
    .map((value) => String(value).toUpperCase());

  return tokens.some((token) => values.some((value) => value.includes(token)));
}

function coverageStreamDisplay(row: CoverageWatchlistEntry, feed?: FeedState) {
  if (!feed) {
    return row.streamed
      ? {
          label: "Stream state unknown",
          tone: "warning" as const,
          title: "No feed-state row was returned for this streamed instrument.",
        }
      : {
          label: "Eligible",
          tone: "inactive" as const,
          title: "Instrument is in the watchlist but is not currently streaming.",
        };
  }

  const reasonLabel = feed.stream_reason?.label;
  const reasonDetail = feed.stream_reason?.operator_action;

  if (feedValueIncludes(feed, "DISCONNECTED", "FAILED", "UNAVAILABLE")) {
    return {
      label: reasonLabel ?? "Disconnected",
      tone: "negative" as const,
      title: reasonDetail ?? "Live stream is disconnected or unavailable for this instrument.",
    };
  }

  if (feedValueIncludes(feed, "POLL", "FALLBACK")) {
    return {
      label: reasonLabel ?? "Polling fallback",
      tone: "warning" as const,
      title: reasonDetail ?? "Fallback polling is active; this is not healthy live streaming.",
    };
  }

  if (feedValueIncludes(feed, "STALE")) {
    return {
      label: reasonLabel ?? "Stale",
      tone: "warning" as const,
      title: reasonDetail ?? "The latest stream tick is stale for this instrument.",
    };
  }

  if (feed.streaming_now && feed.last_tick_age_ms == null) {
    return {
      label: reasonLabel ?? "Stream state unknown",
      tone: "warning" as const,
      title: reasonDetail ?? "Stream coverage exists, but the latest tick timestamp is unavailable.",
    };
  }

  if (feed.stream_connected && feed.streaming_now) {
    return {
      label: reasonLabel ?? "Streaming",
      tone: "positive" as const,
      title: reasonDetail ?? "Live streaming is active for this instrument.",
    };
  }

  return {
    label: reasonLabel ?? (row.streamed ? "Stream not live" : "Eligible"),
    tone: row.streamed ? "warning" as const : "inactive" as const,
    title: reasonDetail ?? "This instrument is not currently receiving healthy live stream ticks.",
  };
}

function coverageWatchlistRowTone(row: CoverageWatchlistEntry, feed?: FeedState): ConsoleTone {
  const streamTone = coverageStreamDisplay(row, feed).tone;
  if (streamTone !== "positive") {
    return streamTone;
  }
  if (row.status !== "ACTIVE") {
    return "warning";
  }
  return "positive";
}

function coverageLastTickLabel(row: CoverageWatchlistEntry, feed?: FeedState) {
  if (feed?.last_tick_age_ms != null) {
    return formatAge(feed.last_tick_age_ms);
  }
  if (feed?.streaming_now) {
    return "Unknown";
  }
  if (feed && !feed.streaming_now) {
    return "No live tick";
  }
  if (row.streamed) {
    return "Unknown";
  }
  return row.last_streamed_at ? `${formatRelativeDuration(row.last_streamed_at)} ago` : "never";
}

export function CoverageLive({ initialCoverage, initialTelemetry, initialOperatingLimits, initialFeedState, initialErrors }: CoverageLiveProps) {
  const [coverage, setCoverage] = useState(initialCoverage);
  const [telemetry, setTelemetry] = useState(initialTelemetry);
  const [operatingLimits, setOperatingLimits] = useState(initialOperatingLimits);
  const [feedState, setFeedState] = useState(initialFeedState);
  const [errors, setErrors] = useState(initialErrors);
  const [allocatorDrawerOpen, setAllocatorDrawerOpen] = useState(false);

  useEffect(() => {
    setCoverage(initialCoverage);
    setTelemetry(initialTelemetry);
    setOperatingLimits(initialOperatingLimits);
    setFeedState(initialFeedState);
    setErrors(initialErrors);
  }, [initialCoverage, initialErrors, initialFeedState, initialOperatingLimits, initialTelemetry]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const [nextCoverage, nextTelemetry, nextOperatingLimits, nextFeedState] = await Promise.allSettled([
          getCoverageSummary(),
          getOperationalTelemetry(),
          getSystemOperatingLimits(),
          getFeedState(),
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
        if (nextFeedState.status === "fulfilled") {
          setFeedState(nextFeedState.value);
        }
        setErrors({
          coverage: nextCoverage.status === "rejected" ? (nextCoverage.reason instanceof Error ? nextCoverage.reason.message : "Failed to load coverage.") : null,
          telemetry: nextTelemetry.status === "rejected" ? (nextTelemetry.reason instanceof Error ? nextTelemetry.reason.message : "Failed to load telemetry.") : null,
          operatingLimits: nextOperatingLimits.status === "rejected" ? (nextOperatingLimits.reason instanceof Error ? nextOperatingLimits.reason.message : "Failed to load limits.") : null,
          feedState: nextFeedState.status === "rejected" ? (nextFeedState.reason instanceof Error ? nextFeedState.reason.message : "Failed to load feed state.") : null,
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
  const feedByInstrument = new Map(feedState.instruments.map((row) => [row.instrument, row]));

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          {
            label: "Strategy Watchlist",
            value: errors.coverage ? (
              <>
                -<DataIndicator state="error" message={errors.coverage} />
              </>
            ) : (
              `${coverage.streaming.active_instruments.length}/${operatingLimits.coverage.max_instruments || "-"}`
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
        className="layout-coverage items-start"
        left={
          <Panel title="Strategy Watchlist" subtitle="Eligible for streaming and strategy evaluation." priority="primary" tone={blockedReadiness.length ? "warning" : "positive"}>
            <CompactTable
              rows={activeUniverseRows}
              emptyLabel={errors.coverage ? "Coverage feed unavailable." : "No active Tier 1 instruments."}
              getRowTone={(row) => coverageWatchlistRowTone(row, feedByInstrument.get(row.instrument))}
              columns={[
                { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
                {
                  key: "stream",
                  header: "Stream",
                  render: (row) => {
                    const display = coverageStreamDisplay(row, feedByInstrument.get(row.instrument));
                    return <StatusPill label={display.label} tone={display.tone} title={display.title} />;
                  },
                },
                {
                  key: "tick",
                  header: "Last Tick",
                  render: (row) => coverageLastTickLabel(row, feedByInstrument.get(row.instrument)),
                },
                {
                  key: "spread",
                  header: "Spread",
                  render: (row) => feedByInstrument.get(row.instrument)?.spread ?? "n/a",
                },
                {
                  key: "eligibility",
                  header: "Evaluation",
                  render: (row) => {
                    const feed = feedByInstrument.get(row.instrument);
                    return <StatusPill label={feed?.strategies_may_evaluate ? "May evaluate" : feed?.entry_eligibility_reason?.label ?? "Blocked"} tone={feed?.strategies_may_evaluate ? "positive" : "warning"} />;
                  },
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
                { key: "quote", header: "Quote", render: (row) => formatAge(row.last_price_age_ms) },
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

            <Panel
              title="Telemetry"
              priority="passive"
              tone="inactive"
              compact
              actions={
                <button type="button" className="console-button console-button--ghost" onClick={() => setAllocatorDrawerOpen(true)}>
                  Allocator Decisions
                </button>
              }
            >
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

      <InspectorDrawer
        title="Allocator Decisions"
        subtitle="Recent allocator selections and rejects."
        open={allocatorDrawerOpen}
        onClose={() => setAllocatorDrawerOpen(false)}
      >
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
      </InspectorDrawer>
    </main>
  );
}
