import { RiskAllocationLive } from "@/components/risk/risk-allocation-live";
import {
  EMPTY_ALLOCATION_DRIFT_SUMMARY,
  EMPTY_ALLOCATION_EXPOSURE_SUMMARY,
  getAllocationAlerts,
  getAllocationCycle,
  getAllocationCycles,
  getAllocationDriftSummary,
  getAllocationExposureSummary,
  getAllocationIntents,
  loadWithMeta,
} from "@/lib/api";
import type { AllocationAlert, AllocationCycle, AllocationIntent } from "@/lib/types";

export default async function RiskPage() {
  const [exposure, alerts, drift, cycles, intents] = await Promise.all([
    loadWithMeta(() => getAllocationExposureSummary(), EMPTY_ALLOCATION_EXPOSURE_SUMMARY),
    loadWithMeta(() => getAllocationAlerts({ limit: 60 }), [] as AllocationAlert[]),
    loadWithMeta(() => getAllocationDriftSummary({ limit: 30, windowMinutes: 720 }), EMPTY_ALLOCATION_DRIFT_SUMMARY),
    loadWithMeta(() => getAllocationCycles(24), [] as AllocationCycle[]),
    loadWithMeta(() => getAllocationIntents({ limit: 60 }), [] as AllocationIntent[]),
  ]);

  const selectedCycleId = cycles.data[0]?.cycle_id;
  const selectedCycle = selectedCycleId
    ? await loadWithMeta(() => getAllocationCycle(selectedCycleId), null)
    : { data: null, error: null };

  return (
    <RiskAllocationLive
      initialExposure={exposure.data}
      initialAlerts={alerts.data}
      initialDrift={drift.data}
      initialCycles={cycles.data}
      initialIntents={intents.data}
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
