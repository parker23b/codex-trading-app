"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { CompactTable, DataIndicator, Panel, SplitPanel, StatusPill, StickyToolbar } from "@/components/console/primitives";
import { getMarketOverview } from "@/lib/api";
import { formatSignedPercent } from "@/lib/format";
import { MarketCategory, MarketCategoryOverviewResponse } from "@/lib/types";

type MarketOverviewDashboardProps = {
  initialOverview: MarketCategoryOverviewResponse;
  initialOverviewError: string | null;
};

const WATCHLIST_STORAGE_KEY = "trading-platform-market-watchlist";
const MARKET_CATEGORIES: MarketCategory[] = ["forex", "indices", "commodities", "stocks", "crypto"];
const MARKET_LABELS: Record<MarketCategory, string> = {
  forex: "Forex",
  indices: "Indices",
  commodities: "Commodities",
  stocks: "Stocks",
  crypto: "Crypto",
};
const MARKET_DESCRIPTIONS: Record<MarketCategory, string> = {
  forex: "Session-aware currency routing.",
  indices: "Benchmark contracts and venue state.",
  commodities: "Metals and energy venue windows.",
  stocks: "Primary cash-equity session coverage.",
  crypto: "Always-on assets with tighter guardrails.",
};

function formatCountdown(targetIso: string) {
  const deltaMs = Math.max(0, new Date(targetIso).getTime() - Date.now());
  const totalMinutes = Math.round(deltaMs / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function MarketOverviewDashboard({ initialOverview, initialOverviewError }: MarketOverviewDashboardProps) {
  const [selectedCategory, setSelectedCategory] = useState<MarketCategory>("forex");
  const [selectedInstrumentId, setSelectedInstrumentId] = useState<string>(initialOverviewError ? "" : initialOverview.instruments[0]?.id ?? "");
  const [search, setSearch] = useState("");
  const [showTradableOnly, setShowTradableOnly] = useState(false);
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [starredIds, setStarredIds] = useState<string[]>([]);
  const [isPending, startTransition] = useTransition();
  const [loadedMarkets, setLoadedMarkets] = useState<Partial<Record<MarketCategory, MarketCategoryOverviewResponse>>>(
    initialOverviewError ? {} : { forex: initialOverview },
  );
  const [loadError, setLoadError] = useState<string | null>(initialOverviewError);

  useEffect(() => {
    const stored = window.localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (stored) {
      try {
        setStarredIds(JSON.parse(stored) as string[]);
      } catch {
        window.localStorage.removeItem(WATCHLIST_STORAGE_KEY);
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(starredIds));
  }, [starredIds]);

  useEffect(() => {
    if (loadedMarkets[selectedCategory]) {
      return;
    }

    startTransition(() => {
      getMarketOverview(selectedCategory)
        .then((overview) => {
          setLoadedMarkets((current) => ({ ...current, [selectedCategory]: overview }));
          setLoadError(null);
        })
        .catch((error: unknown) => {
          setLoadError(error instanceof Error ? error.message : "Failed to load market data.");
        });
    });
  }, [loadedMarkets, selectedCategory]);

  const selectedMarket = loadedMarkets[selectedCategory];
  const selectedSummary = selectedMarket?.summary ?? null;
  const summaries = MARKET_CATEGORIES.map((category) => ({
    category,
    label: loadedMarkets[category]?.summary.label ?? MARKET_LABELS[category],
    description: loadedMarkets[category]?.summary.description ?? MARKET_DESCRIPTIONS[category],
  }));

  const filteredInstruments = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    const rows = selectedMarket?.instruments ?? [];

    return rows
      .filter((instrument) => {
        if (showTradableOnly && !instrument.tradable) {
          return false;
        }
        if (showActiveOnly && !instrument.active) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return (
          instrument.name.toLowerCase().includes(normalizedSearch) ||
          instrument.symbol.toLowerCase().includes(normalizedSearch) ||
          instrument.strategyCompatibility.some((strategy) => strategy.toLowerCase().includes(normalizedSearch))
        );
      })
      .sort((left, right) => {
        const leftStarred = starredIds.includes(left.id) ? 1 : 0;
        const rightStarred = starredIds.includes(right.id) ? 1 : 0;
        if (leftStarred !== rightStarred) {
          return rightStarred - leftStarred;
        }
        if (left.tradable !== right.tradable) {
          return Number(right.tradable) - Number(left.tradable);
        }
        return left.name.localeCompare(right.name);
      });
  }, [search, selectedMarket?.instruments, showActiveOnly, showTradableOnly, starredIds]);

  useEffect(() => {
    if (filteredInstruments.some((instrument) => instrument.id === selectedInstrumentId)) {
      return;
    }
    setSelectedInstrumentId(filteredInstruments[0]?.id ?? "");
  }, [filteredInstruments, selectedInstrumentId]);

  const selectedInstrument = filteredInstruments.find((instrument) => instrument.id === selectedInstrumentId) ?? null;

  const refreshSelectedMarket = async () => {
    try {
      const overview = await getMarketOverview(selectedCategory);
      setLoadedMarkets((current) => ({ ...current, [selectedCategory]: overview }));
      setLoadError(null);
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "Failed to refresh market data.");
    }
  };

  const toggleStar = (instrumentId: string) => {
    setStarredIds((current) =>
      current.includes(instrumentId) ? current.filter((id) => id !== instrumentId) : [...current, instrumentId],
    );
  };

  const selectedInstrumentTone = !selectedInstrument
    ? "inactive"
    : !selectedInstrument.tradable
      ? "negative"
      : selectedInstrument.status !== "OPEN"
        ? "warning"
        : "positive";

  return (
    <main className="console-page console-page--dense">
      <StickyToolbar className="toolbar-markets">
        <div className="toolbar-group">
              {summaries.map((summary) => (
            <button
              key={summary.category}
              type="button"
              className={`console-chip${summary.category === selectedCategory ? " is-active" : ""}`}
              onClick={() => setSelectedCategory(summary.category)}
            >
              {summary.label}
            </button>
          ))}
        </div>
        <div className="toolbar-group">
          <input
            type="search"
            className="console-input"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search instruments or strategy fit"
          />
          <label className="console-toggle">
            <input type="checkbox" checked={showTradableOnly} onChange={() => setShowTradableOnly((current) => !current)} />
            Tradable
          </label>
          <label className="console-toggle">
            <input type="checkbox" checked={showActiveOnly} onChange={() => setShowActiveOnly((current) => !current)} />
            Active
          </label>
          <button
            type="button"
            className="console-button console-button--ghost"
            disabled={isPending}
            onClick={() => startTransition(() => void refreshSelectedMarket())}
          >
            Refresh
          </button>
        </div>
      </StickyToolbar>

      <SplitPanel
        className="layout-markets items-start"
        left={
          <Panel title="Instrument List" priority="secondary" tone="neutral" compact>
            <div className="list-panel">
              {filteredInstruments.length ? (
                filteredInstruments.map((instrument) => {
                  const isActive = instrument.id === selectedInstrumentId;
                  const tone = !instrument.tradable ? "negative" : instrument.status !== "OPEN" ? "warning" : "positive";
                  return (
                    <button
                      key={instrument.id}
                      type="button"
                      className={`list-item${isActive ? " is-active" : ""}`}
                      onClick={() => setSelectedInstrumentId(instrument.id)}
                    >
                      <div className="list-item__main">
                        <strong>{instrument.name}</strong>
                        <span>{instrument.symbol}</span>
                      </div>
                      <div className="list-item__meta">
                        <StatusPill label={instrument.status.toLowerCase()} tone={tone} quiet />
                        <span>{instrument.tradable ? "tradable" : "blocked"}</span>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="console-empty">No instruments match the current filters.</div>
              )}
            </div>
          </Panel>
        }
        center={
          <Panel title="Selected Instrument" priority="primary" tone={selectedInstrumentTone}>
            {selectedInstrument ? (
              <div className="detail-stack">
                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>Venue</span>
                    <strong>{selectedInstrument.status}</strong>
                      <em>{selectedSummary?.label ?? MARKET_LABELS[selectedCategory]}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Tradable</span>
                    <strong>{selectedInstrument.tradable ? "Yes" : "No"}</strong>
                    <em>{selectedInstrument.active ? "active" : "inactive"}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Next transition</span>
                    <strong>
                      {selectedSummary?.nextTransitionAt ? formatCountdown(selectedSummary.nextTransitionAt) : "-"}
                      {!selectedSummary ? <DataIndicator state={isPending ? "loading" : loadError ? "error" : "unavailable"} message={loadError ?? "Market summary has not loaded yet."} /> : null}
                    </strong>
                    <em>{selectedSummary?.nextTransitionLabel ?? "Pending data"}</em>
                  </div>
                </div>

                <CompactTable
                  rows={[selectedInstrument]}
                  emptyLabel="No instrument selected."
                  columns={[
                    { key: "instrument", header: "Instrument", render: (row) => `${row.name} (${row.symbol})` },
                    {
                      key: "state",
                      header: "State",
                      render: (row) => <StatusPill label={row.status.toLowerCase()} tone={!row.tradable ? "negative" : row.status !== "OPEN" ? "warning" : "positive"} />,
                    },
                    { key: "activity", header: "Activity", render: (row) => row.activityLevel },
                    { key: "price", header: "Price", render: (row) => row.price.toFixed(4) },
                    { key: "change", header: "Change", render: (row) => formatSignedPercent(row.changePercent, 2) },
                  ]}
                />

                <Panel title="Strategy Fit" priority="secondary" tone="neutral" compact>
                  <CompactTable
                    dense
                    rows={(selectedInstrument.strategyCompatibility ?? []).map((strategy) => ({ strategy }))}
                    emptyLabel="No compatible strategies."
                    columns={[{ key: "strategy", header: "Strategy", render: (row) => row.strategy }]}
                  />
                </Panel>
              </div>
            ) : (
              <div className="console-empty">Select an instrument from the list.</div>
            )}
          </Panel>
        }
        right={
          <div className="stack-layout">
            <Panel title="Market State" priority="secondary" tone={selectedSummary?.status === "OPEN" ? "positive" : selectedSummary?.status === "LIMITED" ? "warning" : "inactive"} compact>
              <div className="metric-stack">
                <div className="metric-stack__row">
                  <span>Status</span>
                  <strong>
                    {selectedSummary?.status ?? "-"}
                    {!selectedSummary ? <DataIndicator state={isPending ? "loading" : loadError ? "error" : "unavailable"} message={loadError ?? "Market status has not loaded yet."} /> : null}
                  </strong>
                </div>
                <div className="metric-stack__row">
                  <span>Tradable</span>
                  <strong>{selectedSummary ? `${selectedSummary.tradableCount}/${selectedSummary.totalCount}` : "-"}</strong>
                </div>
                <div className="metric-stack__row">
                  <span>Active</span>
                  <strong>{selectedSummary?.activeCount ?? "-"}</strong>
                </div>
              </div>
            </Panel>

            <Panel title="Local Actions" priority="passive" tone="inactive" compact>
              {selectedInstrument ? (
                <div className="detail-stack">
                  <StatusPill label={starredIds.includes(selectedInstrument.id) ? "pinned" : "not pinned"} tone={starredIds.includes(selectedInstrument.id) ? "positive" : "inactive"} />
                  <button type="button" className="console-button console-button--ghost" onClick={() => toggleStar(selectedInstrument.id)}>
                    {starredIds.includes(selectedInstrument.id) ? "Remove Pin" : "Pin Instrument"}
                  </button>
                  {loadError ? <div className="console-alert console-alert--warning">{loadError}</div> : null}
                </div>
              ) : (
                <div className="detail-stack">
                  <div className="console-empty">No instrument selected.</div>
                  {loadError ? <div className="console-alert console-alert--warning">{loadError}</div> : null}
                </div>
              )}
            </Panel>
          </div>
        }
      />
    </main>
  );
}
