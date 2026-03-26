"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatCurrency, formatInstrumentLabel, formatPrice } from "@/lib/format";
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
  const [configDrafts, setConfigDrafts] = useState<Record<string, StrategyDefinition>>(
    Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy])),
  );

  useEffect(() => {
    setInstrumentOverrides((current) => ({
      ...Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy.instrument])),
      ...current,
    }));
    setConfigDrafts(Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy])));
    setSelectedStrategy((current) => (current ? strategies.find((strategy) => strategy.name === current.name) ?? null : null));
  }, [strategies]);

  const sortedStrategies = useMemo(
    () =>
      Object.values(configDrafts).sort((left, right) =>
        left.status === right.status ? left.name.localeCompare(right.name) : left.status === "RUNNING" ? -1 : 1,
      ),
    [configDrafts],
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
      if (strategy.status === "RUNNING") {
        const result = await stopStrategy(instrument);
        setConfigDrafts((current) => ({
          ...current,
          [strategy.name]: {
            ...current[strategy.name],
            status: "STOPPED",
            current_pnl: 0,
          },
        }));
        setStatusMessage(result.status === "stopped" ? `Stopped ${strategy.name}.` : result.status);
      } else {
        const result = await startStrategy(strategy.name, instrument);
        setConfigDrafts((current) => ({
          ...current,
          [strategy.name]: {
            ...current[strategy.name],
            status: "RUNNING",
            instrument,
          },
        }));
        setStatusMessage(result.status === "started" ? `Started ${strategy.name}.` : result.status);
      }
      router.refresh();
    });
  };

  const selectedDraft = selectedStrategy ? configDrafts[selectedStrategy.name] : null;

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
                label={strategy.status === "RUNNING" ? "Running" : "Stopped"}
                tone={strategy.status === "RUNNING" ? "live" : "neutral"}
              />
            }
            className="strategy-card"
          >
            <div className="strategy-card__meta">
              <div className="strategy-stat">
                <span className="eyebrow">Instrument</span>
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
                <span className="eyebrow">Trade Count</span>
                <strong>{strategy.trade_count}</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Win Rate</span>
                <strong>{strategy.win_rate}%</strong>
              </div>
              <div className="strategy-stat">
                <span className="eyebrow">Last Price</span>
                <strong>{strategy.last_price != null ? formatPrice(strategy.last_price, strategy.instrument) : "Waiting..."}</strong>
                <div className="muted">{priceStatusLabel(strategy)}</div>
                {strategy.price_error ? <div className="muted">{strategy.price_error}</div> : null}
              </div>
            </div>
            <label className="strategy-card__instrument">
              <span className="eyebrow">Instrument Override</span>
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
            <div className="strategy-card__actions">
              <button className="button" disabled={pending} onClick={() => runAction(strategy)}>
                {strategy.status === "RUNNING" ? "Stop" : "Start"}
              </button>
              <button className="button secondary" onClick={() => setSelectedStrategy(strategy)}>
                Settings
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
                <button
                  className="button"
                  onClick={() => {
                    setStatusMessage(`Saved settings for ${selectedStrategy.name}.`);
                    setSelectedStrategy(null);
                  }}
                >
                  Save
                </button>
                <button className="button secondary" onClick={() => setSelectedStrategy(null)}>
                  Close
                </button>
              </div>
            </div>
            <div className="config-grid">
              <label>
                <span className="eyebrow">Position Size</span>
                <input
                  value={selectedDraft?.position_size ?? ""}
                  onChange={(event) =>
                    setConfigDrafts((current) => ({
                      ...current,
                      [selectedStrategy.name]: {
                        ...current[selectedStrategy.name],
                        position_size: Number(event.target.value),
                      },
                    }))
                  }
                />
              </label>
              <label>
                <span className="eyebrow">Risk Per Trade (%)</span>
                <input
                  value={selectedDraft?.risk_per_trade ?? ""}
                  onChange={(event) =>
                    setConfigDrafts((current) => ({
                      ...current,
                      [selectedStrategy.name]: {
                        ...current[selectedStrategy.name],
                        risk_per_trade: Number(event.target.value),
                      },
                    }))
                  }
                />
              </label>
              {selectedDraft?.parameters.map((parameter) => (
                <label key={parameter.key}>
                  <span className="eyebrow">{parameter.label}</span>
                  <input
                    value={parameter.value}
                    onChange={(event) =>
                      setConfigDrafts((current) => ({
                        ...current,
                        [selectedStrategy.name]: {
                          ...current[selectedStrategy.name],
                          parameters: current[selectedStrategy.name].parameters.map((currentParameter) =>
                            currentParameter.key === parameter.key
                              ? { ...currentParameter, value: Number(event.target.value) }
                              : currentParameter,
                          ),
                        },
                      }))
                    }
                  />
                </label>
              ))}
            </div>
            <p className="status-note">
              Settings are shown in a side panel to keep the main control surface focused on run-state and intervention.
            </p>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
