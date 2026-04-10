import { StrategyLive } from "@/components/strategy/strategy-live";
import {
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getExecutions,
  getStrategies,
  getStreamHealth,
  loadWithMeta,
} from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, executions, brokerAuth, streamHealth] = await Promise.all([
    loadWithMeta(() => getStrategies(), []),
    loadWithMeta(() => getExecutions(), []),
    loadWithMeta(() => getBrokerAuthStatus(), EMPTY_BROKER_AUTH_STATUS),
    loadWithMeta(() => getStreamHealth(), EMPTY_STREAM_HEALTH_STATUS),
  ]);
  return (
    <StrategyLive
      initialStrategies={strategies.data}
      initialExecutions={executions.data}
      initialBrokerAuth={brokerAuth.data}
      initialStreamHealth={streamHealth.data}
      initialErrors={{
        strategies: strategies.error,
        executions: executions.error,
        brokerAuth: brokerAuth.error,
        streamHealth: streamHealth.error,
      }}
    />
  );
}
