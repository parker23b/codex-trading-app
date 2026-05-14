import { RiskAllocationLive } from "@/components/risk/risk-allocation-live";
import {
  UNAVAILABLE_ALLOCATION_DRIFT_SUMMARY,
  UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
  getAllocationAlerts,
  getAllocationCycle,
  getAllocationCycles,
  getAllocationDriftSummary,
  getAllocationExposureSummary,
  getAllocationIntents,
  loadWithMeta,
} from "@/lib/api";
export default async function RiskPage() {
  const [exposure, alerts, drift, cycles, intents] = await Promise.all([
    loadWithMeta(() => getAllocationExposureSummary()),
    loadWithMeta(() => getAllocationAlerts({ limit: 60 })),
    loadWithMeta(() => getAllocationDriftSummary({ limit: 30, windowMinutes: 720 })),
    loadWithMeta(() => getAllocationCycles(24)),
    loadWithMeta(() => getAllocationIntents({ limit: 60 })),
  ]);

  const selectedCycleId = cycles.data?.[0]?.cycle_id;
  const selectedCycle = selectedCycleId
    ? await loadWithMeta(() => getAllocationCycle(selectedCycleId))
    : { data: null, error: null };

  return (
    <RiskAllocationLive
      initialExposure={exposure.data ?? UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY}
      initialAlerts={alerts.data ?? []}
      initialDrift={drift.data ?? UNAVAILABLE_ALLOCATION_DRIFT_SUMMARY}
      initialCycles={cycles.data ?? []}
      initialIntents={intents.data ?? []}
      initialSelectedCycle={selectedCycle.data}
      initialLoadErrors={{
        exposure: exposure.error,
        alerts: alerts.error,
        drift: drift.error,
        cycles: cycles.error,
        intents: intents.error,
        selectedCycle: selectedCycle.error,
      }}
    />
  );
}
