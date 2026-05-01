import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { EMPTY_MARKET_CATALOGUE, EMPTY_STRATEGY_WATCHLIST, getMarketCatalogue, getMarketOverview, getStrategyWatchlist, loadWithMeta } from "@/lib/api";
import { MarketCategoryOverviewResponse } from "@/lib/types";

const EMPTY_FOREX_OVERVIEW: MarketCategoryOverviewResponse = {
  generatedAt: new Date(0).toISOString(),
  summary: {
    category: "forex",
    label: "Forex",
    description: "Investigate venue state, deployability, and strategy fit without continuous polling.",
    status: "LIMITED",
    headline: "Load on demand",
    detail: "Market inspection is on-demand to avoid overusing IG REST endpoints.",
    nextTransitionAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    nextTransitionLabel: "Refreshes",
    tradableCount: 0,
    activeCount: 0,
    totalCount: 0,
  },
  instruments: [],
};

export default async function MarketsPage() {
  const [overview, catalogue, strategyWatchlist] = await Promise.all([
    loadWithMeta(() => getMarketOverview("forex"), EMPTY_FOREX_OVERVIEW),
    loadWithMeta(() => getMarketCatalogue(), EMPTY_MARKET_CATALOGUE),
    loadWithMeta(() => getStrategyWatchlist(), EMPTY_STRATEGY_WATCHLIST),
  ]);

  return (
    <MarketOverviewDashboard
      initialOverview={overview.data}
      initialOverviewError={overview.error}
      initialCatalogue={catalogue.data}
      initialCatalogueError={catalogue.error}
      initialStrategyWatchlist={strategyWatchlist.data}
      initialStrategyWatchlistError={strategyWatchlist.error}
    />
  );
}
