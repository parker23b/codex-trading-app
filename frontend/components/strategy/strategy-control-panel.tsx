"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatInstrumentLabel, formatPrice, formatSignedCurrency } from "@/lib/format";
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
  const [selectedStrategyName, setSelectedStrategyName] = useState<string | null>(strategies[0]?.name ?? null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    setInstrumentOverrides((current) => ({
      ...Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy.instrument])),
      ...current,
    }));
    setSelectedStrategyName((current) => {
      if (current && strategies.some((strategy) => strategy.name === current)) {
        return current;
      }
      return strategies[0]?.name ?? null;
    });
  }, [strategies]);

  const sortedStrategies = useMemo(
    () =>
      strategies.slice().sort((left, right) =>
        left.status === right.status ? left.name.localeCompare(right.name) : left.status === "RUNNING" ? -1 : 1,
      ),
    [strategies],
  );

  const selectedStrategy =
    sortedStrategies.find((strategy) => strategy.name === selectedStrategyName) ?? sortedStrategies[0] ?? null;

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
    <div className="strategy-layout">
      <aside className="strategy-rail">
        <div className="strategy-rail__header">
          <div className="eyebrow">Operator List</div>
          <h3>Strategies</h3>
          <p className="muted">Select a strategy to inspect runtimes, launch instruments, and review its live configuration.</p>
        </div>
        <div className="strategy-list" aria-label="Strategies">
          {sortedStrategies.map((strategy) => {
            const isSelected = strategy.name === selectedStrategy?.name;
            return (
              <button
                key={strategy.name}
                type="button"
                aria-pressed={isSelected}
                className={`strategy-list-item${isSelected ? " strategy-list-item--active" : ""}`}
                onClick={() => {
                  setSelectedStrategyName(strategy.name);
                }}
              >
                <div className="strategy-list-item__topline">
                  <strong>{strategy.name}</strong>
                  <StatusBadge
                    label={strategy.status === "RUNNING" ? `${strategy.active_runtime_count ?? 1} Live` : "Stopped"}
                    tone={strategy.status === "RUNNING" ? "live" : "neutral"}
                  />
                </div>
                <p>{strategy.description}</p>
                <div className="strategy-list-item__metrics">
                  <span>{strategy.open_position_count ?? 0} positions</span>
                  <span>{strategy.win_rate}% win rate</span>
                  <span className={strategy.current_pnl >= 0 ? "value-positive" : "value-negative"}>
                    {formatSignedCurrency(strategy.current_pnl)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="strategy-detail">
        {selectedStrategy ? (
          <>
            <div className="strategy-detail__hero">
              <div>
                <div className="eyebrow">Selected Strategy</div>
                <h3>{selectedStrategy.name}</h3>
                <p className="muted">{selectedStrategy.description}</p>
              </div>
              <div className="strategy-detail__hero-badges">
                <StatusBadge
                  label={selectedStrategy.status === "RUNNING" ? "Running" : "Stopped"}
                  tone={selectedStrategy.status === "RUNNING" ? "live" : "neutral"}
                />
                <StatusBadge label={priceStatusLabel(selectedStrategy)} tone="neutral" />
              </div>
            </div>

            <div className="strategy-detail__metrics">
              <div className="strategy-stat">
                <span className="eyebrow">Current PnL</span>
                <strong className={selectedStrategy.current_pnl >= 0 ? "value-positive live-pulse" : "value-negative live-pulse"}>
                  {formatSignedCurrency(selectedStrategy.current_pnl)}
                </strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Last Price</span>
                <strong>
                  {selectedStrategy.last_price != null
                    ? formatPrice(selectedStrategy.last_price, selectedStrategy.instrument)
                    : "Waiting..."}
                </strong>
                {selectedStrategy.price_error ? <div className="muted">{selectedStrategy.price_error}</div> : null}
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Live Runtimes</span>
                <strong>{selectedStrategy.active_runtime_count ?? 0}</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Open Positions</span>
                <strong>{selectedStrategy.open_position_count ?? 0}</strong>
              </div>
            </div>

            {selectedStrategy.warning_message ? (
              <div className="status-note status-note--inline strategy-callout strategy-callout--warning">
                <StatusBadge label="Warning" tone="warning" />
                {selectedStrategy.warning_instrument ? `${formatInstrumentLabel(selectedStrategy.warning_instrument)}: ` : ""}
                {selectedStrategy.warning_message}
              </div>
            ) : null}

            <div className="strategy-detail__grid">
              <section className="strategy-panel">
                <div className="strategy-panel__header">
                  <div>
                    <div className="eyebrow">Operator Controls</div>
                    <h4>Runtime launcher</h4>
                  </div>
                </div>
                <label className="strategy-card__instrument">
                  <span className="eyebrow">Instrument</span>
                  <select
                    value={instrumentOverrides[selectedStrategy.name]}
                    onChange={(event) =>
                      setInstrumentOverrides((current) => ({
                        ...current,
                        [selectedStrategy.name]: event.target.value,
                      }))
                    }
                  >
                    {Object.entries(groupedInstrumentOptions(selectedStrategy)).map(([category, options]) => (
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
                <div className="strategy-detail__actions">
                  <button className="button" disabled={pending} onClick={() => runAction(selectedStrategy)}>
                    Start Runtime
                  </button>
                </div>
                <p className="status-note">
                  Launches a new runtime on the selected instrument without hiding the rest of the active deployment.
                </p>
              </section>

              <section className="strategy-panel">
                <div className="strategy-panel__header">
                  <div>
                    <div className="eyebrow">Settings</div>
                    <h4>Strategy configuration</h4>
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
                  Settings are visible here for the operator, but edits are still read-only until backend persistence is ready.
                </p>
              </section>
            </div>

            <section className="strategy-panel">
              <div className="strategy-panel__header">
                <div>
                  <div className="eyebrow">Live Deployment</div>
                  <h4>Active runtimes</h4>
                </div>
              </div>
              {selectedStrategy.active_runtime_count ? (
                <div className="status-note status-note--inline">
                  {selectedStrategy.active_runtime_count} runtime{selectedStrategy.active_runtime_count === 1 ? "" : "s"} active across{" "}
                  {selectedStrategy.active_instruments?.length ?? 0} instrument
                  {(selectedStrategy.active_instruments?.length ?? 0) === 1 ? "" : "s"}.
                </div>
              ) : (
                <div className="status-note status-note--inline">
                  No live runtimes. Start one or more instruments to begin scanning.
                </div>
              )}
              {selectedStrategy.active_runtimes?.length ? (
                <div className="strategy-runtime-list">
                  {selectedStrategy.active_runtimes.map((runtime) => (
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
                        <span className={(runtime.unrealized_pnl ?? 0) >= 0 ? "value-positive" : "value-negative"}>
                          {runtime.unrealized_pnl != null ? formatSignedCurrency(runtime.unrealized_pnl) : "No PnL"}
                        </span>
                      </div>
                      <button
                        className="button secondary table-action"
                        disabled={pending}
                        onClick={() => stopRuntime(selectedStrategy.name, runtime.instrument)}
                      >
                        Stop Runtime
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          </>
        ) : (
          <div className="empty-state">No strategies available.</div>
        )}

        {statusMessage ? <div className="status-note">{statusMessage}</div> : null}
      </section>
    </div>
  );
}
