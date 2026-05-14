import { StrategyLive } from "@/components/strategy/strategy-live";
import {
  UNAVAILABLE_BROKER_AUTH_STATUS,
  UNAVAILABLE_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getExecutions,
  getStrategies,
  getStreamHealth,
  loadWithMeta,
} from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, executions, brokerAuth, streamHealth] = await Promise.all([
    loadWithMeta(() => getStrategies()),
    loadWithMeta(() => getExecutions()),
    loadWithMeta(() => getBrokerAuthStatus()),
    loadWithMeta(() => getStreamHealth()),
  ]);
  return (
    <StrategyLive
      initialStrategies={strategies.data ?? []}
      initialExecutions={executions.data ?? []}
      initialBrokerAuth={brokerAuth.data ?? UNAVAILABLE_BROKER_AUTH_STATUS}
      initialStreamHealth={streamHealth.data ?? UNAVAILABLE_STREAM_HEALTH_STATUS}
      initialErrors={{
        strategies: strategies.error,
        executions: executions.error,
        brokerAuth: brokerAuth.error,
        streamHealth: streamHealth.error,
      }}
    />
  );
}
