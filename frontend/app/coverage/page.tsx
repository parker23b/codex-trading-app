import { CoverageLive } from "@/components/coverage/coverage-live";
import { EMPTY_COVERAGE_SUMMARY, EMPTY_FEED_STATE_RESPONSE, EMPTY_OPERATIONAL_TELEMETRY, EMPTY_SYSTEM_OPERATING_LIMITS, getCoverageSummary, getFeedState, getOperationalTelemetry, getSystemOperatingLimits, loadWithMeta } from "@/lib/api";

export default async function CoveragePage() {
  const [coverage, telemetry, operatingLimits, feedState] = await Promise.all([
    loadWithMeta(() => getCoverageSummary(), EMPTY_COVERAGE_SUMMARY),
    loadWithMeta(() => getOperationalTelemetry(), EMPTY_OPERATIONAL_TELEMETRY),
    loadWithMeta(() => getSystemOperatingLimits(), EMPTY_SYSTEM_OPERATING_LIMITS),
    loadWithMeta(() => getFeedState(), EMPTY_FEED_STATE_RESPONSE),
  ]);

  return (
    <CoverageLive
      initialCoverage={coverage.data}
      initialTelemetry={telemetry.data}
      initialOperatingLimits={operatingLimits.data}
      initialFeedState={feedState.data}
      initialErrors={{
        coverage: coverage.error,
        telemetry: telemetry.error,
        operatingLimits: operatingLimits.error,
        feedState: feedState.error,
      }}
    />
  );
}
