import { StrategyLive } from "@/components/strategy/strategy-live";
import { getStrategies, getStreamHealth } from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, streamHealth] = await Promise.all([getStrategies(), getStreamHealth()]);
  return <StrategyLive initialStrategies={strategies} initialStreamHealth={streamHealth} />;
}
