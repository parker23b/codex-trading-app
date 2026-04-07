import { StrategyLive } from "@/components/strategy/strategy-live";
import { getBrokerAuthStatus, getExecutions, getStrategies, getStreamHealth } from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, executions, brokerAuth, streamHealth] = await Promise.all([
    getStrategies(),
    getExecutions(),
    getBrokerAuthStatus(),
    getStreamHealth(),
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
