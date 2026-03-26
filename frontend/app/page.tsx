import { DashboardLive } from "@/components/dashboard/dashboard-live";
import { getBrokerAuthStatus, getDashboardSnapshot, getOpenPositions, getStreamHealth, getTrades } from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, brokerAuth, dashboard, streamHealth] = await Promise.all([
    getOpenPositions(),
    getTrades(),
    getBrokerAuthStatus(),
    getDashboardSnapshot(),
    getStreamHealth(),
  ]);

  return <DashboardLive initialPositions={positions} initialTrades={trades} initialBrokerAuth={brokerAuth} initialDashboard={dashboard} initialStreamHealth={streamHealth} />;
}
