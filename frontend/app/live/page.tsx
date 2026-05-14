import { LiveSystemView } from "@/components/live/live-system-view";
import {
  UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
  UNAVAILABLE_BROKER_AUTH_STATUS,
  UNAVAILABLE_CONTROL_PLANE_SUMMARY,
  UNAVAILABLE_COVERAGE_SUMMARY,
  UNAVAILABLE_OPERATIONAL_TELEMETRY,
  UNAVAILABLE_STREAM_HEALTH_STATUS,
  getAllocationAlerts,
  getAllocationExposureSummary,
  getBrokerAuthStatus,
  getControlPlaneSummary,
  getCoverageSummary,
  getDomainEvents,
  getExecutions,
  getOperationalTelemetry,
  getOpenPositions,
  getStreamHealth,
  getStrategies,
  loadWithMeta,
} from "@/lib/api";

export default async function LivePage() {
  const [
    positions,
    executions,
    strategies,
    brokerAuth,
    streamHealth,
    coverage,
    controlPlane,
    telemetry,
    exposure,
    alerts,
    events,
  ] = await Promise.all([
    loadWithMeta(() => getOpenPositions()),
    loadWithMeta(() => getExecutions(120)),
    loadWithMeta(() => getStrategies()),
    loadWithMeta(() => getBrokerAuthStatus()),
    loadWithMeta(() => getStreamHealth()),
    loadWithMeta(() => getCoverageSummary()),
    loadWithMeta(() => getControlPlaneSummary()),
    loadWithMeta(() => getOperationalTelemetry()),
    loadWithMeta(() => getAllocationExposureSummary()),
    loadWithMeta(() => getAllocationAlerts({ limit: 20 })),
    loadWithMeta(() => getDomainEvents({ limit: 80 })),
  ]);

  return (
    <LiveSystemView
      initialData={{
        positions: positions.data ?? [],
        executions: executions.data ?? [],
        strategies: strategies.data ?? [],
        brokerAuth: brokerAuth.data ?? UNAVAILABLE_BROKER_AUTH_STATUS,
        streamHealth: streamHealth.data ?? UNAVAILABLE_STREAM_HEALTH_STATUS,
        coverage: coverage.data ?? UNAVAILABLE_COVERAGE_SUMMARY,
        controlPlane: controlPlane.data ?? UNAVAILABLE_CONTROL_PLANE_SUMMARY,
        telemetry: telemetry.data ?? UNAVAILABLE_OPERATIONAL_TELEMETRY,
        exposure: exposure.data ?? UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
        alerts: alerts.data ?? [],
        events: events.data ?? [],
      }}
      initialErrors={{
        positions: positions.error,
        executions: executions.error,
        strategies: strategies.error,
        brokerAuth: brokerAuth.error,
        streamHealth: streamHealth.error,
        coverage: coverage.error,
        controlPlane: controlPlane.error,
        telemetry: telemetry.error,
        exposure: exposure.error,
        alerts: alerts.error,
        events: events.error,
      }}
    />
  );
}
