import { DashboardLive } from "@/components/dashboard/dashboard-live";
import {
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_DASHBOARD_SNAPSHOT,
  EMPTY_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getDashboardSnapshot,
  getExecutions,
  getOpenPositions,
  getStreamHealth,
  getTrades,
  withFallback,
} from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth] = await Promise.all([
    withFallback(() => getOpenPositions(), []),
    withFallback(() => getTrades(), []),
    withFallback(() => getExecutions(), []),
    withFallback(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    withFallback(() => getDashboardSnapshot(), EMPTY_DASHBOARD_SNAPSHOT),
    withFallback(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
  ]);

  return <DashboardLive initialPositions={positions} initialTrades={trades} initialExecutions={executions} initialBrokerAuth={brokerAuth} initialDashboard={dashboard} initialStreamHealth={streamHealth} />;
}
