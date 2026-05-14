import { DashboardLive } from "@/components/dashboard/dashboard-live";
import {
  UNAVAILABLE_ALLOCATION_DRIFT_SUMMARY,
  UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
  UNAVAILABLE_BROKER_AUTH_STATUS,
  UNAVAILABLE_COVERAGE_SUMMARY,
  UNAVAILABLE_CONTROL_PLANE_SUMMARY,
  UNAVAILABLE_DASHBOARD_SNAPSHOT,
  UNAVAILABLE_SYSTEM_OPERATING_LIMITS,
  UNAVAILABLE_STREAM_HEALTH_STATUS,
  getAllocationAlerts,
  getAllocationCycles,
  getAllocationDriftSummary,
  getAllocationExposureSummary,
  getAllocationIntents,
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
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth, coverage, controlPlane, operatingLimits, allocationExposure, allocationAlerts, allocationDrift, allocationCycles, allocationIntents] = await Promise.all([
    loadWithMeta(() => getOpenPositions()),
    loadWithMeta(() => getTrades()),
    loadWithMeta(() => getExecutions()),
    loadWithMeta(() => getBrokerAuthStatus()),
    loadWithMeta(() => getDashboardSnapshot()),
    loadWithMeta(() => getStreamHealth()),
    loadWithMeta(() => getCoverageSummary()),
    loadWithMeta(() => getControlPlaneSummary()),
    loadWithMeta(() => getSystemOperatingLimits()),
    loadWithMeta(() => getAllocationExposureSummary()),
    loadWithMeta(() => getAllocationAlerts({ limit: 40 })),
    loadWithMeta(() => getAllocationDriftSummary({ limit: 20, windowMinutes: 720 })),
    loadWithMeta(() => getAllocationCycles(12)),
    loadWithMeta(() => getAllocationIntents({ limit: 40 })),
  ]);

  return (
    <DashboardLive
      initialPositions={positions.data ?? []}
      initialTrades={trades.data ?? []}
      initialExecutions={executions.data ?? []}
      initialBrokerAuth={brokerAuth.data ?? UNAVAILABLE_BROKER_AUTH_STATUS}
      initialDashboard={dashboard.data ?? UNAVAILABLE_DASHBOARD_SNAPSHOT}
      initialStreamHealth={streamHealth.data ?? UNAVAILABLE_STREAM_HEALTH_STATUS}
      initialCoverage={coverage.data ?? UNAVAILABLE_COVERAGE_SUMMARY}
      initialControlPlane={controlPlane.data ?? UNAVAILABLE_CONTROL_PLANE_SUMMARY}
      initialOperatingLimits={operatingLimits.data ?? UNAVAILABLE_SYSTEM_OPERATING_LIMITS}
      initialAllocationExposure={allocationExposure.data ?? UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY}
      initialAllocationAlerts={allocationAlerts.data ?? []}
      initialAllocationDrift={allocationDrift.data ?? UNAVAILABLE_ALLOCATION_DRIFT_SUMMARY}
      initialAllocationCycles={allocationCycles.data ?? []}
      initialAllocationIntents={allocationIntents.data ?? []}
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
        allocationExposure: allocationExposure.error,
        allocationAlerts: allocationAlerts.error,
        allocationDrift: allocationDrift.error,
        allocationCycles: allocationCycles.error,
        allocationIntents: allocationIntents.error,
      }}
    />
  );
}
