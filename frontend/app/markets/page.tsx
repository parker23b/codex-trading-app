import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { getMarketOverview } from "@/lib/api";

export default async function MarketsPage() {
  const overview = await getMarketOverview("forex");

  return (
    <>
      <MarketOverviewDashboard initialOverview={overview} />
    </>
  );
}
