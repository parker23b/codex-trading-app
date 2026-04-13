import { getAimeeSnapshot } from "@/lib/api";

import type { AimeeSnapshot } from "@/components/aimee/types";

export async function loadSnapshot(): Promise<AimeeSnapshot> {
  const snapshot = await getAimeeSnapshot();
  return {
    review: snapshot.review,
    history: snapshot.history,
    controlPlane: snapshot.controlPlane,
    coverage: snapshot.coverage,
    telemetry: snapshot.telemetry,
    events: snapshot.events,
    strategies: snapshot.strategies,
    updatedAt: snapshot.updatedAt ?? new Date().toISOString(),
  };
}

export function buildSnapshotSignature(snapshot: AimeeSnapshot) {
  return JSON.stringify({
    leadObservation: snapshot.review?.derived_observations[0]?.code ?? null,
    warnings: snapshot.review?.warnings.map((warning) => `${warning.code}:${warning.severity}`) ?? [],
    misalignedCount: snapshot.controlPlane?.misaligned_count ?? 0,
    blockedFamilies:
      snapshot.controlPlane?.families
        .filter((family) => family.deployment?.state === "BLOCKED" || family.deployment?.state === "DEGRADED")
        .map((family) => `${family.strategy_name}:${family.deployment?.state}`)
        .sort() ?? [],
    streamConnected: snapshot.telemetry?.stream_connected ?? null,
    reconciliationMismatches: snapshot.telemetry?.reconciliation_mismatches ?? 0,
    latestEvent: snapshot.events[0]?.id ?? null,
  });
}
