"use client";

import { useEffect, useMemo, useState } from "react";

import { CompactTable, DataIndicator, Panel, SplitPanel, StatusPill, StatusStrip, StickyToolbar } from "@/components/console/primitives";
import {
  addShortlistInstrument,
  addStrategyWatchlistInstruments,
  getMarketCatalogue,
  getMarketOverview,
  getStrategyWatchlist,
  removeShortlistInstrument,
  removeStrategyWatchlistInstrument,
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

type MarketMutationState = {
  kind:
    | "shortlist-add"
    | "shortlist-remove"
    | "watchlist-add"
    | "watchlist-remove"
    | "refresh";
  instruments: string[];
};

type MarketStatusNotice = {
  tone: "neutral" | "warning";
  message: string;
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

function catalogueStateLabel(row: MarketCatalogueInstrument) {
  if (row.streaming_now) {
    return "Streaming data";
  }
  if (row.in_strategy_watchlist) {
    return "Watchlisted, not streaming";
  }
  if (row.shortlisted) {
    return "Shortlisted only";
  }
  return "Catalogue only";
}

function watchlistStateLabel(row: StrategyWatchlistResponse["instruments"][number]) {
  return row.streamed ? "Streaming data" : "Evaluation candidate only";
}

function watchlistStateDetail(row: StrategyWatchlistResponse["instruments"][number]) {
  if (row.streamed) {
    return "Data coverage only. Not entry approval.";
  }
  return "Not trading approval. Entry still depends on governance, risk, broker, and market-data gates.";
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
  const [statusNotice, setStatusNotice] = useState<MarketStatusNotice | null>(null);
  const [mutationState, setMutationState] = useState<MarketMutationState | null>(null);
  const isPending = mutationState !== null;

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
    const nextOverviewError = nextOverview.status === "rejected" ? (nextOverview.reason instanceof Error ? nextOverview.reason.message : "Market overview unavailable.") : null;
    setOverviewError(nextOverviewError);

    return {
      failureDetail:
        (nextCatalogue.status === "rejected" ? (nextCatalogue.reason instanceof Error ? nextCatalogue.reason.message : "Catalogue unavailable.") : null)
        ?? (nextWatchlist.status === "rejected" ? (nextWatchlist.reason instanceof Error ? nextWatchlist.reason.message : "Strategy watchlist unavailable.") : null)
        ?? nextOverviewError,
      catalogue: nextCatalogue.status === "fulfilled" ? nextCatalogue.value : null,
      strategyWatchlist: nextWatchlist.status === "fulfilled" ? nextWatchlist.value : null,
    };
  };

  const toggleShortlist = (instrumentId: string, currentlyShortlisted: boolean) => {
    void (async () => {
      setMutationState({
        kind: currentlyShortlisted ? "shortlist-remove" : "shortlist-add",
        instruments: [instrumentId],
      });
      setStatusNotice(null);
      try {
        if (currentlyShortlisted) {
          await removeShortlistInstrument(instrumentId);
        } else {
          await addShortlistInstrument(instrumentId);
        }
        const refreshed = await refreshAll();
        const shortlistVisible =
          refreshed.catalogue?.instruments.find((row) => row.instrument === instrumentId)?.shortlisted ?? currentlyShortlisted;
        if (refreshed.failureDetail) {
          setStatusNotice({
            tone: "warning",
            message: `Shortlist mutation succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
          });
        } else if (currentlyShortlisted ? shortlistVisible : !shortlistVisible) {
          setStatusNotice({
            tone: "warning",
            message: `Shortlist mutation route succeeded, but refreshed backend truth does not yet show ${formatInstrumentLabel(instrumentId)} in the expected shortlist state.`,
          });
        } else {
          setStatusNotice({
            tone: "neutral",
            message: `Shortlist mutation confirmed after backend truth refreshed for ${formatInstrumentLabel(instrumentId)}.`,
          });
        }
      } catch (error) {
        setStatusNotice({
          tone: "warning",
          message: `Shortlist mutation failed: ${error instanceof Error ? error.message : "backend shortlist truth could not be updated."}`,
        });
      } finally {
        setMutationState(null);
      }
    })();
  };

  const addToStrategyWatchlist = (instrumentIds: string[]) => {
    void (async () => {
      setMutationState({
        kind: "watchlist-add",
        instruments: instrumentIds,
      });
      setStatusNotice(null);
      try {
        const result = await addStrategyWatchlistInstruments(instrumentIds);
        const refreshed = await refreshAll();
        const visibleInstruments = new Set((refreshed.strategyWatchlist?.instruments ?? []).map((row) => row.instrument));
        const expectedVisible = result.added.every((item) => visibleInstruments.has(item.instrument));
        const skippedReasons = result.skipped
          .slice(0, 3)
          .map((item) => `${formatInstrumentLabel(item.instrument)}: ${item.reason_detail?.label ?? item.reason}`)
          .join(" · ");
        setSelectedIds([]);
        if (refreshed.failureDetail) {
          setStatusNotice({
            tone: "warning",
            message: `Strategy watchlist mutation succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
          });
        } else if (!expectedVisible) {
          setStatusNotice({
            tone: "warning",
            message: "Strategy watchlist mutation route succeeded, but refreshed backend truth does not yet show every added instrument.",
          });
        } else {
          setStatusNotice({
            tone: "neutral",
            message: `Strategy watchlist mutation confirmed after backend truth refreshed. ${result.added.length} added, ${result.skipped.length} blocked.${skippedReasons ? ` ${skippedReasons}` : ""}`,
          });
        }
      } catch (error) {
        setStatusNotice({
          tone: "warning",
          message: `Strategy watchlist mutation failed: ${error instanceof Error ? error.message : "backend watchlist truth could not be updated."}`,
        });
      } finally {
        setMutationState(null);
      }
    })();
  };

  const removeFromStrategyWatchlist = (instrumentId: string) => {
    void (async () => {
      setMutationState({
        kind: "watchlist-remove",
        instruments: [instrumentId],
      });
      setStatusNotice(null);
      try {
        await removeStrategyWatchlistInstrument(instrumentId);
        const refreshed = await refreshAll();
        const stillVisible = refreshed.strategyWatchlist?.instruments.some((row) => row.instrument === instrumentId) ?? true;
        if (refreshed.failureDetail) {
          setStatusNotice({
            tone: "warning",
            message: `Strategy watchlist mutation succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
          });
        } else if (stillVisible) {
          setStatusNotice({
            tone: "warning",
            message: `Strategy watchlist remove route succeeded, but refreshed backend truth still shows ${formatInstrumentLabel(instrumentId)} as an evaluation candidate.`,
          });
        } else {
          setStatusNotice({
            tone: "neutral",
            message: `Strategy watchlist removal confirmed after backend truth refreshed for ${formatInstrumentLabel(instrumentId)}.`,
          });
        }
      } catch (error) {
        setStatusNotice({
          tone: "warning",
          message: `Strategy watchlist mutation failed: ${error instanceof Error ? error.message : "backend watchlist truth could not be updated."}`,
        });
      } finally {
        setMutationState(null);
      }
    })();
  };

  const selectedRows = catalogue.instruments.filter((row) => selectedIds.includes(row.instrument));
  const normalWatchlistCount = strategyWatchlist.normal_count ?? Math.max(0, strategyWatchlist.active_count - (strategyWatchlist.protective_count ?? 0));
  const addableShortlist = shortlistedRows.filter((row) => !canAdd(row, strategyWatchlist.limit, normalWatchlistCount));
  const addSelectedDisabledReason = Boolean(catalogueError || watchlistError)
    ? catalogueError ?? watchlistError
    : !selectedRows.length
      ? "Select one or more catalogue instruments before sending a strategy-watchlist mutation."
      : null;
  const addAllDisabledReason = Boolean(catalogueError || watchlistError)
    ? catalogueError ?? watchlistError
    : !addableShortlist.length
      ? "No shortlisted instruments are currently eligible for strategy-watchlist add."
      : null;

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          {
            label: "Catalogue",
            value: catalogueError ? "Unavailable" : catalogue.summary.total_count,
            tone: catalogueError ? "inactive" : "neutral",
            meta: catalogueError ?? "available markets",
          },
          {
            label: "Shortlist",
            value: catalogueError ? "Unavailable" : catalogue.summary.shortlisted_count,
            tone: catalogueError ? "inactive" : "neutral",
            meta: catalogueError ?? "operator interest",
          },
          {
            label: "Strategy Watchlist",
            value: watchlistError ? "Unavailable" : `${normalWatchlistCount}/${strategyWatchlist.limit || "-"}`,
            tone: watchlistError ? "inactive" : strategyWatchlist.cap_exceeded_by_protective_coverage ? "warning" : normalWatchlistCount >= strategyWatchlist.limit ? "warning" : "positive",
            meta: watchlistError ?? (strategyWatchlist.cap_exceeded_by_protective_coverage ? `${strategyWatchlist.protective_count ?? 0} protective above normal capacity` : "normal watchlist capacity"),
          },
          {
            label: "Live",
            value: watchlistError ? "Unavailable" : strategyWatchlist.streaming_count,
            tone: watchlistError ? "inactive" : strategyWatchlist.streaming_count ? "positive" : "inactive",
            meta: watchlistError ?? "data coverage now",
          },
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
          <button
            type="button"
            className="console-button console-button--ghost"
            disabled={isPending}
            onClick={() =>
              void (async () => {
                setMutationState({
                  kind: "refresh",
                  instruments: [],
                });
                setStatusNotice(null);
                const refreshed = await refreshAll();
                setStatusNotice(
                  refreshed.failureDetail
                    ? {
                        tone: "warning",
                        message: `Markets refresh failed: ${refreshed.failureDetail}`,
                      }
                    : {
                        tone: "neutral",
                        message: "Markets truth refreshed from backend sources.",
                      },
                );
                setMutationState(null);
              })()
            }
          >
            {isPending && mutationState?.kind === "refresh" ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </StickyToolbar>

      <SplitPanel
        className="layout-markets items-start"
        left={
          <Panel
            title="Instrument Catalogue"
            subtitle={catalogueError ? "Catalogue source unavailable. Stars do not stream or trade." : "Available markets. Stars do not stream or trade."}
            priority="primary"
            tone={catalogueError ? "inactive" : "neutral"}
          >
            <CompactTable
              rows={filteredRows}
              emptyLabel={catalogueError ? "Catalogue unavailable." : "No instruments match the current filters."}
              getRowTone={rowTone}
              columns={[
                {
                  key: "star",
                  header: "",
                  render: (row) => (
                    <button
                      type="button"
                      className={`star-button ${row.shortlisted ? "is-active" : ""}`.trim()}
                      disabled={isPending}
                      onClick={() => toggleShortlist(row.instrument, row.shortlisted)}
                      aria-label={row.shortlisted ? "Remove from shortlist" : "Add to shortlist"}
                      title={row.shortlisted ? "Operator interest only. Removing from shortlist does not remove streaming or trading approval because shortlist state is not approval." : "Operator interest only. Adding to shortlist does not deploy, stream, or approve trading."}
                    >
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
                { key: "state", header: "State", render: (row) => <StatusPill label={catalogueStateLabel(row)} tone={rowTone(row)} /> },
                { key: "fit", header: "Strategy Fit", render: (row) => row.strategy_compatibility.slice(0, 2).join(", ") || "n/a" },
              ]}
            />
          </Panel>
        }
        center={
          <Panel title="Shortlist" subtitle={catalogueError ? "Shortlist source unavailable." : "Operator interest only."} priority="secondary" tone={catalogueError ? "inactive" : "neutral"} actions={<div className="console-inline-actions"><button type="button" className="console-button console-button--ghost" disabled={Boolean(addSelectedDisabledReason) || isPending} onClick={() => addToStrategyWatchlist(selectedRows.map((row) => row.instrument))}>{isPending && mutationState?.kind === "watchlist-add" && mutationState.instruments.length === selectedRows.length ? "Adding..." : "Add Selected"}</button><button type="button" className="console-button" disabled={Boolean(addAllDisabledReason) || isPending} onClick={() => addToStrategyWatchlist(addableShortlist.map((row) => row.instrument))}>{isPending && mutationState?.kind === "watchlist-add" && mutationState.instruments.length === addableShortlist.length ? "Adding..." : "Add All Eligible"}</button></div>}>
            <CompactTable
              rows={shortlistedRows}
              emptyLabel={catalogueError ? "Shortlist unavailable." : "No shortlisted instruments yet."}
              getRowTone={(row) => (strategyRowsById.has(row.instrument) ? "positive" : "neutral")}
              columns={[
                { key: "instrument", header: "Instrument", render: (row) => `${row.name} (${row.symbol})` },
                { key: "status", header: "Meaning", render: (row) => strategyRowsById.has(row.instrument) ? "in strategy watchlist" : "operator interest" },
                {
                  key: "reason",
                  header: "Add Readiness",
                  render: (row) => canAdd(row, strategyWatchlist.limit, normalWatchlistCount) ?? "Can be added",
                },
                {
                  key: "action",
                  header: "Action",
                  render: (row) => (
                    <button type="button" className="console-button console-button--ghost" disabled={Boolean(canAdd(row, strategyWatchlist.limit, normalWatchlistCount)) || isPending} onClick={() => addToStrategyWatchlist([row.instrument])}>
                      {isPending && mutationState?.kind === "watchlist-add" && mutationState.instruments.includes(row.instrument) ? "Adding..." : "Add"}
                    </button>
                  ),
                },
              ]}
            />
          </Panel>
        }
        right={
          <div className="stack-layout">
            <Panel title="Strategy Watchlist" subtitle={watchlistError ? "Strategy watchlist source unavailable." : "Evaluation candidates. Not trading approval."} priority="critical" tone={watchlistError ? "inactive" : strategyWatchlist.active_count ? "positive" : "inactive"} compact>
              <CompactTable
                dense
                rows={strategyWatchlist.instruments}
                emptyLabel={watchlistError ? "Strategy watchlist unavailable." : "No active strategy watchlist instruments."}
                getRowTone={(row) => row.streamed ? "positive" : "warning"}
                columns={[
                  { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
                  {
                    key: "state",
                    header: "State",
                    render: (row) => (
                      <span className="cell-stack" title={watchlistStateDetail(row)}>
                        <StatusPill label={watchlistStateLabel(row)} tone={row.streamed ? "positive" : "warning"} />
                        <span className="status-note status-note--inline">{watchlistStateDetail(row)}</span>
                      </span>
                    ),
                  },
                  {
                    key: "reason",
                    header: "Source",
                    render: (row) => (
                      <span title={row.reason_detail ? `${row.reason_detail.operator_action} (${row.reason_detail.code})` : row.reason ?? undefined}>
                        {row.reason_detail?.label ?? "Watchlist"}
                      </span>
                    ),
                  },
                  {
                    key: "action",
                    header: "Action",
                    render: (row) => (
                      <button
                        type="button"
                        className="console-button console-button--ghost"
                        disabled={Boolean(watchlistError) || isPending}
                        onClick={() => removeFromStrategyWatchlist(row.instrument)}
                      >
                        {isPending && mutationState?.kind === "watchlist-remove" && mutationState.instruments.includes(row.instrument) ? "Removing..." : "Remove"}
                      </button>
                    ),
                  },
                ]}
              />
            </Panel>
            <Panel title="Operator Notes" priority="passive" tone="inactive" compact>
              <div className="metric-stack">
                <div className="metric-stack__row"><span>Catalogue</span><strong>{catalogueError ? "Unavailable" : "Available markets"}</strong></div>
                <div className="metric-stack__row"><span>Shortlist</span><strong>{catalogueError ? "Unavailable" : "Operator interest"}</strong></div>
                <div className="metric-stack__row"><span>Strategy watchlist</span><strong>{watchlistError ? "Unavailable" : "Evaluation candidates"}</strong></div>
                <div className="metric-stack__row"><span>Live</span><strong>{watchlistError ? "Unavailable" : "Data coverage only"}</strong></div>
                <div className="metric-stack__row"><span>Normal capacity</span><strong>{watchlistError ? "Unavailable" : `${normalWatchlistCount}/${strategyWatchlist.limit || "-"}`}</strong></div>
                <div className="metric-stack__row"><span>Protective coverage</span><strong>{watchlistError ? "Unavailable" : `${strategyWatchlist.protective_count ?? 0} pinned separately`}</strong></div>
              </div>
              {addSelectedDisabledReason ? <div className="status-note status-note--inline">Add Selected unavailable: {addSelectedDisabledReason}</div> : null}
              {addAllDisabledReason ? <div className="status-note status-note--inline">Add All Eligible unavailable: {addAllDisabledReason}</div> : null}
              {overviewError || catalogueError || watchlistError ? <div className="console-alert console-alert--warning">{overviewError ?? catalogueError ?? watchlistError}<DataIndicator state="error" message={overviewError ?? catalogueError ?? watchlistError ?? "Market data unavailable."} /></div> : null}
              {statusNotice ? <div className={`console-alert console-alert--${statusNotice.tone}`}>{statusNotice.message}</div> : null}
              <div className="console-empty">Forex overview: {initialOverview.summary.detail}</div>
            </Panel>
          </div>
        }
      />
    </main>
  );
}
