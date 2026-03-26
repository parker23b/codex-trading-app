"use client";

import { useEffect, useState } from "react";

import { StrategyControlPanel } from "@/components/strategy/strategy-control-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getStrategies, getStreamHealth } from "@/lib/api";
import { StrategyDefinition, StreamHealthStatus } from "@/lib/types";

type StrategyLiveProps = {
  initialStrategies: StrategyDefinition[];
  initialStreamHealth: StreamHealthStatus;
};

export function StrategyLive({ initialStrategies, initialStreamHealth }: StrategyLiveProps) {
  const [strategies, setStrategies] = useState(initialStrategies);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);

  useEffect(() => {
    setStrategies(initialStrategies);
    setStreamHealth(initialStreamHealth);
  }, [initialStrategies, initialStreamHealth]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [nextStrategies, nextStreamHealth] = await Promise.all([getStrategies(), getStreamHealth()]);
        if (cancelled) {
          return;
        }
        setStrategies(nextStrategies);
        setStreamHealth(nextStreamHealth);
      } catch {
        // Preserve the last good payload on transient errors.
      }
    };

    const intervalId = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const mode = strategies[0]?.account_type ?? "DEMO";

  return (
    <main className="page-grid">
      <section className="top-command-bar">
        <ModeIndicator mode={mode} streamHealth={streamHealth} />
      </section>
      <Card
        title="Strategy Control Panel"
        subtitle="Each card exposes run-state, current performance, and configuration so you can operate strategies like a control surface, not a list."
      >
        <StrategyControlPanel strategies={strategies} />
      </Card>
    </main>
  );
}
