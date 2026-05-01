import { LiveSystemView } from "@/components/live/live-system-view";
import {
  EMPTY_ALLOCATION_EXPOSURE_SUMMARY,
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_CONTROL_PLANE_SUMMARY,
  EMPTY_COVERAGE_SUMMARY,
  EMPTY_OPERATIONAL_TELEMETRY,
  EMPTY_STREAM_HEALTH_STATUS,
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
    loadWithMeta(() => getOpenPositions(), []),
    loadWithMeta(() => getExecutions(120), []),
    loadWithMeta(() => getStrategies(), []),
    loadWithMeta(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    loadWithMeta(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
    loadWithMeta(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    loadWithMeta(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY),
    loadWithMeta(() => getOperationalTelemetry(), EMPTY_OPERATIONAL_TELEMETRY),
    loadWithMeta(() => getAllocationExposureSummary(), EMPTY_ALLOCATION_EXPOSURE_SUMMARY),
    loadWithMeta(() => getAllocationAlerts({ limit: 20, refresh: true }), []),
    loadWithMeta(() => getDomainEvents({ limit: 80 }), []),
  ]);

  return (
    <LiveSystemView
      initialData={{
        positions: positions.data,
        executions: executions.data,
        strategies: strategies.data,
        brokerAuth: brokerAuth.data,
        streamHealth: streamHealth.data,
        coverage: coverage.data,
        controlPlane: controlPlane.data,
        telemetry: telemetry.data,
        exposure: exposure.data,
        alerts: alerts.data,
        events: events.data,
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
