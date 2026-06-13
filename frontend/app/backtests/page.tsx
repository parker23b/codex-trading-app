import { BacktestsLive } from "@/components/backtests/backtests-live";
import {
  getBacktests,
  getHistoricalDatasets,
  getHistoricalProviders,
  getStrategies,
  loadWithMeta,
} from "@/lib/api";

export default async function BacktestsPage() {
  const [providers, datasets, runs, strategies] = await Promise.all([
    loadWithMeta(() => getHistoricalProviders()),
    loadWithMeta(() => getHistoricalDatasets()),
    loadWithMeta(() => getBacktests()),
    loadWithMeta(() => getStrategies()),
  ]);

  return (
    <BacktestsLive
      initialProviders={providers.data ?? []}
      initialDatasets={datasets.data ?? []}
      initialRuns={runs.data ?? []}
      initialStrategies={strategies.data ?? []}
      initialError={
        providers.error ?? datasets.error ?? runs.error ?? strategies.error
      }
    />
  );
}
