import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { EMPTY_MARKET_CATALOGUE, EMPTY_STRATEGY_WATCHLIST, getMarketCatalogue, getMarketOverview, getStrategyWatchlist, loadWithMeta } from "@/lib/api";
import { MarketCategoryOverviewResponse } from "@/lib/types";

const EMPTY_FOREX_OVERVIEW: MarketCategoryOverviewResponse = {
  generatedAt: new Date(0).toISOString(),
  summary: {
    category: "forex",
    label: "Forex",
    description: "Market overview backend data is unavailable.",
    status: "UNAVAILABLE",
    headline: "Backend unavailable",
    detail: "Market overview could not be loaded. Counts are unavailable, not zero market truth.",
    nextTransitionAt: new Date(0).toISOString(),
    nextTransitionLabel: "Unavailable",
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
