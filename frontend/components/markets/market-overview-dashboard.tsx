"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { CompactTable, DataIndicator, Panel, SplitPanel, StatusPill, StatusStrip, StickyToolbar } from "@/components/console/primitives";
import {
  addShortlistInstrument,
  addStrategyWatchlistInstruments,
  getMarketCatalogue,
  getMarketOverview,
  getStrategyWatchlist,
  removeShortlistInstrument,
} from "@/lib/api";
import { formatInstrumentLabel } from "@/lib/format";
import { MarketCatalogueInstrument, MarketCatalogueResponse, MarketCategoryOverviewResponse, StrategyWatchlistResponse } from "@/lib/types";

type MarketOverviewDashboardProps = {
  initialOverview: MarketCategoryOverviewResponse;
  initialOverviewError: string | null;
  initialCatalogue: MarketCatalogueResponse;
  initialCatalogueError: string | null;
  initialStrategyWatchlist: StrategyWatchlistResponse;
  initialStrategyWatchlistError: string | null;
};

const ASSET_CLASSES = ["ALL", "FOREX", "INDICES", "COMMODITIES", "STOCKS", "CRYPTO"];

function rowTone(row: MarketCatalogueInstrument) {
  if (row.streaming_now) {
    return "positive" as const;
  }
  if (row.in_strategy_watchlist) {
    return "warning" as const;
  }
  if (row.shortlisted) {
    return "neutral" as const;
  }
  return "inactive" as const;
}

function canAdd(row: MarketCatalogueInstrument, limit: number, activeCount: number) {
  if (row.in_strategy_watchlist) {
    return "Already in strategy watchlist.";
  }
  if (limit > 0 && activeCount >= limit) {
    return `Strategy watchlist limit reached (${limit}).`;
  }
  return null;
}

export function MarketOverviewDashboard({
  initialOverview,
  initialOverviewError,
  initialCatalogue,
  initialCatalogueError,
  initialStrategyWatchlist,
  initialStrategyWatchlistError,
}: MarketOverviewDashboardProps) {
  const [catalogue, setCatalogue] = useState(initialCatalogue);
  const [strategyWatchlist, setStrategyWatchlist] = useState(initialStrategyWatchlist);
  const [overviewError, setOverviewError] = useState(initialOverviewError);
  const [catalogueError, setCatalogueError] = useState(initialCatalogueError);
  const [watchlistError, setWatchlistError] = useState(initialStrategyWatchlistError);
  const [search, setSearch] = useState("");
  const [assetClass, setAssetClass] = useState("FOREX");
  const [currency, setCurrency] = useState("ALL");
  const [forexMajorsOnly, setForexMajorsOnly] = useState(true);
  const [tradableOnly, setTradableOnly] = useState(false);
  const [shortlistedOnly, setShortlistedOnly] = useState(false);
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [streamingOnly, setStreamingOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setCatalogue(initialCatalogue);
    setStrategyWatchlist(initialStrategyWatchlist);
    setOverviewError(initialOverviewError);
    setCatalogueError(initialCatalogueError);
    setWatchlistError(initialStrategyWatchlistError);
  }, [initialCatalogue, initialCatalogueError, initialOverviewError, initialStrategyWatchlist, initialStrategyWatchlistError]);

  const currencies = useMemo(
    () => ["ALL", ...Array.from(new Set(catalogue.instruments.map((item) => item.quote_currency || item.currency).filter(Boolean) as string[])).sort()],
    [catalogue.instruments],
  );

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return catalogue.instruments
      .filter((row) => {
        if (assetClass !== "ALL" && row.asset_class !== assetClass) {
          return false;
        }
        if (currency !== "ALL" && row.quote_currency !== currency && row.currency !== currency) {
          return false;
        }
        if (forexMajorsOnly && !row.forex_major) {
          return false;
        }
        if (tradableOnly && !row.tradable) {
          return false;
        }
        if (shortlistedOnly && !row.shortlisted) {
          return false;
        }
        if (watchlistOnly && !row.in_strategy_watchlist) {
          return false;
        }
        if (streamingOnly && !row.streaming_now) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return (
          row.name.toLowerCase().includes(normalizedSearch) ||
          row.symbol.toLowerCase().includes(normalizedSearch) ||
          row.instrument.toLowerCase().includes(normalizedSearch) ||
          row.strategy_compatibility.some((strategy) => strategy.toLowerCase().includes(normalizedSearch))
        );
      })
      .sort((left, right) => Number(right.streaming_now) - Number(left.streaming_now) || Number(right.in_strategy_watchlist) - Number(left.in_strategy_watchlist) || Number(right.shortlisted) - Number(left.shortlisted) || left.symbol.localeCompare(right.symbol));
  }, [assetClass, catalogue.instruments, currency, forexMajorsOnly, search, shortlistedOnly, streamingOnly, tradableOnly, watchlistOnly]);

  const shortlistedRows = catalogue.instruments.filter((row) => row.shortlisted);
  const strategyRowsById = new Set(strategyWatchlist.instruments.map((row) => row.instrument));

  const refreshAll = async () => {
    const [nextCatalogue, nextWatchlist, nextOverview] = await Promise.allSettled([
      getMarketCatalogue(),
      getStrategyWatchlist(),
      getMarketOverview("forex"),
    ]);
    if (nextCatalogue.status === "fulfilled") {
      setCatalogue(nextCatalogue.value);
      setCatalogueError(null);
    } else {
      setCatalogueError(nextCatalogue.reason instanceof Error ? nextCatalogue.reason.message : "Catalogue unavailable.");
    }
    if (nextWatchlist.status === "fulfilled") {
      setStrategyWatchlist(nextWatchlist.value);
      setWatchlistError(null);
    } else {
      setWatchlistError(nextWatchlist.reason instanceof Error ? nextWatchlist.reason.message : "Strategy watchlist unavailable.");
    }
    setOverviewError(nextOverview.status === "rejected" ? (nextOverview.reason instanceof Error ? nextOverview.reason.message : "Market overview unavailable.") : null);
  };

  const toggleShortlist = (instrumentId: string, currentlyShortlisted: boolean) => {
    startTransition(async () => {
      try {
        if (currentlyShortlisted) {
          await removeShortlistInstrument(instrumentId);
          setStatusMessage(`${formatInstrumentLabel(instrumentId)} removed from shortlist.`);
        } else {
          await addShortlistInstrument(instrumentId);
          setStatusMessage(`${formatInstrumentLabel(instrumentId)} added to shortlist.`);
        }
        await refreshAll();
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Shortlist update failed.");
      }
    });
  };

  const addToStrategyWatchlist = (instrumentIds: string[]) => {
    startTransition(async () => {
      try {
        const result = await addStrategyWatchlistInstruments(instrumentIds);
        const skippedReasons = result.skipped
          .slice(0, 3)
          .map((item) => `${formatInstrumentLabel(item.instrument)}: ${item.reason_detail?.label ?? item.reason}`)
          .join(" · ");
        setStatusMessage(`${result.added.length} added, ${result.skipped.length} blocked.${skippedReasons ? ` ${skippedReasons}` : ""}`);
        setSelectedIds([]);
        await refreshAll();
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Strategy watchlist update failed.");
      }
    });
  };

  const selectedRows = catalogue.instruments.filter((row) => selectedIds.includes(row.instrument));
  const addableShortlist = shortlistedRows.filter((row) => !canAdd(row, strategyWatchlist.limit, strategyWatchlist.active_count));

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          { label: "Catalogue", value: catalogue.summary.total_count, tone: catalogueError ? "inactive" : "neutral", meta: catalogueError ?? "available markets" },
          { label: "Shortlist", value: catalogue.summary.shortlisted_count, tone: "neutral", meta: "operator interest" },
          {
            label: "Strategy Watchlist",
            value: `${strategyWatchlist.active_count}/${strategyWatchlist.limit || "-"}`,
            tone: watchlistError ? "inactive" : strategyWatchlist.cap_exceeded_by_protective_coverage ? "warning" : strategyWatchlist.active_count >= strategyWatchlist.limit ? "warning" : "positive",
            meta: watchlistError ?? (strategyWatchlist.cap_exceeded_by_protective_coverage ? "protective coverage above cap" : "eligible for evaluation"),
          },
          { label: "Live", value: strategyWatchlist.streaming_count, tone: strategyWatchlist.streaming_count ? "positive" : "inactive", meta: "streaming now" },
        ]}
      />

      <StickyToolbar className="toolbar-markets">
        <div className="toolbar-group">
          <input className="console-input" type="search" placeholder="Search catalogue" value={search} onChange={(event) => setSearch(event.target.value)} />
          <select className="console-select" value={assetClass} onChange={(event) => setAssetClass(event.target.value)}>
            {ASSET_CLASSES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="console-select" value={currency} onChange={(event) => setCurrency(event.target.value)}>
            {currencies.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="toolbar-group">
          <label className="console-toggle"><input type="checkbox" checked={forexMajorsOnly} onChange={() => setForexMajorsOnly((value) => !value)} />Forex majors</label>
          <label className="console-toggle"><input type="checkbox" checked={tradableOnly} onChange={() => setTradableOnly((value) => !value)} />Tradable</label>
          <label className="console-toggle"><input type="checkbox" checked={shortlistedOnly} onChange={() => setShortlistedOnly((value) => !value)} />Shortlisted</label>
          <label className="console-toggle"><input type="checkbox" checked={watchlistOnly} onChange={() => setWatchlistOnly((value) => !value)} />Strategy watchlist</label>
          <label className="console-toggle"><input type="checkbox" checked={streamingOnly} onChange={() => setStreamingOnly((value) => !value)} />Streaming</label>
          <button type="button" className="console-button console-button--ghost" disabled={isPending} onClick={() => startTransition(() => void refreshAll())}>Refresh</button>
        </div>
      </StickyToolbar>

      <SplitPanel
        className="layout-markets items-start"
        left={
          <Panel title="Instrument Catalogue" subtitle="Available markets. Stars do not stream or trade." priority="primary" tone="neutral">
            <CompactTable
              rows={filteredRows}
              emptyLabel={catalogueError ? "Catalogue unavailable." : "No instruments match the current filters."}
              getRowTone={rowTone}
              columns={[
                {
                  key: "star",
                  header: "",
                  render: (row) => (
                    <button type="button" className={`star-button ${row.shortlisted ? "is-active" : ""}`.trim()} disabled={isPending} onClick={() => toggleShortlist(row.instrument, row.shortlisted)} aria-label={row.shortlisted ? "Remove from shortlist" : "Add to shortlist"}>
                      {row.shortlisted ? "★" : "☆"}
                    </button>
                  ),
                },
                {
                  key: "select",
                  header: "",
                  render: (row) => (
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(row.instrument)}
                      onChange={() => setSelectedIds((current) => current.includes(row.instrument) ? current.filter((id) => id !== row.instrument) : [...current, row.instrument])}
                      aria-label={`Select ${row.symbol}`}
                    />
                  ),
                },
                { key: "instrument", header: "Instrument", render: (row) => <span>{row.name} <span className="muted">{row.symbol}</span></span> },
                { key: "asset", header: "Class", render: (row) => row.asset_class },
                { key: "state", header: "State", render: (row) => <StatusPill label={row.streaming_now ? "live" : row.in_strategy_watchlist ? "eligible" : row.shortlisted ? "shortlisted" : "catalogue"} tone={rowTone(row)} /> },
                { key: "fit", header: "Strategy Fit", render: (row) => row.strategy_compatibility.slice(0, 2).join(", ") || "n/a" },
              ]}
            />
          </Panel>
        }
        center={
          <Panel title="Shortlist" subtitle="Operator interest only." priority="secondary" tone="neutral" actions={<div className="console-inline-actions"><button type="button" className="console-button console-button--ghost" disabled={!selectedRows.length || isPending} onClick={() => addToStrategyWatchlist(selectedRows.map((row) => row.instrument))}>Add Selected</button><button type="button" className="console-button" disabled={!addableShortlist.length || isPending} onClick={() => addToStrategyWatchlist(addableShortlist.map((row) => row.instrument))}>Add All Eligible</button></div>}>
            <CompactTable
              rows={shortlistedRows}
              emptyLabel="No shortlisted instruments yet."
              getRowTone={(row) => (strategyRowsById.has(row.instrument) ? "positive" : "neutral")}
              columns={[
                { key: "instrument", header: "Instrument", render: (row) => `${row.name} (${row.symbol})` },
                { key: "status", header: "Meaning", render: (row) => strategyRowsById.has(row.instrument) ? "in strategy watchlist" : "operator interest" },
                {
                  key: "reason",
                  header: "Add Readiness",
                  render: (row) => canAdd(row, strategyWatchlist.limit, strategyWatchlist.active_count) ?? "Can be added",
                },
                {
                  key: "action",
                  header: "Action",
                  render: (row) => (
                    <button type="button" className="console-button console-button--ghost" disabled={Boolean(canAdd(row, strategyWatchlist.limit, strategyWatchlist.active_count)) || isPending} onClick={() => addToStrategyWatchlist([row.instrument])}>
                      Add
                    </button>
                  ),
                },
              ]}
            />
          </Panel>
        }
        right={
          <div className="stack-layout">
            <Panel title="Strategy Watchlist" subtitle="Eligible for backend streaming/evaluation." priority="critical" tone={strategyWatchlist.active_count ? "positive" : "inactive"} compact>
              <CompactTable
                dense
                rows={strategyWatchlist.instruments}
                emptyLabel={watchlistError ? "Strategy watchlist unavailable." : "No active strategy watchlist instruments."}
                getRowTone={(row) => row.streamed ? "positive" : "warning"}
                columns={[
                  { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
                  { key: "state", header: "State", render: (row) => <StatusPill label={row.streamed ? "streaming" : "eligible"} tone={row.streamed ? "positive" : "warning"} /> },
                  {
                    key: "reason",
                    header: "Source",
                    render: (row) => (
                      <span title={row.reason_detail ? `${row.reason_detail.operator_action} (${row.reason_detail.code})` : row.reason ?? undefined}>
                        {row.reason_detail?.label ?? "Watchlist"}
                      </span>
                    ),
                  },
                ]}
              />
            </Panel>
            <Panel title="Operator Notes" priority="passive" tone="inactive" compact>
              <div className="metric-stack">
                <div className="metric-stack__row"><span>Catalogue</span><strong>Available markets</strong></div>
                <div className="metric-stack__row"><span>Shortlist</span><strong>Operator interest</strong></div>
                <div className="metric-stack__row"><span>Strategy watchlist</span><strong>Stream eligible</strong></div>
                <div className="metric-stack__row"><span>Live</span><strong>Streaming/evaluating</strong></div>
                <div className="metric-stack__row"><span>Protective coverage</span><strong>{strategyWatchlist.protective_count ?? 0} pinned</strong></div>
              </div>
              {overviewError || catalogueError || watchlistError ? <div className="console-alert console-alert--warning">{overviewError ?? catalogueError ?? watchlistError}<DataIndicator state="error" message={overviewError ?? catalogueError ?? watchlistError ?? "Market data unavailable."} /></div> : null}
              {statusMessage ? <div className="console-alert console-alert--neutral">{statusMessage}</div> : null}
              <div className="console-empty">Forex overview: {initialOverview.summary.detail}</div>
            </Panel>
          </div>
        }
      />
    </main>
  );
}
