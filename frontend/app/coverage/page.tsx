import { CoverageLive } from "@/components/coverage/coverage-live";
import { UNAVAILABLE_COVERAGE_SUMMARY, UNAVAILABLE_FEED_STATE_RESPONSE, UNAVAILABLE_OPERATIONAL_TELEMETRY, UNAVAILABLE_SYSTEM_OPERATING_LIMITS, getCoverageSummary, getFeedState, getOperationalTelemetry, getSystemOperatingLimits, loadWithMeta } from "@/lib/api";

export default async function CoveragePage() {
  const [coverage, telemetry, operatingLimits, feedState] = await Promise.all([
    loadWithMeta(() => getCoverageSummary()),
    loadWithMeta(() => getOperationalTelemetry()),
    loadWithMeta(() => getSystemOperatingLimits()),
    loadWithMeta(() => getFeedState()),
  ]);

  return (
    <CoverageLive
      initialCoverage={coverage.data ?? UNAVAILABLE_COVERAGE_SUMMARY}
      initialTelemetry={telemetry.data ?? UNAVAILABLE_OPERATIONAL_TELEMETRY}
      initialOperatingLimits={operatingLimits.data ?? UNAVAILABLE_SYSTEM_OPERATING_LIMITS}
      initialFeedState={feedState.data ?? UNAVAILABLE_FEED_STATE_RESPONSE}
      initialErrors={{
        coverage: coverage.error,
        telemetry: telemetry.error,
        operatingLimits: operatingLimits.error,
        feedState: feedState.error,
      }}
    />
  );
}
