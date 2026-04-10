"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { CompactTable, Panel, SplitPanel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getBrokerAuthStatus, getExecutions, getStrategies, getStreamHealth, startStrategy, stopStrategy } from "@/lib/api";
import { formatInstrumentLabel, formatPrice, formatSignedCurrency } from "@/lib/format";
import { BrokerAuthStatus, Execution, StrategyDefinition, StreamHealthStatus } from "@/lib/types";

type StrategyLiveProps = {
  initialStrategies: StrategyDefinition[];
  initialExecutions: Execution[];
  initialBrokerAuth: BrokerAuthStatus;
  initialStreamHealth: StreamHealthStatus;
};

function strategyTone(strategy: StrategyDefinition) {
  if (strategy.warning_message) {
    return "warning" as const;
  }
  return strategy.status === "RUNNING" ? "positive" as const : "inactive" as const;
}

export function StrategyLive({
  initialStrategies,
  initialExecutions,
  initialBrokerAuth,
  initialStreamHealth,
}: StrategyLiveProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [strategies, setStrategies] = useState(initialStrategies);
  const [executions, setExecutions] = useState(initialExecutions);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);
  const [selectedStrategyName, setSelectedStrategyName] = useState(initialStrategies[0]?.name ?? "");
  const [instrumentOverrides, setInstrumentOverrides] = useState<Record<string, string>>(
    Object.fromEntries(initialStrategies.map((strategy) => [strategy.name, strategy.instrument])),
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

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
        // Keep last good state visible.
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    setInstrumentOverrides((current) => ({
      ...Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy.instrument])),
      ...current,
    }));
    if (selectedStrategyName && strategies.some((strategy) => strategy.name === selectedStrategyName)) {
      return;
    }
    setSelectedStrategyName(strategies[0]?.name ?? "");
  }, [selectedStrategyName, strategies]);

  const sortedStrategies = useMemo(
    () =>
      strategies.slice().sort((left, right) => {
        if (left.status !== right.status) {
          return left.status === "RUNNING" ? -1 : 1;
        }
        return left.name.localeCompare(right.name);
      }),
    [strategies],
  );

  const selectedStrategy =
    sortedStrategies.find((strategy) => strategy.name === selectedStrategyName) ?? sortedStrategies[0] ?? null;

  const executionQueue = executions
    .slice()
    .sort((left, right) => new Date(right.last_transition_at).getTime() - new Date(left.last_transition_at).getTime());

  const runAction = (strategy: StrategyDefinition) => {
    startTransition(async () => {
      const instrument = instrumentOverrides[strategy.name];
      const result = await startStrategy(strategy.name, instrument);
      setStatusMessage(
        result.status === "started" ? `Started ${strategy.name} on ${formatInstrumentLabel(instrument)}.` : result.status,
      );
      router.refresh();
    });
  };

  const stopRuntime = (strategyName: string, instrument: string) => {
    startTransition(async () => {
      const result = await stopStrategy({ strategyName, instrument });
      setStatusMessage(
        result.status === "stopped" ? `Stopped ${strategyName} on ${formatInstrumentLabel(instrument)}.` : result.status,
      );
      router.refresh();
    });
  };

  return (
    <main className="console-page">
      <StatusStrip
        items={[
          { label: "Strategies", value: strategies.length, tone: "neutral" },
          {
            label: "Running",
            value: strategies.filter((strategy) => strategy.status === "RUNNING").length,
            tone: "positive",
            emphasis: "strong",
          },
          {
            label: "Warnings",
            value: strategies.filter((strategy) => strategy.warning_message).length,
            tone: strategies.some((strategy) => strategy.warning_message) ? "warning" : "positive",
            emphasis: "strong",
          },
          {
            label: "Broker",
            value: brokerAuth.state === "connected" ? "Connected" : brokerAuth.label,
            tone: brokerAuth.state === "connected" ? "positive" : "inactive",
          },
          {
            label: "Stream",
            value: streamHealth.connected ? "Live" : "Interrupted",
            tone: streamHealth.connected ? "positive" : "warning",
          },
        ]}
      />

      <SplitPanel
        left={
          <Panel title="Strategy Matrix" priority="primary" tone="neutral">
            <CompactTable
              rows={sortedStrategies}
              emptyLabel="No strategies are configured."
              getRowTone={(row) => strategyTone(row)}
              getRowActive={(row) => row.name === selectedStrategy?.name}
              columns={[
                {
                  key: "name",
                  header: "Strategy",
                  render: (row) => (
                    <button
                      type="button"
                      className={`console-link-button${row.name === selectedStrategy?.name ? " is-active" : ""}`}
                      onClick={() => setSelectedStrategyName(row.name)}
                    >
                      {row.name}
                    </button>
                  ),
                },
                {
                  key: "state",
                  header: "State",
                  render: (row) => <StatusPill label={row.status.toLowerCase()} tone={strategyTone(row)} />,
                },
                { key: "instrument", header: "Default", render: (row) => formatInstrumentLabel(row.instrument) },
                { key: "pnl", header: "PnL", render: (row) => formatSignedCurrency(row.current_pnl) },
              ]}
            />
          </Panel>
        }
        center={
          <Panel
            title={selectedStrategy ? selectedStrategy.name : "Selected Strategy"}
            priority="critical"
            tone={selectedStrategy ? strategyTone(selectedStrategy) : "inactive"}
            actions={
              selectedStrategy ? (
                <div className="console-inline-actions">
                  <button type="button" className="console-button" disabled={pending} onClick={() => runAction(selectedStrategy)}>
                    {pending ? "Starting..." : "Start Runtime"}
                  </button>
                </div>
              ) : null
            }
          >
            {selectedStrategy ? (
              <div className="detail-stack">
                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>State</span>
                    <strong>{selectedStrategy.status}</strong>
                    <em>{selectedStrategy.active_runtime_count ?? 0} runtimes</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Price</span>
                    <strong>
                      {selectedStrategy.last_price != null
                        ? formatPrice(selectedStrategy.last_price, selectedStrategy.instrument)
                        : "waiting"}
                    </strong>
                    <em>{selectedStrategy.price_status ?? "unknown"}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Open positions</span>
                    <strong>{selectedStrategy.open_position_count ?? 0}</strong>
                    <em>{selectedStrategy.win_rate}% win rate</em>
                  </div>
                </div>

                {selectedStrategy.warning_message ? (
                  <div className="console-alert console-alert--warning">
                    {selectedStrategy.warning_instrument ? `${formatInstrumentLabel(selectedStrategy.warning_instrument)}: ` : ""}
                    {selectedStrategy.warning_message}
                  </div>
                ) : null}

                <div className="detail-block">
                  <span className="console-kicker">Launch Instrument</span>
                  <select
                    className="console-select"
                    value={instrumentOverrides[selectedStrategy.name]}
                    onChange={(event) =>
                      setInstrumentOverrides((current) => ({
                        ...current,
                        [selectedStrategy.name]: event.target.value,
                      }))
                    }
                  >
                    {(selectedStrategy.instrument_options ?? []).map((option) => (
                      <option key={option.epic} value={option.epic}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                <CompactTable
                  dense
                  rows={selectedStrategy.active_runtimes ?? []}
                  emptyLabel="No active runtimes."
                  getRowTone={(row) => (row.has_open_position ? "warning" : "positive")}
                  columns={[
                    { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
                    {
                      key: "state",
                      header: "State",
                      render: (row) =>
                        row.has_open_position ? <StatusPill label={`${row.direction ?? "live"} position`} tone="warning" /> : <StatusPill label="watching" tone="positive" />,
                    },
                    {
                      key: "pnl",
                      header: "Unrealized",
                      render: (row) => (row.unrealized_pnl != null ? formatSignedCurrency(row.unrealized_pnl) : "n/a"),
                    },
                    {
                      key: "action",
                      header: "Action",
                      render: (row) => (
                        <button
                          type="button"
                          className="console-button console-button--ghost"
                          disabled={pending}
                          onClick={() => stopRuntime(selectedStrategy.name, row.instrument)}
                        >
                          Stop
                        </button>
                      ),
                    },
                  ]}
                />
              </div>
            ) : (
              <div className="console-empty">No strategy selected.</div>
            )}
          </Panel>
        }
        right={
          <div className="stack-layout">
            <Panel title="Config" priority="secondary" tone="neutral" compact>
              {selectedStrategy ? (
                <CompactTable
                  dense
                  rows={[
                    { label: "Position size", value: selectedStrategy.position_size },
                    { label: "Risk per trade", value: `${selectedStrategy.risk_per_trade}%` },
                    ...selectedStrategy.parameters.map((parameter) => ({
                      label: parameter.label,
                      value: parameter.value,
                    })),
                  ]}
                  emptyLabel="No parameters."
                  columns={[
                    { key: "label", header: "Parameter", render: (row) => row.label },
                    { key: "value", header: "Value", render: (row) => row.value },
                  ]}
                />
              ) : (
                <div className="console-empty">No strategy selected.</div>
              )}
            </Panel>

            <Panel title="Execution Feed" priority="passive" tone="inactive" compact>
              <CompactTable
                dense
                rows={executionQueue.slice(0, 8)}
                emptyLabel="No execution activity."
                getRowTone={(row) =>
                  row.status === "FAILED" || row.status === "NEEDS_MANUAL_REVIEW"
                    ? "negative"
                    : row.status === "RISK_REJECTED"
                      ? "warning"
                      : "neutral"
                }
                columns={[
                  { key: "strategy", header: "Strategy", render: (row) => row.strategy_name },
                  { key: "instrument", header: "Instrument", render: (row) => formatInstrumentLabel(row.instrument) },
                  { key: "status", header: "Status", render: (row) => row.status.replaceAll("_", " ") },
                ]}
              />
            </Panel>

            {statusMessage ? <div className="console-alert console-alert--neutral">{statusMessage}</div> : null}
          </div>
        }
      />
    </main>
  );
}
