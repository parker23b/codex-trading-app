import { DashboardLive } from "@/components/dashboard/dashboard-live";
import { getBrokerAuthStatus, getDashboardSnapshot, getExecutions, getOpenPositions, getStreamHealth, getTrades } from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth] = await Promise.all([
    getOpenPositions(),
    getTrades(),
    getExecutions(),
    getBrokerAuthStatus(),
    getDashboardSnapshot(),
    getStreamHealth(),
  ]);

  return <DashboardLive initialPositions={positions} initialTrades={trades} initialExecutions={executions} initialBrokerAuth={brokerAuth} initialDashboard={dashboard} initialStreamHealth={streamHealth} />;
}
