"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import {
  getAllocationAlerts,
  getAllocationExposureSummary,
  getBrokerAuthStatus,
  getControlPlaneSummary,
  getCoverageSummary,
  getDomainEvents,
  getExecutions,
  getLiveInstrumentChart,
  getOperationalTelemetry,
  getOpenPositions,
  getStreamHealth,
  getStrategies,
} from "@/lib/api";
import {
  buildLiveSystemViewModel,
  type LiveActivityItem,
  type LiveInstrumentItem,
  type LiveSelection,
  type LiveStatusChip,
  type LiveStrategyItem,
} from "@/lib/live-system-view";
import { StatusPill } from "@/components/console/primitives";
import type { LiveChartResponse } from "@/lib/types";
import { formatInstrumentLabel } from "@/lib/format";

type LiveSystemViewProps = {
  initialData: {
    positions: Awaited<ReturnType<typeof getOpenPositions>>;
    executions: Awaited<ReturnType<typeof getExecutions>>;
    strategies: Awaited<ReturnType<typeof getStrategies>>;
    brokerAuth: Awaited<ReturnType<typeof getBrokerAuthStatus>>;
    streamHealth: Awaited<ReturnType<typeof getStreamHealth>>;
    coverage: Awaited<ReturnType<typeof getCoverageSummary>>;
    controlPlane: Awaited<ReturnType<typeof getControlPlaneSummary>>;
    telemetry: Awaited<ReturnType<typeof getOperationalTelemetry>>;
    exposure: Awaited<ReturnType<typeof getAllocationExposureSummary>>;
    alerts: Awaited<ReturnType<typeof getAllocationAlerts>>;
    events: Awaited<ReturnType<typeof getDomainEvents>>;
  };
  initialErrors: {
    positions: string | null;
    executions: string | null;
    strategies: string | null;
    brokerAuth: string | null;
    streamHealth: string | null;
    coverage: string | null;
    controlPlane: string | null;
    telemetry: string | null;
    exposure: string | null;
    alerts: string | null;
    events: string | null;
  };
};

function toneClassName(tone: LiveStatusChip["tone"]) {
  if (tone === "positive") {
    return "is-positive";
  }
  if (tone === "warning") {
    return "is-warning";
  }
  if (tone === "negative") {
    return "is-negative";
  }
  if (tone === "inactive") {
    return "is-inactive";
  }
  return "is-neutral";
}

function selectionLookupKey(selection: LiveSelection) {
  if (!selection) {
    return "system";
  }
  if (selection.type === "anomaly") {
    return selection.id;
  }
  return `${selection.type}:${selection.id}`;
}

function instrumentBarWidth(instrument: LiveInstrumentItem) {
  const base = instrument.riskPercent ?? instrument.significance;
  return `${Math.max(14, Math.min(100, base * 18 + instrument.activeStrategyCount * 8 + instrument.activePositionCount * 10))}%`;
}

function modeTone(mode: LiveStrategyItem["mode"]) {
  if (mode === "blocked") {
    return "negative" as const;
  }
  if (mode === "degraded" || mode === "constrained") {
    return "warning" as const;
  }
  if (mode === "holding" || mode === "scaling" || mode === "waiting") {
    return "positive" as const;
  }
  return "inactive" as const;
}

function chartX(index: number, count: number) {
  return count <= 1 ? 20 : 20 + (index / (count - 1)) * 560;
}

function chartY(value: number, min: number, max: number) {
  const span = Math.max(max - min, 1e-9);
  return 220 - ((value - min) / span) * 180;
}

export function LiveSystemView({ initialData, initialErrors }: LiveSystemViewProps) {
  const [data, setData] = useState(initialData);
  const [errors, setErrors] = useState(initialErrors);
  const [refreshedAt, setRefreshedAt] = useState(() => new Date().toISOString());
  const [assetClassFilter, setAssetClassFilter] = useState("All");
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [showAnomaliesOnly, setShowAnomaliesOnly] = useState(false);
  const [autoFollowActivity, setAutoFollowActivity] = useState(true);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [selection, setSelection] = useState<LiveSelection>(null);
  const [chartInstrument, setChartInstrument] = useState("");
  const [chartData, setChartData] = useState<LiveChartResponse | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const dataRef = useRef(data);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  useEffect(() => {
    setData(initialData);
    setErrors(initialErrors);
    setRefreshedAt(new Date().toISOString());
  }, [initialData, initialErrors]);

  const model = useMemo(
    () =>
      buildLiveSystemViewModel({
        ...data,
        errors,
        refreshedAt,
      }),
    [data, errors, refreshedAt],
  );

  useEffect(() => {
    setSelection((current) => current ?? model.defaultSelection);
  }, [model.defaultSelection]);

  useEffect(() => {
    const lookupKey = selectionLookupKey(selection);
    if (model.inspection[lookupKey]) {
      return;
    }
    setSelection(model.defaultSelection);
  }, [model.defaultSelection, model.inspection, selection]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      const refreshIso = new Date().toISOString();
      const [
        nextPositions,
        nextExecutions,
        nextStrategies,
        nextBrokerAuth,
        nextStreamHealth,
        nextCoverage,
        nextControlPlane,
        nextTelemetry,
        nextExposure,
        nextAlerts,
        nextEvents,
      ] = await Promise.allSettled([
        getOpenPositions(),
        getExecutions(120),
        getStrategies(),
        getBrokerAuthStatus(),
        getStreamHealth(),
        getCoverageSummary(),
        getControlPlaneSummary(),
        getOperationalTelemetry(),
        getAllocationExposureSummary(),
        getAllocationAlerts({ limit: 20 }),
        getDomainEvents({ limit: 80 }),
      ]);

      if (cancelled) {
        return;
      }

      let nextResolvedData = dataRef.current;
      setData((current) => {
        nextResolvedData = {
          positions: nextPositions.status === "fulfilled" ? nextPositions.value : current.positions,
          executions: nextExecutions.status === "fulfilled" ? nextExecutions.value : current.executions,
          strategies: nextStrategies.status === "fulfilled" ? nextStrategies.value : current.strategies,
          brokerAuth: nextBrokerAuth.status === "fulfilled" ? nextBrokerAuth.value : current.brokerAuth,
          streamHealth: nextStreamHealth.status === "fulfilled" ? nextStreamHealth.value : current.streamHealth,
          coverage: nextCoverage.status === "fulfilled" ? nextCoverage.value : current.coverage,
          controlPlane: nextControlPlane.status === "fulfilled" ? nextControlPlane.value : current.controlPlane,
          telemetry: nextTelemetry.status === "fulfilled" ? nextTelemetry.value : current.telemetry,
          exposure: nextExposure.status === "fulfilled" ? nextExposure.value : current.exposure,
          alerts: nextAlerts.status === "fulfilled" ? nextAlerts.value : current.alerts,
          events: nextEvents.status === "fulfilled" ? nextEvents.value : current.events,
        };
        return nextResolvedData;
      });

      const nextResolvedErrors = {
        positions: nextPositions.status === "rejected" ? (nextPositions.reason instanceof Error ? nextPositions.reason.message : "Failed to load positions.") : null,
        executions: nextExecutions.status === "rejected" ? (nextExecutions.reason instanceof Error ? nextExecutions.reason.message : "Failed to load executions.") : null,
        strategies: nextStrategies.status === "rejected" ? (nextStrategies.reason instanceof Error ? nextStrategies.reason.message : "Failed to load strategies.") : null,
        brokerAuth: nextBrokerAuth.status === "rejected" ? (nextBrokerAuth.reason instanceof Error ? nextBrokerAuth.reason.message : "Failed to load broker status.") : null,
        streamHealth: nextStreamHealth.status === "rejected" ? (nextStreamHealth.reason instanceof Error ? nextStreamHealth.reason.message : "Failed to load stream health.") : null,
        coverage: nextCoverage.status === "rejected" ? (nextCoverage.reason instanceof Error ? nextCoverage.reason.message : "Failed to load coverage.") : null,
        controlPlane: nextControlPlane.status === "rejected" ? (nextControlPlane.reason instanceof Error ? nextControlPlane.reason.message : "Failed to load control plane.") : null,
        telemetry: nextTelemetry.status === "rejected" ? (nextTelemetry.reason instanceof Error ? nextTelemetry.reason.message : "Failed to load telemetry.") : null,
        exposure: nextExposure.status === "rejected" ? (nextExposure.reason instanceof Error ? nextExposure.reason.message : "Failed to load exposure.") : null,
        alerts: nextAlerts.status === "rejected" ? (nextAlerts.reason instanceof Error ? nextAlerts.reason.message : "Failed to load allocator alerts.") : null,
        events: nextEvents.status === "rejected" ? (nextEvents.reason instanceof Error ? nextEvents.reason.message : "Failed to load domain events.") : null,
      };

      setErrors(nextResolvedErrors);
      setRefreshedAt(refreshIso);

      if (autoFollowActivity && selection?.type === "activity") {
        const nextModel = buildLiveSystemViewModel({
          ...nextResolvedData,
          errors: nextResolvedErrors,
          refreshedAt: refreshIso,
        });
        if (nextModel.activity[0]) {
          setSelection({ type: "activity", id: nextModel.activity[0].id });
        }
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 7000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [autoFollowActivity, selection]);

  const normalizedSearch = deferredSearch.trim().toLowerCase();
  const filteredInstruments = useMemo(
    () =>
      model.instruments.filter((instrument) => {
        if (assetClassFilter !== "All" && instrument.assetClass !== assetClassFilter) {
          return false;
        }
        if (showActiveOnly && instrument.state !== "active" && instrument.state !== "degraded" && instrument.state !== "blocked") {
          return false;
        }
        if (showAnomaliesOnly && !instrument.isAnomalous) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return (
          instrument.label.toLowerCase().includes(normalizedSearch) ||
          instrument.canonical.toLowerCase().includes(normalizedSearch) ||
          instrument.activeStrategies.some((strategy) => strategy.toLowerCase().includes(normalizedSearch))
        );
      }),
    [assetClassFilter, model.instruments, normalizedSearch, showActiveOnly, showAnomaliesOnly],
  );

  const groupedInstruments = useMemo(() => {
    const groups = new Map<string, LiveInstrumentItem[]>();
    for (const instrument of filteredInstruments) {
      const existing = groups.get(instrument.assetClass) ?? [];
      existing.push(instrument);
      groups.set(instrument.assetClass, existing);
    }
    return [...groups.entries()];
  }, [filteredInstruments]);

  const activeChartInstruments = useMemo(
    () => model.instruments.filter((instrument) => instrument.state === "active" || instrument.state === "degraded" || instrument.state === "blocked"),
    [model.instruments],
  );

  useEffect(() => {
    if (chartInstrument || !activeChartInstruments[0]) {
      return;
    }
    setChartInstrument(activeChartInstruments[0].id);
  }, [activeChartInstruments, chartInstrument]);

  useEffect(() => {
    if (!chartInstrument) {
      return;
    }
    let cancelled = false;
    getLiveInstrumentChart(chartInstrument)
      .then((payload) => {
        if (!cancelled) {
          setChartData(payload);
          setChartError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setChartError(error instanceof Error ? error.message : "Chart unavailable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chartInstrument, refreshedAt]);

  const chartExtents = useMemo(() => {
    const candles = chartData?.candles.slice(-80) ?? [];
    const lows = candles.map((candle) => candle.low);
    const highs = candles.map((candle) => candle.high);
    return {
      candles,
      low: lows.length ? Math.min(...lows) : 0,
      high: highs.length ? Math.max(...highs) : 1,
    };
  }, [chartData]);

  const filteredStrategies = useMemo(
    () =>
      model.strategies.filter((strategy) => {
        if (showActiveOnly && strategy.mode === "idle") {
          return false;
        }
        if (showAnomaliesOnly && !strategy.isAnomalous) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return (
          strategy.name.toLowerCase().includes(normalizedSearch) ||
          strategy.activeInstruments.some((instrument) => instrument.toLowerCase().includes(normalizedSearch))
        );
      }),
    [model.strategies, normalizedSearch, showActiveOnly, showAnomaliesOnly],
  );

  const filteredActivity = useMemo(
    () =>
      model.activity.filter((item) => {
        if (showAnomaliesOnly && item.tone !== "warning" && item.tone !== "negative") {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return (
          item.title.toLowerCase().includes(normalizedSearch) ||
          item.detail.toLowerCase().includes(normalizedSearch) ||
          item.relatedStrategy?.toLowerCase().includes(normalizedSearch) ||
          item.relatedInstrument?.toLowerCase().includes(normalizedSearch)
        );
      }),
    [model.activity, normalizedSearch, showAnomaliesOnly],
  );

  const inspection = model.inspection[selectionLookupKey(selection)] ?? model.inspection.system;

  return (
    <main className="console-page live-system-page">
      <section className="live-system-hero">
        <div className="live-system-hero__copy">
          <span className="live-system-kicker">Live System View</span>
          <h1>Observation layer for an autonomous trading system.</h1>
          <p>
            This screen is for trust and pattern recognition: what the system is seeing, what it is doing,
            and whether live behaviour still looks normal.
          </p>
        </div>
        <div className="live-system-hero__context" aria-live="polite">
          <strong>{model.anomalies.length ? `${model.anomalies.length} unusual signal${model.anomalies.length === 1 ? "" : "s"}` : "Nominal live posture"}</strong>
          <span>{model.trustRail.find((item) => item.id === "updated")?.meta}</span>
        </div>
      </section>

      <section className="live-trust-rail" aria-label="Live system trust rail">
        {model.trustRail.map((item, index) => (
          <article
            key={item.id}
            className={`live-trust-chip ${toneClassName(item.tone)}${index === 0 ? " live-trust-chip--primary" : ""}`}
          >
            <div className="live-trust-chip__topline">
              <span>{item.label}</span>
              <em>{item.source}</em>
            </div>
            <strong>{item.value}</strong>
            <p>{item.meta}</p>
          </article>
        ))}
      </section>

      {model.dataWarnings.length ? (
        <section className="live-data-warning" role="status" aria-live="polite">
          <strong>Some live sources are degraded.</strong>
          <span>{model.dataWarnings[0]}</span>
        </section>
      ) : null}

      <section className="live-system-workspace">
        <section className="live-observation-stage" aria-label="Main live observation area">
          <div className="live-toolbar">
            <div className="live-toolbar__group">
              <label className="live-field">
                <span>Search</span>
                <input
                  type="search"
                  className="console-input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Instrument, strategy, or signal"
                  aria-label="Search instrument, strategy, or signal"
                />
              </label>

              <label className="live-field">
                <span>Asset class</span>
                <select
                  className="console-select"
                  value={assetClassFilter}
                  onChange={(event) => setAssetClassFilter(event.target.value)}
                  aria-label="Filter by asset class"
                >
                  <option value="All">All</option>
                  {model.assetClasses.map((assetClass) => (
                    <option key={assetClass} value={assetClass}>
                      {assetClass}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="live-toolbar__group">
              <label className="console-toggle">
                <input type="checkbox" checked={showActiveOnly} onChange={() => setShowActiveOnly((current) => !current)} />
                Active only
              </label>
              <label className="console-toggle">
                <input type="checkbox" checked={showAnomaliesOnly} onChange={() => setShowAnomaliesOnly((current) => !current)} />
                Unusual only
              </label>
              <label className="console-toggle">
                <input
                  type="checkbox"
                  checked={autoFollowActivity}
                  onChange={() => setAutoFollowActivity((current) => !current)}
                />
                Auto-follow activity
              </label>
            </div>
          </div>

          <div className="live-observation-grid">
            <section className="live-panel live-panel--chart" aria-label="Selected active instrument chart">
              <div className="live-panel__header">
                <div>
                  <span className="live-system-kicker">Backend chart</span>
                  <h2>{chartInstrument ? formatInstrumentLabel(chartInstrument) : "Active instrument"} candles</h2>
                </div>
                <select className="console-select" value={chartInstrument} onChange={(event) => setChartInstrument(event.target.value)}>
                  {activeChartInstruments.map((instrument) => (
                    <option key={instrument.id} value={instrument.id}>
                      {instrument.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="live-chart-layout">
                <div className="live-candle-chart">
                  {chartError ? (
                    <div className="live-empty-state">{chartError}</div>
                  ) : chartData?.data_state === "UNSUPPORTED" ? (
                    <div className="live-empty-state">
                      {chartData.reason_detail?.label ?? "Chart unavailable for this instrument."}
                      <br />
                      {chartData.reason_detail?.operator_action ?? "Select another active instrument."}
                    </div>
                  ) : chartExtents.candles.length ? (
                    <svg viewBox="0 0 600 250" role="img" aria-label="Candlestick chart">
                      <line x1="20" y1="230" x2="580" y2="230" className="live-chart-axis" />
                      {chartExtents.candles.map((candle, index) => {
                        const x = chartX(index, chartExtents.candles.length);
                        const openY = chartY(candle.open, chartExtents.low, chartExtents.high);
                        const closeY = chartY(candle.close, chartExtents.low, chartExtents.high);
                        const highY = chartY(candle.high, chartExtents.low, chartExtents.high);
                        const lowY = chartY(candle.low, chartExtents.low, chartExtents.high);
                        const up = candle.close >= candle.open;
                        return (
                          <g key={`${candle.time}-${index}`} className={up ? "live-candle live-candle--up" : "live-candle live-candle--down"}>
                            <line x1={x} x2={x} y1={highY} y2={lowY} />
                            <rect x={x - 2.5} y={Math.min(openY, closeY)} width="5" height={Math.max(2, Math.abs(closeY - openY))} />
                          </g>
                        );
                      })}
                      {(chartData?.markers ?? []).slice(0, 24).map((marker, index) => {
                        const markerTime = Number(marker.time ?? 0);
                        const candleIndex = Math.max(0, chartExtents.candles.findIndex((candle) => candle.time >= markerTime));
                        const x = chartX(candleIndex === -1 ? chartExtents.candles.length - 1 : candleIndex, chartExtents.candles.length);
                        const y = 24 + (index % 4) * 12;
                        const status = String(marker.status ?? "selected");
                        return <circle key={`marker-${index}-${markerTime}`} cx={x} cy={y} r="4" className={`live-chart-marker live-chart-marker--${status}`} />;
                      })}
                    </svg>
                  ) : (
                    <div className="live-empty-state">
                      {chartData?.reason_detail?.label ?? "No candle data is available for the selected instrument."}
                      <br />
                      {chartData?.reason_detail?.operator_action ?? "Wait for backend candle data or choose another instrument."}
                    </div>
                  )}
                </div>
                <aside className="live-feed-state">
                  <div><span>Stream</span><strong>{String(chartData?.feed_state.stream_reason?.label ?? chartData?.feed_state.stream_status ?? "unknown")}</strong></div>
                  <div><span>Last tick</span><strong>{chartData?.feed_state.last_tick_age_ms == null ? "n/a" : `${Number(chartData.feed_state.last_tick_age_ms).toFixed(0)}ms`}</strong></div>
                  <div><span>Spread</span><strong>{chartData?.feed_state.spread == null ? "n/a" : String(chartData.feed_state.spread)}</strong></div>
                  <div><span>Source</span><strong>{String(chartData?.feed_state.price_source ?? "backend")}</strong></div>
                  <div><span>Entry</span><strong>{String(chartData?.feed_state.entry_eligibility_reason?.label ?? chartData?.feed_state.entry_eligibility ?? "unknown")}</strong></div>
                  <div><span>Candidates</span><strong>{chartData?.markers.length ?? 0}</strong></div>
                  <div><span>Positions</span><strong>{chartData?.position_overlays.length ?? 0}</strong></div>
                  <div><span>Executions</span><strong>{chartData?.execution_markers.length ?? 0}</strong></div>
                </aside>
              </div>
            </section>

            <section className="live-panel live-panel--activity" aria-labelledby="live-activity-heading">
              <div className="live-panel__header">
                <div>
                  <span className="live-system-kicker">System activity stream</span>
                  <h2 id="live-activity-heading">Operational tape</h2>
                </div>
                <p>Human-readable behaviour updates, grouped into a calmer feed.</p>
              </div>

              <div className="live-activity-list" role="list">
                {filteredActivity.length ? (
                  filteredActivity.map((item: LiveActivityItem) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`live-activity-item ${toneClassName(item.tone)}${selection?.type === "activity" && selection.id === item.id ? " is-selected" : ""}`}
                      onClick={() => setSelection({ type: "activity", id: item.id })}
                    >
                      <div className="live-activity-item__meta">
                        <span>{item.relativeTime}</span>
                        <span>{item.source}</span>
                      </div>
                      <strong>{item.title}</strong>
                      <p>{item.detail}</p>
                      {item.groupCount > 1 ? <span className="live-activity-item__count">{item.groupCount} similar</span> : null}
                    </button>
                  ))
                ) : (
                  <div className="live-empty-state">
                    No live activity matches the current filters. Missing activity is shown honestly rather than replaced with synthetic calm.
                  </div>
                )}
              </div>
            </section>

            <section className="live-panel live-panel--map" aria-labelledby="live-map-heading">
              <div className="live-panel__header">
                <div>
                  <span className="live-system-kicker">Instrument / exposure map</span>
                  <h2 id="live-map-heading">What the system is engaging with</h2>
                </div>
                <p>Asset lanes make concentration, blocked markets, and multi-strategy clustering easy to spot.</p>
              </div>

              <div className="live-instrument-lanes">
                {groupedInstruments.length ? (
                  groupedInstruments.map(([assetClass, instruments]) => (
                    <section key={assetClass} className="live-instrument-lane" aria-label={`${assetClass} instruments`}>
                      <header className="live-instrument-lane__header">
                        <strong>{assetClass}</strong>
                        <span>{instruments.length} observed</span>
                      </header>

                      <div className="live-instrument-lane__items">
                        {instruments.map((instrument) => (
                          <button
                            key={instrument.id}
                            type="button"
                            className={`live-instrument-tile ${toneClassName(instrument.tone)}${selection?.type === "instrument" && selection.id === instrument.id ? " is-selected" : ""}`}
                            onClick={() => setSelection({ type: "instrument", id: instrument.id })}
                          >
                            <span className="live-instrument-tile__bar" style={{ width: instrumentBarWidth(instrument) }} aria-hidden="true" />
                            <div className="live-instrument-tile__header">
                              <div>
                                <strong>{instrument.label}</strong>
                                <span>{instrument.canonical}</span>
                              </div>
                              <StatusPill label={instrument.state} tone={instrument.tone} quiet />
                            </div>
                            <div className="live-instrument-tile__body">
                              <div>
                                <span>Bias</span>
                                <strong>{instrument.bias}</strong>
                              </div>
                              <div>
                                <span>Live risk</span>
                                <strong>{instrument.riskPercent == null ? "Unknown" : `${instrument.riskPercent.toFixed(2)}%`}</strong>
                              </div>
                              <div>
                                <span>Strategies</span>
                                <strong>{instrument.activeStrategyCount}</strong>
                              </div>
                            </div>
                            <p>{instrument.constraint ?? instrument.whyActive}</p>
                          </button>
                        ))}
                      </div>
                    </section>
                  ))
                ) : (
                  <div className="live-empty-state">
                    No instruments match the current filters. If live coverage is unavailable, this view stays incomplete rather than implying healthy inactivity.
                  </div>
                )}
              </div>
            </section>

            <section className="live-panel live-panel--strategy" aria-labelledby="live-strategy-heading">
              <div className="live-panel__header">
                <div>
                  <span className="live-system-kicker">Strategy behaviour layer</span>
                  <h2 id="live-strategy-heading">How runtimes are behaving</h2>
                </div>
                <p>Behavioural posture is prioritised over config detail so the operator can tell what the system is trying to do.</p>
              </div>

              <div className="live-strategy-list" role="list">
                {filteredStrategies.length ? (
                  filteredStrategies.map((strategy) => (
                    <button
                      key={strategy.id}
                      type="button"
                      className={`live-strategy-item ${toneClassName(strategy.tone)}${selection?.type === "strategy" && selection.id === strategy.id ? " is-selected" : ""}`}
                      onClick={() => setSelection({ type: "strategy", id: strategy.id })}
                    >
                      <div className="live-strategy-item__header">
                        <strong>{strategy.name}</strong>
                        <StatusPill label={strategy.mode} tone={modeTone(strategy.mode)} />
                      </div>
                      <p>{strategy.summary}</p>
                      <div className="live-strategy-item__meta">
                        <span>{strategy.activeInstruments.length ? strategy.activeInstruments.join(", ") : "No live instruments"}</span>
                        <span>{strategy.runtimeCount} runtime{strategy.runtimeCount === 1 ? "" : "s"}</span>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="live-empty-state">No strategies match the current filters.</div>
                )}
              </div>
            </section>

            <section className="live-panel live-panel--anomaly" aria-labelledby="live-anomaly-heading">
              <div className="live-panel__header">
                <div>
                  <span className="live-system-kicker">Unusual activity</span>
                  <h2 id="live-anomaly-heading">This deserves attention</h2>
                </div>
                <p>Ranked operator-facing signals with context about why they matter and what they affect.</p>
              </div>

              <div className="live-anomaly-list" role="list">
                {model.anomalies.length ? (
                  model.anomalies.map((anomaly) => (
                    <button
                      key={anomaly.id}
                      type="button"
                      className={`live-anomaly-item ${toneClassName(anomaly.tone)}${selection?.type === "anomaly" && selection.id === anomaly.id ? " is-selected" : ""}`}
                      onClick={() => setSelection({ type: "anomaly", id: anomaly.id })}
                    >
                      <div className="live-anomaly-item__header">
                        <strong>{anomaly.title}</strong>
                        <span>{anomaly.source}</span>
                      </div>
                      <p>{anomaly.explanation}</p>
                      <div className="live-anomaly-item__footer">
                        <span>{anomaly.whyItMatters}</span>
                        <span>{anomaly.affects.length ? anomaly.affects.join(", ") : "System-wide"}</span>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="live-empty-state live-empty-state--positive">
                    No unusual activity is currently ranked above the screen’s attention threshold.
                  </div>
                )}
              </div>
            </section>
          </div>
        </section>

        <aside className="live-inspector" aria-label="Contextual inspection panel">
          <div className={`live-inspector__shell ${toneClassName(inspection.tone)}`}>
            <div className="live-inspector__header">
              <div>
                <span className="live-system-kicker">{inspection.kicker}</span>
                <h2>{inspection.title}</h2>
                <p>{inspection.subtitle}</p>
              </div>
              <StatusPill label={inspection.status} tone={inspection.tone} />
            </div>

            <div className="live-inspector__summary">
              <div>
                <span>Freshness</span>
                <strong>{inspection.freshness}</strong>
              </div>
              <div>
                <span>Source</span>
                <strong>{inspection.source}</strong>
              </div>
            </div>

            <div className="live-inspector__section">
              {inspection.sections.map((section) => (
                <div key={section.label} className="live-inspector__metric">
                  <span>{section.label}</span>
                  <strong>{section.value}</strong>
                </div>
              ))}
            </div>

            <div className="live-inspector__section">
              <h3>Related context</h3>
              {inspection.related.length ? (
                <ul className="live-inspector__list">
                  {inspection.related.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div className="live-empty-state">No related context is available for this selection yet.</div>
              )}
            </div>

            <div className="live-inspector__section">
              <h3>Recent notes</h3>
              {inspection.recentNotes.length ? (
                <ul className="live-inspector__list">
                  {inspection.recentNotes.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div className="live-empty-state">No recent supporting activity is available.</div>
              )}
            </div>

            <div className="live-inspector__section">
              <h3>Canonical identifiers</h3>
              {inspection.identifiers.length ? (
                <div className="live-identifiers">
                  {inspection.identifiers.map((item) => (
                    <code key={item}>{item}</code>
                  ))}
                </div>
              ) : (
                <div className="live-empty-state">No canonical identifiers are available.</div>
              )}
            </div>

            <div className="live-inspector__section">
              <h3>Deeper diagnostics</h3>
              <div className="live-inspector__links">
                {inspection.links.map((link) => (
                  <Link key={link.href + link.label} href={link.href} className="console-chip">
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
