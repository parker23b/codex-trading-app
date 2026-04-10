import { DashboardLive } from "@/components/dashboard/dashboard-live";
import {
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_COVERAGE_SUMMARY,
  EMPTY_CONTROL_PLANE_SUMMARY,
  EMPTY_DASHBOARD_SNAPSHOT,
  EMPTY_SYSTEM_OPERATING_LIMITS,
  EMPTY_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getControlPlaneSummary,
  getCoverageSummary,
  getDashboardSnapshot,
  getExecutions,
  getOpenPositions,
  getSystemOperatingLimits,
  getStreamHealth,
  getTrades,
  withFallback,
} from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth, coverage, controlPlane, operatingLimits] = await Promise.all([
    withFallback(() => getOpenPositions(), []),
    withFallback(() => getTrades(), []),
    withFallback(() => getExecutions(), []),
    withFallback(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    withFallback(() => getDashboardSnapshot(), EMPTY_DASHBOARD_SNAPSHOT),
    withFallback(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
    withFallback(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    withFallback(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY),
    withFallback(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
  ]);

  return <DashboardLive initialPositions={positions} initialTrades={trades} initialExecutions={executions} initialBrokerAuth={brokerAuth} initialDashboard={dashboard} initialStreamHealth={streamHealth} initialCoverage={coverage} initialControlPlane={controlPlane} initialOperatingLimits={operatingLimits} />;
}
