"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatCurrency, formatInstrumentLabel, formatPrice, formatSignedCurrency } from "@/lib/format";
import { startStrategy, stopStrategy } from "@/lib/api";
import { StrategyDefinition } from "@/lib/types";

type StrategyControlPanelProps = {
  strategies: StrategyDefinition[];
};

export function StrategyControlPanel({ strategies }: StrategyControlPanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [instrumentOverrides, setInstrumentOverrides] = useState<Record<string, string>>(
    Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy.instrument])),
  );
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDefinition | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    setInstrumentOverrides((current) => ({
      ...Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy.instrument])),
      ...current,
    }));
    setSelectedStrategy((current) => (current ? strategies.find((strategy) => strategy.name === current.name) ?? null : null));
  }, [strategies]);

  const sortedStrategies = useMemo(
    () =>
      strategies.slice().sort((left, right) =>
        left.status === right.status ? left.name.localeCompare(right.name) : left.status === "RUNNING" ? -1 : 1,
      ),
    [strategies],
  );
  const groupedInstrumentOptions = (strategy: StrategyDefinition) =>
    (strategy.instrument_options ?? []).reduce<Record<string, { epic: string; label: string; category: string }[]>>((groups, option) => {
      groups[option.category] = [...(groups[option.category] ?? []), option];
      return groups;
    }, {});
  const priceStatusLabel = (strategy: StrategyDefinition) => {
    switch (strategy.price_status) {
      case "LIVE":
        return "Live stream";
      case "POLLED":
        return "REST fallback";
      case "STALE":
        return "Price stale";
      case "ERROR":
        return "Price unavailable";
      case "POSITION":
        return "Position price";
      case "CACHED":
        return "Cached";
      case "REST":
        return "REST quote";
      default:
        return strategy.status === "RUNNING" ? "Waiting for price" : "No live price";
    }
  };

  const runAction = (strategy: StrategyDefinition) => {
    startTransition(async () => {
      const instrument = instrumentOverrides[strategy.name];
      const result = await startStrategy(strategy.name, instrument);
      setStatusMessage(result.status === "started" ? `Started ${strategy.name} on ${formatInstrumentLabel(instrument)}.` : result.status);
      router.refresh();
    });
  };

  const stopRuntime = (strategyName: string, instrument: string) => {
    startTransition(async () => {
      const result = await stopStrategy({ strategyName, instrument });
      setStatusMessage(
        result.status === "stopped"
          ? `Stopped ${strategyName} on ${formatInstrumentLabel(instrument)}.`
          : result.status,
      );
      router.refresh();
    });
  };

  return (
    <div className="strategy-workspace">
      <div className="strategy-grid">
        {sortedStrategies.map((strategy) => (
          <Card
            key={strategy.name}
            title={strategy.name}
            subtitle={strategy.description}
            action={
              <StatusBadge
                label={strategy.status === "RUNNING" ? `${strategy.active_runtime_count ?? 1} Live` : "Stopped"}
                tone={strategy.status === "RUNNING" ? "live" : "neutral"}
              />
            }
            className="strategy-card"
          >
            <div className="strategy-card__meta">
              <div className="strategy-stat">
                <span className="eyebrow">Next Instrument</span>
                <strong>{formatInstrumentLabel(instrumentOverrides[strategy.name])}</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Current PnL</span>
                <strong className={strategy.current_pnl >= 0 ? "value-positive live-pulse" : "value-negative live-pulse"}>
                  {strategy.current_pnl >= 0 ? "+" : "-"}
                  {formatCurrency(Math.abs(strategy.current_pnl))}
                </strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Live Runtimes</span>
                <strong>{strategy.active_runtime_count ?? 0}</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Open Positions</span>
                <strong>{strategy.open_position_count ?? 0}</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Last Price</span>
                <strong>{strategy.last_price != null ? formatPrice(strategy.last_price, strategy.instrument) : "Waiting..."}</strong>
                <div className="muted">{priceStatusLabel(strategy)}</div>
                {strategy.price_error ? <div className="muted">{strategy.price_error}</div> : null}
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Win Rate</span>
                <strong>{strategy.win_rate}%</strong>
              </div>
            </div>
            <div className="status-note status-note--inline">
              {strategy.active_runtime_count
                ? `${strategy.active_runtime_count} runtime${strategy.active_runtime_count === 1 ? "" : "s"} active across ${strategy.active_instruments?.length ?? 0} instrument${(strategy.active_instruments?.length ?? 0) === 1 ? "" : "s"}.`
                : "Stopped. Launch one or more instruments to start scanning."}
            </div>
            <label className="strategy-card__instrument">
              <span className="eyebrow">Launch Another Runtime</span>
              <select
                value={instrumentOverrides[strategy.name]}
                onChange={(event) =>
                  setInstrumentOverrides((current) => ({
                    ...current,
                    [strategy.name]: event.target.value,
                  }))
                }
              >
                {Object.entries(groupedInstrumentOptions(strategy)).map(([category, options]) => (
                  <optgroup key={category} label={category}>
                    {options.map((option) => (
                      <option key={option.epic} value={option.epic}>
                        {option.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            {strategy.active_runtimes?.length ? (
              <div className="strategy-runtime-list">
                {strategy.active_runtimes.map((runtime) => (
                  <div key={runtime.runtime_key} className="strategy-runtime-row">
                    <div className="cell-stack">
                      <strong>{formatInstrumentLabel(runtime.instrument)}</strong>
                      <span className="muted">
                        {runtime.has_open_position
                          ? `${runtime.direction ?? "LIVE"} ${runtime.broker_reference ?? "pending fill"}`
                          : "Scanning only"}
                      </span>
                    </div>
                    <div className="cell-stack">
                      <StatusBadge
                        label={runtime.has_open_position ? "Position Open" : "Watching"}
                        tone={runtime.has_open_position ? "live" : "neutral"}
                      />
                      <span className={((runtime.unrealized_pnl ?? 0) >= 0 ? "value-positive" : "value-negative")}>
                        {runtime.unrealized_pnl != null ? formatSignedCurrency(runtime.unrealized_pnl) : "No PnL"}
                      </span>
                    </div>
                    <button
                      className="button secondary table-action"
                      disabled={pending}
                      onClick={() => stopRuntime(strategy.name, runtime.instrument)}
                    >
                      Stop Runtime
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="status-note">No live runtimes. Start one or more instruments to begin scanning.</div>
            )}
            <div className="strategy-card__actions">
              <button className="button" disabled={pending} onClick={() => runAction(strategy)}>
                Start Runtime
              </button>
              <button className="button secondary" onClick={() => setSelectedStrategy(strategy)}>
                View Config
              </button>
            </div>
          </Card>
        ))}
      </div>
      {statusMessage ? <div className="status-note">{statusMessage}</div> : null}
      {selectedStrategy ? (
        <div className="config-drawer-backdrop" onClick={() => setSelectedStrategy(null)}>
          <aside className="config-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="config-drawer__header">
              <div>
                <div className="eyebrow">Strategy Configuration</div>
                <h3>{selectedStrategy.name}</h3>
              </div>
              <div className="strategy-card__actions">
                <button className="button secondary" onClick={() => setSelectedStrategy(null)}>
                  Close
                </button>
              </div>
            </div>
            <div className="config-grid">
              <div className="config-field">
                <span className="eyebrow">Position Size</span>
                <strong>{selectedStrategy.position_size}</strong>
              </div>
              <div className="config-field">
                <span className="eyebrow">Risk Per Trade (%)</span>
                <strong>{selectedStrategy.risk_per_trade}</strong>
              </div>
              {selectedStrategy.parameters.map((parameter) => (
                <div key={parameter.key} className="config-field">
                  <span className="eyebrow">{parameter.label}</span>
                  <strong>{parameter.value}</strong>
                </div>
              ))}
            </div>
            <p className="status-note">
              Configuration is read-only here. Runtime start and stop are live, but strategy setting edits are hidden until they can persist through the backend.
            </p>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
