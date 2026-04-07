"use client";

import { useEffect, useState } from "react";

import { NotificationCenter } from "@/components/dashboard/notification-center";
import { StrategyControlPanel } from "@/components/strategy/strategy-control-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getBrokerAuthStatus, getExecutions, getStrategies, getStreamHealth } from "@/lib/api";
import { BrokerAuthStatus, Execution, StrategyDefinition, StreamHealthStatus } from "@/lib/types";

type StrategyLiveProps = {
  initialStrategies: StrategyDefinition[];
  initialExecutions: Execution[];
  initialBrokerAuth: BrokerAuthStatus;
  initialStreamHealth: StreamHealthStatus;
};

export function StrategyLive({
  initialStrategies,
  initialExecutions,
  initialBrokerAuth,
  initialStreamHealth,
}: StrategyLiveProps) {
  const [strategies, setStrategies] = useState(initialStrategies);
  const [executions, setExecutions] = useState(initialExecutions);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);

  useEffect(() => {
    setStrategies(initialStrategies);
    setExecutions(initialExecutions);
    setBrokerAuth(initialBrokerAuth);
    setStreamHealth(initialStreamHealth);
  }, [initialStrategies, initialExecutions, initialBrokerAuth, initialStreamHealth]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [nextStrategies, nextExecutions, nextBrokerAuth, nextStreamHealth] = await Promise.all([
          getStrategies(),
          getExecutions(),
          getBrokerAuthStatus(),
          getStreamHealth(),
        ]);
        if (cancelled) {
          return;
        }
        setStrategies(nextStrategies);
        setExecutions(nextExecutions);
        setBrokerAuth(nextBrokerAuth);
        setStreamHealth(nextStreamHealth);
      } catch {
        // Preserve the last good payload on transient errors.
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const mode = strategies[0]?.account_type ?? "DEMO";

  return (
    <main className="page-grid">
      <NotificationCenter executions={executions} brokerAuth={brokerAuth} streamHealth={streamHealth} />
      <section className="top-command-bar">
        <ModeIndicator mode={mode} streamHealth={streamHealth} />
      </section>
      <Card
        title="Strategy Control Panel"
        subtitle="Each card can launch multiple instrument runtimes, show which ones are only scanning, and surface live exposure without collapsing everything into a single row."
      >
        <StrategyControlPanel strategies={strategies} />
      </Card>
    </main>
  );
}
