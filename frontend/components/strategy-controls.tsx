"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { startStrategy, stopStrategy } from "@/lib/api";
import { StrategyDefinition } from "@/lib/types";

type StrategyControlsProps = {
  strategies: StrategyDefinition[];
};

export function StrategyControls({ strategies }: StrategyControlsProps) {
  const router = useRouter();
  const [instrument, setInstrument] = useState("IX.D.FTSE.DAILY.IP");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleStart = (strategyName: string) => {
    setError(null);
    setStatusMessage(null);
    startTransition(async () => {
      try {
        const result = await startStrategy(strategyName, instrument);
        setStatusMessage(
          result.status.startsWith("simulated-start:")
            ? `Simulated start for ${strategyName} on ${instrument}.`
            : `Started ${strategyName} on ${instrument}.`,
        );
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to start strategy.");
      }
    });
  };

  const handleStop = () => {
    setError(null);
    setStatusMessage(null);
    startTransition(async () => {
      try {
        const result = await stopStrategy(instrument);
        setStatusMessage(
          result.status.startsWith("simulated-stop:")
            ? `Simulated stop for ${instrument}.`
            : `Stopped strategy on ${instrument}.`,
        );
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to stop strategy.");
      }
    });
  };

  return (
    <div className="stack">
      <label>
        <div className="muted">Instrument</div>
        <input
          value={instrument}
          onChange={(event) => setInstrument(event.target.value)}
          style={{
            width: "100%",
            marginTop: 8,
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "12px 14px",
          }}
        />
      </label>
      {strategies.map((strategy) => (
        <div className="card" key={strategy.name}>
          <div className="stack">
            <div>
              <h3 style={{ marginBottom: 8 }}>{strategy.name}</h3>
              <p className="muted">{strategy.description}</p>
            </div>
            <div className="actions">
              <button className="button" disabled={pending} onClick={() => handleStart(strategy.name)}>
                Start
              </button>
              <button className="button secondary" disabled={pending} onClick={handleStop}>
                Stop
              </button>
            </div>
          </div>
        </div>
      ))}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {statusMessage ? <p style={{ color: "var(--success)" }}>{statusMessage}</p> : null}
    </div>
  );
}
