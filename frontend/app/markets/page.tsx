import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { getMarketOverview, withFallback } from "@/lib/api";
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
  const overview = await withFallback(() => getMarketOverview("forex"), EMPTY_FOREX_OVERVIEW);

  return <MarketOverviewDashboard initialOverview={overview} />;
}
