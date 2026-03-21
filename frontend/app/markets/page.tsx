import { MarketOverviewDashboard } from "@/components/markets/market-overview-dashboard";
import { getBackendMode, getMarketOverview } from "@/lib/api";

export default async function MarketsPage() {
  const [overview, backendMode] = await Promise.all([getMarketOverview("forex"), getBackendMode()]);

  return (
    <>
      <MarketOverviewDashboard initialOverview={overview} />
      {backendMode === "dev-fallback" ? (
        <div className="status-note">Market session data is using development fallback mode while the backend is unavailable.</div>
      ) : null}
    </>
  );
}
