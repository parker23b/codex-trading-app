import { CoverageLive } from "@/components/coverage/coverage-live";
import { EMPTY_COVERAGE_SUMMARY, EMPTY_OPERATIONAL_TELEMETRY, EMPTY_SYSTEM_OPERATING_LIMITS, getCoverageSummary, getOperationalTelemetry, getSystemOperatingLimits, loadWithMeta } from "@/lib/api";

export default async function CoveragePage() {
  const [coverage, telemetry, operatingLimits] = await Promise.all([
    loadWithMeta(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    loadWithMeta(() => getOperationalTelemetry(), EMPTY_OPERATIONAL_TELEMETRY),
    loadWithMeta(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
  ]);

  return (
    <CoverageLive
      initialCoverage={coverage.data}
      initialTelemetry={telemetry.data}
      initialOperatingLimits={operatingLimits.data}
      initialErrors={{
        coverage: coverage.error,
        telemetry: telemetry.error,
        operatingLimits: operatingLimits.error,
      }}
    />
  );
}
