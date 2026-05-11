import { DashboardLive } from "@/components/dashboard/dashboard-live";
import {
  EMPTY_ALLOCATION_DRIFT_SUMMARY,
  EMPTY_ALLOCATION_EXPOSURE_SUMMARY,
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_COVERAGE_SUMMARY,
  EMPTY_CONTROL_PLANE_SUMMARY,
  EMPTY_DASHBOARD_SNAPSHOT,
  EMPTY_SYSTEM_OPERATING_LIMITS,
  EMPTY_STREAM_HEALTH_STATUS,
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
import type { AllocationAlert, AllocationCycle, AllocationIntent } from "@/lib/types";

export default async function DashboardPage() {
  const [positions, trades, executions, brokerAuth, dashboard, streamHealth, coverage, controlPlane, operatingLimits, allocationExposure, allocationAlerts, allocationDrift, allocationCycles, allocationIntents] = await Promise.all([
    loadWithMeta(() => getOpenPositions(), []),
    loadWithMeta(() => getTrades(), []),
    loadWithMeta(() => getExecutions(), []),
    loadWithMeta(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    loadWithMeta(() => getDashboardSnapshot(), EMPTY_DASHBOARD_SNAPSHOT),
    loadWithMeta(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
    loadWithMeta(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    loadWithMeta(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY),
    loadWithMeta(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
    loadWithMeta(() => getAllocationExposureSummary(), EMPTY_ALLOCATION_EXPOSURE_SUMMARY),
    loadWithMeta(() => getAllocationAlerts({ limit: 40 }), [] as AllocationAlert[]),
    loadWithMeta(() => getAllocationDriftSummary({ limit: 20, windowMinutes: 720 }), EMPTY_ALLOCATION_DRIFT_SUMMARY),
    loadWithMeta(() => getAllocationCycles(12), [] as AllocationCycle[]),
    loadWithMeta(() => getAllocationIntents({ limit: 40 }), [] as AllocationIntent[]),
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
      initialAllocationExposure={allocationExposure.data}
      initialAllocationAlerts={allocationAlerts.data}
      initialAllocationDrift={allocationDrift.data}
      initialAllocationCycles={allocationCycles.data}
      initialAllocationIntents={allocationIntents.data}
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
