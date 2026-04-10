import { CoverageLive } from "@/components/coverage/coverage-live";
import { EMPTY_COVERAGE_SUMMARY, EMPTY_OPERATIONAL_TELEMETRY, EMPTY_SYSTEM_OPERATING_LIMITS, getCoverageSummary, getOperationalTelemetry, getSystemOperatingLimits, withFallback } from "@/lib/api";

export default async function CoveragePage() {
  const [coverage, telemetry, operatingLimits] = await Promise.all([
    withFallback(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    withFallback(() => getOperationalTelemetry(), EMPTY_OPERATIONAL_TELEMETRY),
    withFallback(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
  ]);

  return <CoverageLive initialCoverage={coverage} initialTelemetry={telemetry} initialOperatingLimits={operatingLimits} />;
}
