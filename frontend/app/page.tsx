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
  loadWithMeta,
} from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth, coverage, controlPlane, operatingLimits] = await Promise.all([
    loadWithMeta(() => getOpenPositions(), []),
    loadWithMeta(() => getTrades(), []),
    loadWithMeta(() => getExecutions(), []),
    loadWithMeta(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    loadWithMeta(() => getDashboardSnapshot(), EMPTY_DASHBOARD_SNAPSHOT),
    loadWithMeta(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
    loadWithMeta(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    loadWithMeta(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY),
    loadWithMeta(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
  ]);

  return (
    <DashboardLive
      initialPositions={positions.data}
      initialTrades={trades.data}
      initialExecutions={executions.data}
      initialBrokerAuth={brokerAuth.data}
      initialDashboard={dashboard.data}
      initialStreamHealth={streamHealth.data}
      initialCoverage={coverage.data}
      initialControlPlane={controlPlane.data}
      initialOperatingLimits={operatingLimits.data}
      initialErrors={{
        positions: positions.error,
        trades: trades.error,
        executions: executions.error,
        brokerAuth: brokerAuth.error,
        dashboard: dashboard.error,
        streamHealth: streamHealth.error,
        coverage: coverage.error,
        controlPlane: controlPlane.error,
        operatingLimits: operatingLimits.error,
      }}
    />
  );
}
