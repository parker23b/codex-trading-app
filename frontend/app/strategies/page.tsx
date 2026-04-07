import { StrategyLive } from "@/components/strategy/strategy-live";
import {
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getExecutions,
  getStrategies,
  getStreamHealth,
  withFallback,
} from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, executions, brokerAuth, streamHealth] = await Promise.all([
    withFallback(() => getStrategies(), []),
    withFallback(() => getExecutions(), []),
    withFallback(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    withFallback(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
  ]);
  return (
    <StrategyLive
      initialStrategies={strategies}
      initialExecutions={executions}
      initialBrokerAuth={brokerAuth}
      initialStreamHealth={streamHealth}
    />
  );
}
