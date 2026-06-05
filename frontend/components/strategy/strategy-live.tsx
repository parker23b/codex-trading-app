"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CompactTable, DataIndicator, InspectorDrawer, Panel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getBrokerAuthStatus, getExecutions, getStrategies, getStreamHealth, startStrategy, stopStrategy } from "@/lib/api";
import { formatIdentifierDisplay, formatIdentifierFingerprint, formatInstrumentLabel, formatPrice, formatSignedCurrency } from "@/lib/format";
import {
  closeExecutionSourceMeta,
  controlModeMeta,
  executionStatusMeta,
  runtimeModeMeta,
} from "@/lib/operator-vocabulary";
import { BrokerAuthStatus, Execution, SafeIdentifier, StrategyDefinition, StreamHealthStatus } from "@/lib/types";

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

type StrategyMutationTarget = {
  kind: "start" | "stop";
  strategyName: string;
  instrument: string;
};

type StrategyStatusNotice = {
  tone: "neutral" | "warning";
  message: string;
};

type StrategyRefreshResult = {
  failureDetail: string | null;
  strategies: StrategyDefinition[] | null;
};

function strategyErrorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

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
  const [statusNotice, setStatusNotice] = useState<StrategyStatusNotice | null>(null);
  const [mutationTarget, setMutationTarget] = useState<StrategyMutationTarget | null>(null);
  const [stopConfirmation, setStopConfirmation] = useState<{
    strategyName: string;
    instrument: string;
    brokerReference?: SafeIdentifier | string | null;
  } | null>(null);
  const [executionDrawerOpen, setExecutionDrawerOpen] = useState(false);
  const pending = mutationTarget !== null;

  useEffect(() => {
    setStrategies(initialStrategies);
    setExecutions(initialExecutions);
    setBrokerAuth(initialBrokerAuth);
    setStreamHealth(initialStreamHealth);
    setErrors(initialErrors);
  }, [initialStrategies, initialExecutions, initialBrokerAuth, initialErrors, initialStreamHealth]);

  const refreshResources = useCallback(async (): Promise<StrategyRefreshResult> => {
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
    const nextErrors = {
      strategies: nextStrategies.status === "rejected" ? strategyErrorMessage(nextStrategies.reason, "Failed to load strategies.") : null,
      executions: nextExecutions.status === "rejected" ? strategyErrorMessage(nextExecutions.reason, "Failed to load executions.") : null,
      brokerAuth: nextBrokerAuth.status === "rejected" ? strategyErrorMessage(nextBrokerAuth.reason, "Failed to load broker status.") : null,
      streamHealth: nextStreamHealth.status === "rejected" ? strategyErrorMessage(nextStreamHealth.reason, "Failed to load stream health.") : null,
    };
    setErrors(nextErrors);
    setLoading({
      strategies: false,
      executions: false,
      brokerAuth: false,
      streamHealth: false,
    });

    return {
      failureDetail: nextErrors.strategies ?? nextErrors.executions ?? nextErrors.brokerAuth ?? nextErrors.streamHealth,
      strategies: nextStrategies.status === "fulfilled" ? nextStrategies.value : null,
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      if (cancelled) {
        return;
      }
      await refreshResources();
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [refreshResources]);

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

  const mutationErrorMessage = (actionLabel: string, error: unknown) =>
    `${actionLabel} failed: ${error instanceof Error ? error.message : "backend truth could not be updated."}`;

  const startDisabledReason = (() => {
    if (!selectedStrategy) {
      return "Start unavailable because no strategy is selected.";
    }
    const selectedInstrument = instrumentOverrides[selectedStrategy.name]?.trim();
    if (!selectedInstrument) {
      return "Start unavailable because backend launch instrument truth is unavailable.";
    }
    if (!(selectedStrategy.instrument_options ?? []).length) {
      return "Start unavailable because backend launch instrument options are unavailable.";
    }
    return null;
  })();

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
    const instrument = instrumentOverrides[strategy.name]?.trim();
    if (!instrument) {
      setStatusNotice({
        tone: "warning",
        message: "Start unavailable because backend launch instrument truth is unavailable.",
      });
      return;
    }
    void (async () => {
      setMutationTarget({
        kind: "start",
        strategyName: strategy.name,
        instrument,
      });
      setStopConfirmation(null);
      setStatusNotice(null);
      try {
        await startStrategy(strategy.name, instrument);
        const refreshed = await refreshResources();
        const refreshedStrategy = refreshed.strategies?.find((entry) => entry.name === strategy.name);
        const runtimeVisible = refreshedStrategy?.active_runtimes?.some((runtime) => runtime.instrument === instrument) ?? false;
        if (refreshed.failureDetail) {
          setStatusNotice({
            tone: "warning",
            message: `Runtime start succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
          });
        } else if (!runtimeVisible) {
          setStatusNotice({
            tone: "warning",
            message: `Runtime start route succeeded, but refreshed backend truth does not yet show ${strategy.name} on ${formatInstrumentLabel(instrument)} as active.`,
          });
        } else {
          setStatusNotice({
            tone: "neutral",
            message: `Runtime start confirmed after backend truth refreshed for ${strategy.name} on ${formatInstrumentLabel(instrument)}.`,
          });
        }
      } catch (error) {
        setStatusNotice({
          tone: "warning",
          message: mutationErrorMessage("Runtime start", error),
        });
      } finally {
        setMutationTarget(null);
      }
    })();
  };

  const stopRuntime = async (strategyName: string, instrument: string) => {
    setMutationTarget({
      kind: "stop",
      strategyName,
      instrument,
    });
    setStatusNotice(null);
    try {
      await stopStrategy({ strategyName, instrument });
      const refreshed = await refreshResources();
      const refreshedStrategy = refreshed.strategies?.find((entry) => entry.name === strategyName);
      const runtimeStillVisible = refreshedStrategy?.active_runtimes?.some((runtime) => runtime.instrument === instrument) ?? false;
      if (refreshed.failureDetail) {
        setStatusNotice({
          tone: "warning",
          message: `Runtime stop succeeded, but backend truth refresh failed: ${refreshed.failureDetail}`,
        });
      } else if (runtimeStillVisible) {
        setStatusNotice({
          tone: "warning",
          message: `Runtime stop route succeeded, but refreshed backend truth still shows ${strategyName} on ${formatInstrumentLabel(instrument)} as active.`,
        });
      } else {
        setStatusNotice({
          tone: "neutral",
          message: `Runtime stop confirmed after backend truth refreshed for ${strategyName} on ${formatInstrumentLabel(instrument)}.`,
        });
      }
    } catch (error) {
      setStatusNotice({
        tone: "warning",
        message: mutationErrorMessage("Runtime stop", error),
      });
    } finally {
      setMutationTarget(null);
      setStopConfirmation(null);
    }
  };

  const executionSourceMeta = (execution: Execution) => {
    const detailSource = execution.details?.execution_source;
    if (typeof detailSource === "string") {
      return closeExecutionSourceMeta(detailSource);
    }
    const closeSource = execution.details?.close_execution_source;
    if (typeof closeSource === "string") {
      return closeExecutionSourceMeta(closeSource);
    }
    return null;
  };

  const recoveryContext = selectedStrategy?.persisted_runtimes?.find((runtime) => runtime.recovery_reason) ?? null;

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
              <button
                type="button"
                className="console-button"
                disabled={pending || Boolean(startDisabledReason)}
                onClick={() => runAction(selectedStrategy)}
              >
                {pending && mutationTarget?.kind === "start" && mutationTarget.strategyName === selectedStrategy.name ? "Starting..." : "Start Runtime"}
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
                disabled={pending}
              >
                <option value="" disabled>
                  Select instrument
                </option>
                {(selectedStrategy.instrument_options ?? []).map((option) => (
                  <option key={option.epic} value={option.epic}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="status-note status-note--inline">
                {startDisabledReason
                  ? startDisabledReason
                  : "Starts a manual runtime only. This does not imply governance approval, entry eligibility, or broker mutation."}
              </p>
            </div>

            {selectedStrategy.open_positions?.length ? (
              <div className="detail-block">
                <span className="console-kicker">Open Risk Book</span>
                {!(selectedStrategy.active_runtimes?.length ?? 0) ? (
                  <div className="console-alert console-alert--warning">
                    Known open risk remains visible even without an active runtime. Do not treat a stopped runtime as flat or resolved.
                    {recoveryContext?.recovery_reason ? (
                      <div className="status-note status-note--inline">
                        Recovery context: {recoveryContext.recovery_reason}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <CompactTable
                  dense
                  rows={selectedStrategy.open_positions}
                  emptyLabel="No open positions."
                  getRowTone={() => "warning"}
                  columns={[
                    {
                      key: "instrument",
                      header: "Instrument",
                      render: (row) => (
                        <div className="cell-stack">
                          <strong>{formatInstrumentLabel(row.instrument)}</strong>
                          <span className="muted">{`${row.direction} ${row.size} at ${formatPrice(row.open_price, row.instrument)}`}</span>
                        </div>
                      ),
                    },
                    {
                      key: "broker",
                      header: "Broker Ref",
                      render: (row) => (
                        <div className="cell-stack">
                          <span>{formatIdentifierDisplay(row.broker_reference) ?? "Broker reference unavailable"}</span>
                          {formatIdentifierFingerprint(row.broker_reference) ? (
                            <span className="muted">{formatIdentifierFingerprint(row.broker_reference)}</span>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: "risk",
                      header: "Open Risk",
                      render: (row) => (
                        <div className="cell-stack">
                          <StatusPill label={`${row.direction} position`} tone="warning" />
                          <span className="muted">{row.risk_percent != null ? `${row.risk_percent.toFixed(2)}% risk` : "Risk amount unavailable"}</span>
                        </div>
                      ),
                    },
                    {
                      key: "pnl",
                      header: "Unrealized",
                      render: (row) => (row.unrealized_pnl != null ? formatSignedCurrency(row.unrealized_pnl) : "n/a"),
                    },
                  ]}
                />
              </div>
            ) : null}

            {stopConfirmation && stopConfirmation.strategyName === selectedStrategy.name ? (
              <div className="console-alert console-alert--warning">
                Stop only ends the selected runtime process. Broker-confirmed open risk remains live and may still need an exit-capable runtime, recovery path, or manual review.
                <div className="status-note status-note--inline">
                  {formatInstrumentLabel(stopConfirmation.instrument)} · {formatIdentifierDisplay(stopConfirmation.brokerReference) ?? "Broker reference unavailable"}
                </div>
                <div className="console-inline-actions">
                  <button
                    type="button"
                    className="console-button"
                    disabled={pending}
                    onClick={() => stopRuntime(stopConfirmation.strategyName, stopConfirmation.instrument)}
                  >
                    {pending && mutationTarget?.kind === "stop" && mutationTarget.instrument === stopConfirmation.instrument ? "Stopping..." : "Confirm Stop Runtime"}
                  </button>
                  <button
                    type="button"
                    className="console-button console-button--ghost"
                    disabled={pending}
                    onClick={() => setStopConfirmation(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}

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
                        <span className="muted">{formatIdentifierDisplay(row.broker_reference) ?? "broker reference unavailable"}</span>
                        {formatIdentifierFingerprint(row.broker_reference) ? (
                          <span className="muted">{formatIdentifierFingerprint(row.broker_reference)}</span>
                        ) : null}
                        <span className="muted">{`${controlModeMeta(row.control_mode).label} / ${runtimeModeMeta(row.runtime_mode).label}`}</span>
                        {row.recovery_reason ? <span className="muted">{row.recovery_reason}</span> : null}
                        <span className="muted">Stopping this runtime does not close broker-confirmed open risk.</span>
                      </div>
                    ) : (
                      <div className="cell-stack">
                        <StatusPill label="watching" tone="positive" />
                        <span className="muted">{`${controlModeMeta(row.control_mode).label} / ${runtimeModeMeta(row.runtime_mode).label}`}</span>
                        {row.recovery_reason ? <span className="muted">{row.recovery_reason}</span> : null}
                      </div>
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
                      onClick={() => {
                        if (row.has_open_position) {
                          setStatusNotice(null);
                          setStopConfirmation({
                            strategyName: selectedStrategy.name,
                            instrument: row.instrument,
                            brokerReference: row.broker_reference,
                          });
                          return;
                        }
                        void stopRuntime(selectedStrategy.name, row.instrument);
                      }}
                    >
                      {pending && mutationTarget?.kind === "stop" && mutationTarget.strategyName === selectedStrategy.name && mutationTarget.instrument === row.instrument ? "Stopping..." : "Stop Runtime"}
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
      {statusNotice ? <div className={`console-alert console-alert--${statusNotice.tone}`}>{statusNotice.message}</div> : null}

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
            {
              key: "status",
              header: "Status",
              render: (row) => {
                const meta = executionStatusMeta(row.status);
                return <StatusPill label={meta.label} tone={meta.tone} title={meta.detail} />;
              },
            },
            {
              key: "source",
              header: "Source",
              render: (row) => {
                const meta = executionSourceMeta(row);
                return meta ? <StatusPill label={meta.label} tone={meta.tone} title={meta.detail} /> : "n/a";
              },
            },
            {
              key: "request",
              header: "Request",
              render: (row) =>
                formatIdentifierDisplay(row.client_request_id) ? (
                  <div className="cell-stack">
                    <span>{formatIdentifierDisplay(row.client_request_id)}</span>
                    {formatIdentifierFingerprint(row.client_request_id) ? (
                      <span className="muted">{formatIdentifierFingerprint(row.client_request_id)}</span>
                    ) : null}
                  </div>
                ) : (
                  "n/a"
                ),
            },
            {
              key: "broker",
              header: "Broker Ref",
              render: (row) =>
                formatIdentifierDisplay(row.broker_reference) ? (
                  <div className="cell-stack">
                    <span>{formatIdentifierDisplay(row.broker_reference)}</span>
                    {formatIdentifierFingerprint(row.broker_reference) ? (
                      <span className="muted">{formatIdentifierFingerprint(row.broker_reference)}</span>
                    ) : null}
                  </div>
                ) : (
                  "n/a"
                ),
            },
            { key: "reason", header: "Reason", render: (row) => row.error_message ?? row.reason ?? "n/a" },
          ]}
        />
      </InspectorDrawer>
    </main>
  );
}
