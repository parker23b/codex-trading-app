"use client";

import { useEffect, useMemo, useState } from "react";

import { InstrumentsTable } from "@/components/markets/instruments-table";
import { MarketSelector } from "@/components/markets/market-selector";
import { MarketStatusCard } from "@/components/markets/market-status-card";
import { Card } from "@/components/ui/card";
import { MarketCategory, MarketOverviewResponse } from "@/lib/types";

type MarketOverviewDashboardProps = {
  overview: MarketOverviewResponse;
};

const WATCHLIST_STORAGE_KEY = "trading-platform-market-watchlist";

function formatCountdown(targetIso: string) {
  const deltaMs = Math.max(0, new Date(targetIso).getTime() - Date.now());
  const totalMinutes = Math.round(deltaMs / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function MarketOverviewDashboard({ overview }: MarketOverviewDashboardProps) {
  const [selectedCategory, setSelectedCategory] = useState<MarketCategory>(overview.summaries[0]?.category ?? "forex");
  const [search, setSearch] = useState("");
  const [showTradableOnly, setShowTradableOnly] = useState(false);
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [starredIds, setStarredIds] = useState<string[]>([]);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const stored = window.localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as string[];
        setStarredIds(parsed);
      } catch {
        window.localStorage.removeItem(WATCHLIST_STORAGE_KEY);
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(starredIds));
  }, [starredIds]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const selectedSummary = overview.summaries.find((summary) => summary.category === selectedCategory) ?? overview.summaries[0];

  const filteredInstruments = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    const rows = overview.instruments[selectedCategory] ?? [];

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
        // Watchlist items stay pinned first so repeat-check instruments are always visible without extra filtering.
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
  }, [overview.instruments, search, selectedCategory, showActiveOnly, showTradableOnly, starredIds]);

  const handleToggleStar = (instrumentId: string) => {
    setStarredIds((current) =>
      current.includes(instrumentId) ? current.filter((id) => id !== instrumentId) : [...current, instrumentId],
    );
  };

  const countdownLabel = selectedSummary
    ? `${selectedSummary.nextTransitionLabel} in ${formatCountdown(selectedSummary.nextTransitionAt)}`
    : "Awaiting session data";

  return (
    <main className="dashboard-layout">
      <section className="page-grid">
        <Card
          title="Market Readiness"
          subtitle="Use the market selector to see where strategies can operate right now, then narrow the instrument table to tradable, active names."
          action={<MarketSelector summaries={overview.summaries} selectedCategory={selectedCategory} onSelect={setSelectedCategory} />}
        >
          {/* The strip gives an at-a-glance scan across categories before the operator commits to one table view. */}
          <div className="markets-summary-strip">
            {overview.summaries.map((summary) => (
              <button
                type="button"
                key={summary.category}
                className={`market-chip ${summary.category === selectedCategory ? "is-active" : ""}`.trim()}
                onClick={() => setSelectedCategory(summary.category)}
              >
                <span>{summary.label}</span>
                <strong>{summary.tradableCount} tradable</strong>
              </button>
            ))}
          </div>
        </Card>
      </section>

      {selectedSummary ? (
        <section className="hero-grid market-hero-grid">
          <div className="hero-grid__main">
            <MarketStatusCard summary={selectedSummary} countdownLabel={countdownLabel} />
          </div>
          <div className="hero-grid__side">
            <Card
              title="Table Controls"
              subtitle="Fast scanning matters, so the controls trim noise before the user reaches the rows."
              className="card--compact"
            >
              <div className="markets-controls">
                <label className="markets-search">
                  <span className="eyebrow">Search</span>
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder={`Search ${selectedSummary.label.toLowerCase()} instruments or strategies`}
                  />
                </label>
                <label className="markets-toggle">
                  <input
                    type="checkbox"
                    checked={showTradableOnly}
                    onChange={() => setShowTradableOnly((current) => !current)}
                  />
                  <span>Show tradable only</span>
                </label>
                <label className="markets-toggle">
                  <input
                    type="checkbox"
                    checked={showActiveOnly}
                    onChange={() => setShowActiveOnly((current) => !current)}
                  />
                  <span>Show active only</span>
                </label>
                <div className="status-note status-note--inline">
                  Watchlist stars stay in local browser state so the operator can pin priority instruments without backend writes.
                </div>
              </div>
            </Card>
          </div>
        </section>
      ) : null}

      <section className="page-grid">
        <Card
          title={`${selectedSummary?.label ?? "Market"} Instruments`}
          subtitle="Starred instruments stay at the top so the page behaves like a market-readiness dashboard instead of a static reference table."
          className="card--table"
        >
          <InstrumentsTable instruments={filteredInstruments} starredIds={starredIds} onToggleStar={handleToggleStar} />
          <div className="status-note">
            Snapshot refreshed from {new Date(overview.generatedAt).toLocaleString("en-GB")} and countdown updated at{" "}
            {new Date(now).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}.
          </div>
        </Card>
      </section>
    </main>
  );
}
