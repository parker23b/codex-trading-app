import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { UNAVAILABLE_MARKET_CATALOGUE, UNAVAILABLE_STRATEGY_WATCHLIST, getMarketCatalogue, getMarketOverview, getStrategyWatchlist, loadWithMeta } from "@/lib/api";
import { MarketCategoryOverviewResponse } from "@/lib/types";

const UNAVAILABLE_FOREX_OVERVIEW: MarketCategoryOverviewResponse = {
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
    loadWithMeta(() => getMarketOverview("forex")),
    loadWithMeta(() => getMarketCatalogue()),
    loadWithMeta(() => getStrategyWatchlist()),
  ]);

  return (
    <MarketOverviewDashboard
      initialOverview={overview.data ?? UNAVAILABLE_FOREX_OVERVIEW}
      initialOverviewError={overview.error}
      initialCatalogue={catalogue.data ?? UNAVAILABLE_MARKET_CATALOGUE}
      initialCatalogueError={catalogue.error}
      initialStrategyWatchlist={strategyWatchlist.data ?? UNAVAILABLE_STRATEGY_WATCHLIST}
      initialStrategyWatchlistError={strategyWatchlist.error}
    />
  );
}
