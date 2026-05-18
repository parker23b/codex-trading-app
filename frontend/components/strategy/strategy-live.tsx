"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { CompactTable, DataIndicator, InspectorDrawer, Panel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getBrokerAuthStatus, getExecutions, getStrategies, getStreamHealth, startStrategy, stopStrategy } from "@/lib/api";
import { formatInstrumentLabel, formatPrice, formatSignedCurrency } from "@/lib/format";
import { BrokerAuthStatus, Execution, StrategyDefinition, StreamHealthStatus } from "@/lib/types";

type StrategyResourceErrors = {
  strategies: string | null;
  executions: string | null;
  brokerAuth: string | null;
  streamHealth: string | null;
};

type StrategyLiveProps = {
  initialStrategies: StrategyDefinition[];
  initialExecutions: Execution[];
  initialBrokerAuth: BrokerAuthStatus;
  initialStreamHealth: StreamHealthStatus;
  initialErrors: StrategyResourceErrors;
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
  initialErrors,
}: StrategyLiveProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [strategies, setStrategies] = useState(initialStrategies);
  const [executions, setExecutions] = useState(initialExecutions);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);
  const [errors, setErrors] = useState(initialErrors);
  const [loading, setLoading] = useState({
    strategies: false,
    executions: false,
    brokerAuth: false,
    streamHealth: false,
  });
  const [selectedStrategyName, setSelectedStrategyName] = useState(initialStrategies[0]?.name ?? "");
  const [instrumentOverrides, setInstrumentOverrides] = useState<Record<string, string>>(
    Object.fromEntries(initialStrategies.map((strategy) => [strategy.name, strategy.instrument])),
  );
  const [dirtyOverrides, setDirtyOverrides] = useState<Record<string, boolean>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [executionDrawerOpen, setExecutionDrawerOpen] = useState(false);

  useEffect(() => {
    setStrategies(initialStrategies);
    setExecutions(initialExecutions);
    setBrokerAuth(initialBrokerAuth);
    setStreamHealth(initialStreamHealth);
    setErrors(initialErrors);
  }, [initialStrategies, initialExecutions, initialBrokerAuth, initialErrors, initialStreamHealth]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      setLoading({
        strategies: true,
        executions: true,
        brokerAuth: true,
        streamHealth: true,
      });
      const [nextStrategies, nextExecutions, nextBrokerAuth, nextStreamHealth] = await Promise.allSettled([
        getStrategies(),
        getExecutions(),
        getBrokerAuthStatus(),
        getStreamHealth(),
      ]);
      if (cancelled) {
        return;
      }
      if (nextStrategies.status === "fulfilled") {
        setStrategies(nextStrategies.value);
      }
      if (nextExecutions.status === "fulfilled") {
        setExecutions(nextExecutions.value);
      }
      if (nextBrokerAuth.status === "fulfilled") {
        setBrokerAuth(nextBrokerAuth.value);
      }
      if (nextStreamHealth.status === "fulfilled") {
        setStreamHealth(nextStreamHealth.value);
      }
      setErrors({
        strategies: nextStrategies.status === "rejected" ? (nextStrategies.reason instanceof Error ? nextStrategies.reason.message : "Failed to load strategies.") : null,
        executions: nextExecutions.status === "rejected" ? (nextExecutions.reason instanceof Error ? nextExecutions.reason.message : "Failed to load executions.") : null,
        brokerAuth: nextBrokerAuth.status === "rejected" ? (nextBrokerAuth.reason instanceof Error ? nextBrokerAuth.reason.message : "Failed to load broker status.") : null,
        streamHealth: nextStreamHealth.status === "rejected" ? (nextStreamHealth.reason instanceof Error ? nextStreamHealth.reason.message : "Failed to load stream health.") : null,
      });
      setLoading({
        strategies: false,
        executions: false,
        brokerAuth: false,
        streamHealth: false,
      });
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
      ...Object.fromEntries(
        strategies.map((strategy) => [
          strategy.name,
          dirtyOverrides[strategy.name] ? current[strategy.name] ?? strategy.instrument : strategy.instrument,
        ]),
      ),
    }));
    if (selectedStrategyName && strategies.some((strategy) => strategy.name === selectedStrategyName)) {
      return;
    }
    setSelectedStrategyName(strategies[0]?.name ?? "");
  }, [dirtyOverrides, selectedStrategyName, strategies]);

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

  const strategyCountValue = errors.strategies ? (
    <>
      -<DataIndicator state={loading.strategies ? "loading" : "error"} message={errors.strategies} />
    </>
  ) : (
    strategies.length
  );
  const brokerValue = errors.brokerAuth ? (
    <>
      -<DataIndicator state={loading.brokerAuth ? "loading" : "error"} message={errors.brokerAuth} />
    </>
  ) : brokerAuth.state === "connected" ? (
    "Connected"
  ) : (
    brokerAuth.label
  );
  const streamValue = errors.streamHealth ? (
    <>
      -<DataIndicator state={loading.streamHealth ? "loading" : "error"} message={errors.streamHealth} />
    </>
  ) : streamHealth.connected ? (
    "Live"
  ) : (
    "Interrupted"
  );

  const runAction = (strategy: StrategyDefinition) => {
    startTransition(async () => {
      try {
        const instrument = instrumentOverrides[strategy.name];
        const result = await startStrategy(strategy.name, instrument);
        setStatusMessage(
          result.status === "started" ? `Started ${strategy.name} on ${formatInstrumentLabel(instrument)}.` : result.status,
        );
        router.refresh();
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Failed to start strategy.");
      }
    });
  };

  const stopRuntime = (strategyName: string, instrument: string) => {
    startTransition(async () => {
      try {
        const result = await stopStrategy({ strategyName, instrument });
        setStatusMessage(
          result.status === "stopped" ? `Stopped ${strategyName} on ${formatInstrumentLabel(instrument)}.` : result.status,
        );
        router.refresh();
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Failed to stop strategy.");
      }
    });
  };

  return (
    <main className="console-page console-page--dense">
      <StatusStrip
        items={[
          { label: "Strategies", value: strategyCountValue, tone: errors.strategies ? "inactive" : "neutral", meta: errors.strategies ?? undefined },
          {
            label: "Running",
            value: errors.strategies ? "-" : strategies.filter((strategy) => strategy.status === "RUNNING").length,
            tone: errors.strategies ? "inactive" : "positive",
            emphasis: "strong",
          },
          {
            label: "Authorised",
            value: errors.strategies ? "-" : strategies.filter((strategy) => strategy.authorized).length,
            tone: errors.strategies ? "inactive" : "positive",
            emphasis: "strong",
          },
          {
            label: "Candidates Today",
            value: errors.strategies ? "-" : strategies.reduce((sum, strategy) => sum + (strategy.candidates_generated_today ?? 0), 0),
            tone: errors.strategies ? "inactive" : "neutral",
            meta: "generated",
          },
          {
            label: "Warnings",
            value: errors.strategies ? "-" : strategies.filter((strategy) => strategy.warning_message).length,
            tone: errors.strategies ? "inactive" : strategies.some((strategy) => strategy.warning_message) ? "warning" : "positive",
            emphasis: "strong",
          },
          {
            label: "Broker",
            value: brokerValue,
            tone: errors.brokerAuth ? "inactive" : brokerAuth.state === "connected" ? "positive" : "inactive",
            meta: errors.brokerAuth ?? brokerAuth.detail,
          },
          {
            label: "Stream",
            value: streamValue,
            tone: errors.streamHealth ? "inactive" : streamHealth.connected ? "positive" : "warning",
            meta: errors.streamHealth ?? undefined,
          },
        ]}
      />

      <section className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
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
              { key: "auth", header: "Authorised", render: (row) => <StatusPill label={row.authorized ? "yes" : "no"} tone={row.authorized ? "positive" : "inactive"} /> },
              { key: "evaluating", header: "Evaluating", render: (row) => row.evaluating_instrument_count ?? row.active_runtime_count ?? 0 },
              { key: "candidates", header: "Today", render: (row) => `${row.candidates_generated_today ?? 0} / ${row.candidates_promoted_today ?? 0} / ${row.candidates_blocked_today ?? 0}` },
              { key: "pnl", header: "PnL", render: (row) => formatSignedCurrency(row.current_pnl) },
            ]}
          />
        </Panel>

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
      </section>

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
              <button type="button" className="console-button console-button--ghost" onClick={() => setExecutionDrawerOpen(true)}>
                Execution Feed
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
              <div className="summary-bar__item">
                <span>Candidates today</span>
                <strong>{selectedStrategy.candidates_generated_today ?? 0}</strong>
                <em>{selectedStrategy.candidates_promoted_today ?? 0} promoted / {selectedStrategy.candidates_blocked_today ?? 0} blocked</em>
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
                  {
                    setInstrumentOverrides((current) => ({
                      ...current,
                      [selectedStrategy.name]: event.target.value,
                    }));
                    setDirtyOverrides((current) => ({
                      ...current,
                      [selectedStrategy.name]: true,
                    }));
                  }
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
                    row.has_open_position ? (
                      <div className="cell-stack">
                        <StatusPill label={`${row.direction ?? "live"} position`} tone="warning" />
                        <span className="muted">{row.broker_reference ?? "broker reference unavailable"}</span>
                        <span className="muted">Stopping this runtime does not close broker-confirmed open risk.</span>
                      </div>
                    ) : (
                      <StatusPill label="watching" tone="positive" />
                    ),
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
                      title={
                        row.has_open_position
                          ? "Stops the runtime process only; broker-confirmed open risk remains visible for exit management."
                          : "Stops this runtime."
                      }
                      onClick={() => stopRuntime(selectedStrategy.name, row.instrument)}
                    >
                      Stop Runtime
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

      {errors.executions ? <div className="console-alert console-alert--warning">Execution feed unavailable. {errors.executions}</div> : null}
      {statusMessage ? <div className="console-alert console-alert--neutral">{statusMessage}</div> : null}

      <InspectorDrawer
        title="Execution Feed"
        subtitle="Recent execution transitions across all strategies."
        open={executionDrawerOpen}
        onClose={() => setExecutionDrawerOpen(false)}
      >
        <CompactTable
          dense
          rows={executionQueue.slice(0, 20)}
          emptyLabel={errors.executions ? "Execution feed unavailable." : "No execution activity."}
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
            { key: "request", header: "Request", render: (row) => row.client_request_id ?? "n/a" },
            { key: "broker", header: "Broker Ref", render: (row) => row.broker_reference ?? "n/a" },
            { key: "reason", header: "Reason", render: (row) => row.error_message ?? row.reason ?? "n/a" },
          ]}
        />
      </InspectorDrawer>
    </main>
  );
}
