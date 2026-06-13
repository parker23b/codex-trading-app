"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { LineChart } from "@/components/line-chart";
import {
  CompactTable,
  DataIndicator,
  Panel,
  StatusPill,
  StatusStrip,
} from "@/components/console/primitives";
import {
  createBacktest,
  getBacktest,
  getBacktestEquity,
  getBacktestInstruments,
  getBacktestMetrics,
  getBacktestTrades,
  getBacktestWarnings,
  getBacktests,
  getHistoricalDataset,
  getHistoricalDatasets,
  importHistoricalCsv,
  importHistoricalProviderData,
} from "@/lib/api";
import type {
  BacktestEquityPoint,
  BacktestInstrument,
  BacktestMetrics,
  BacktestRun,
  BacktestTrade,
  BacktestWarning,
  HistoricalDataset,
  HistoricalProviderCapabilities,
  StrategyDefinition,
} from "@/lib/types";

type Props = {
  initialProviders: HistoricalProviderCapabilities[];
  initialDatasets: HistoricalDataset[];
  initialRuns: BacktestRun[];
  initialStrategies: StrategyDefinition[];
  initialError: string | null;
};

type ResultBundle = {
  run: BacktestRun;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  equity: BacktestEquityPoint[];
  warnings: BacktestWarning[];
  instruments: BacktestInstrument[];
};

const inputClass =
  "w-full rounded-[10px] border border-[color:var(--border)] bg-[color:var(--bg-elevated)] px-3 py-2 text-sm";
const buttonClass =
  "rounded-[10px] border border-[color:var(--border-strong)] bg-[color:var(--accent-soft)] px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The backend action failed.";
}

function localInputValue(value?: string | null) {
  if (!value) return "";
  return utcDate(value).toISOString().slice(0, 16);
}

function utcDate(value: string) {
  const includesTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(includesTimezone ? value : `${value}Z`);
}

function utcTimestampLabel(value: string) {
  return `${utcDate(value).toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

function utcChartLabel(value: string) {
  return utcDate(value).toISOString().slice(5, 16).replace("T", " ");
}

function coverageEndValue(dataset: HistoricalDataset | null) {
  if (!dataset?.latest_at) return "";
  const seconds: Record<string, number> = {
    S5: 5,
    "1m": 60,
    M1: 60,
    "5m": 300,
    M5: 300,
    "15m": 900,
    M15: 900,
    "30m": 1800,
    "1h": 3600,
    H1: 3600,
  };
  const end = new Date(
    new Date(dataset.latest_at).getTime() +
      (seconds[dataset.base_timeframe] ?? 60) * 1000,
  );
  return localInputValue(end.toISOString());
}

function toIso(value: string) {
  return utcDate(value).toISOString();
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value : null;
}

function money(value: unknown) {
  const amount = numberValue(value);
  return amount == null
    ? "Undefined"
    : new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP",
        maximumFractionDigits: 2,
      }).format(amount);
}

export function BacktestsLive({
  initialProviders,
  initialDatasets,
  initialRuns,
  initialStrategies,
  initialError,
}: Props) {
  const [datasets, setDatasets] = useState(initialDatasets);
  const [runs, setRuns] = useState(initialRuns);
  const [selectedDataset, setSelectedDataset] = useState<HistoricalDataset | null>(
    null,
  );
  const [selectedRunId, setSelectedRunId] = useState(initialRuns[0]?.id ?? "");
  const [result, setResult] = useState<ResultBundle | null>(null);
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const readyDatasets = datasets.filter((dataset) => dataset.status === "READY");
  const configuredProviders = initialProviders.filter((provider) => provider.configured);

  const refreshLists = useCallback(async () => {
    const [nextDatasets, nextRuns] = await Promise.all([
      getHistoricalDatasets(),
      getBacktests(),
    ]);
    setDatasets(nextDatasets);
    setRuns(nextRuns);
  }, []);

  const loadDataset = useCallback(async (datasetId: string) => {
    if (!datasetId) {
      setSelectedDataset(null);
      return;
    }
    try {
      setSelectedDataset(await getHistoricalDataset(datasetId));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }, []);

  const loadResult = useCallback(async (runId: string) => {
    if (!runId) {
      setResult(null);
      return;
    }
    setPending("result");
    try {
      const [run, metrics, trades, equity, warnings, instruments] =
        await Promise.all([
          getBacktest(runId),
          getBacktestMetrics(runId),
          getBacktestTrades(runId),
          getBacktestEquity(runId),
          getBacktestWarnings(runId),
          getBacktestInstruments(runId),
        ]);
      setResult({ run, metrics, trades, equity, warnings, instruments });
      setError(null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(null);
    }
  }, []);

  useEffect(() => {
    if (!selectedDataset && readyDatasets[0]) {
      void loadDataset(readyDatasets[0].id);
    }
  }, [loadDataset, readyDatasets, selectedDataset]);

  useEffect(() => {
    if (selectedRunId) void loadResult(selectedRunId);
  }, [loadResult, selectedRunId]);

  const handleCsvImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("csv_file");
    if (!(file instanceof File) || !file.size) {
      setError("Choose a CSV file before importing.");
      return;
    }
    setPending("csv");
    setNotice(null);
    try {
      const dataset = await importHistoricalCsv({
        display_name: String(form.get("display_name") || file.name),
        csv_text: await file.text(),
        asset_class: String(form.get("asset_class") || "FOREX"),
        venue: String(form.get("venue") || "USER_SUPPLIED"),
        market_type: String(form.get("market_type") || "SPOT_FX"),
        source_identifier: file.name,
        source_metadata: { filename: file.name, size_bytes: file.size },
      });
      await refreshLists();
      await loadDataset(dataset.id);
      setNotice(`Imported immutable dataset ${dataset.display_name}.`);
      setError(null);
      event.currentTarget.reset();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(null);
    }
  };

  const handleProviderImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const providerId = String(form.get("provider_id"));
    const provider = initialProviders.find(
      (item) => item.provider_id === providerId,
    );
    setPending("provider");
    setNotice(null);
    try {
      const dataset = await importHistoricalProviderData({
        display_name: String(form.get("display_name")),
        provider_id: providerId,
        instruments: String(form.get("instruments"))
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        timeframe: String(form.get("timeframe")),
        start_at: toIso(String(form.get("start_at"))),
        end_at: toIso(String(form.get("end_at"))),
        asset_class: String(form.get("asset_class")),
        market_type: String(form.get("market_type")),
        venue: provider?.venue,
      });
      await refreshLists();
      await loadDataset(dataset.id);
      setNotice(`Imported immutable dataset ${dataset.display_name}.`);
      setError(null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(null);
    }
  };

  const handleBacktest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedDataset) {
      setError("Select a ready immutable dataset.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const instruments = form.getAll("shortlist").map(String);
    const spreadModel = String(form.get("spread_model"));
    setPending("backtest");
    setNotice(null);
    try {
      const run = await createBacktest({
        name: String(form.get("name") || "") || null,
        notes: String(form.get("notes") || "") || null,
        strategy_identifier: String(form.get("strategy_identifier")),
        profile_name: String(form.get("profile_name") || "default"),
        dataset_id: selectedDataset.id,
        shortlist: instruments,
        timeframe: String(form.get("timeframe")),
        start_at: toIso(String(form.get("start_at"))),
        end_at: toIso(String(form.get("end_at"))),
        starting_capital: Number(form.get("starting_capital")),
        position_sizing_mode: String(form.get("position_sizing_mode")),
        risk_configuration: {
          fixed_size: Number(form.get("fixed_size")),
          risk_per_trade_percent: Number(form.get("risk_per_trade_percent")),
          fallback_stop_percent: Number(form.get("fallback_stop_percent")),
          max_open_positions: Number(form.get("max_open_positions")),
        },
        spread_model: spreadModel,
        spread_assumption: { value: Number(form.get("spread_value")) },
        slippage_model: String(form.get("slippage_model")),
        slippage_assumption: { value: Number(form.get("slippage_value")) },
        fee_model: String(form.get("fee_model")),
        fee_assumption: { value: Number(form.get("fee_value")) },
        open_position_treatment: String(form.get("open_position_treatment")),
      });
      await refreshLists();
      setSelectedRunId(run.id);
      setNotice(
        run.status === "COMPLETED"
          ? "Backtest completed and persisted."
          : `Backtest finished with status ${run.status}.`,
      );
      setError(null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(null);
    }
  };

  const selectedStrategy = initialStrategies[0];
  const chartPoints = useMemo(() => {
    const rows = result?.equity ?? [];
    const stride = Math.max(Math.ceil(rows.length / 8), 1);
    return rows
      .filter((_, index) => index % stride === 0 || index === rows.length - 1)
      .map((point) => ({
        label: utcChartLabel(point.timestamp),
        value: point.equity,
      }));
  }, [result]);

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <StatusStrip
        items={[
          {
            label: "Ready datasets",
            value: readyDatasets.length,
            tone: readyDatasets.length ? "positive" : "inactive",
            meta: "Immutable local snapshots",
          },
          {
            label: "Providers",
            value: `${configuredProviders.length}/${initialProviders.length}`,
            tone: configuredProviders.length ? "positive" : "warning",
            meta: "Optional credentials remain isolated",
          },
          {
            label: "Runs",
            value: runs.length,
            tone: "neutral",
            meta: "Single-strategy simulations",
          },
          {
            label: "Selected pricing",
            value: result?.run.pricing_mode ?? "Not run",
            tone: result?.run.pricing_mode.includes("SYNTHETIC")
              ? "warning"
              : "neutral",
            meta: "Persisted execution assumption",
          },
          {
            label: "Replay boundary",
            value: "Close then next open",
            tone: "neutral",
            meta: "Prevents candle-close look-ahead",
          },
          {
            label: "Precision",
            value: "Candle simulation",
            tone: "warning",
            meta: "Not tick-level execution",
          },
        ]}
      />

      {error ? (
        <div className="rounded-[12px] border border-[color:var(--negative)] p-3 text-sm">
          <DataIndicator state="error" message={error} />
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-[12px] border border-[color:var(--positive)] p-3 text-sm">
          {notice}
        </div>
      ) : null}

      <section className="grid grid-cols-2 gap-3 max-[1100px]:grid-cols-1">
        <Panel
          title="Historical datasets"
          subtitle="External providers ingest only before replay. Completed snapshots are immutable."
          priority="primary"
        >
          <div className="grid grid-cols-2 gap-3 max-[720px]:grid-cols-1">
            <form className="flex flex-col gap-2" onSubmit={handleCsvImport}>
              <strong>CSV import</strong>
              <input className={inputClass} name="display_name" placeholder="Dataset name" required />
              <input className={inputClass} name="csv_file" type="file" accept=".csv,text/csv" required />
              <div className="grid grid-cols-3 gap-2">
                <select className={inputClass} name="asset_class" defaultValue="FOREX">
                  <option>FOREX</option>
                  <option>CRYPTO</option>
                  <option>INDICES</option>
                  <option>COMMODITIES</option>
                </select>
                <input className={inputClass} name="venue" defaultValue="USER_SUPPLIED" />
                <input className={inputClass} name="market_type" defaultValue="SPOT_FX" />
              </div>
              <button className={buttonClass} disabled={pending !== null}>
                {pending === "csv" ? "Importing..." : "Upload CSV snapshot"}
              </button>
              <p className="text-xs text-[color:var(--text-secondary)]">
                CSV timestamps must include UTC or an explicit offset. Mixed instruments,
                mixed timeframes, duplicate timestamps, and invalid OHLC are rejected.
              </p>
            </form>

            <form className="flex flex-col gap-2" onSubmit={handleProviderImport}>
              <strong>Provider import</strong>
              <select className={inputClass} name="provider_id" required>
                {initialProviders
                  .filter((provider) => provider.provider_id !== "CSV")
                  .map((provider) => (
                    <option key={provider.provider_id} value={provider.provider_id}>
                      {provider.provider_id} · {provider.configured ? "configured" : "optional credentials missing"}
                    </option>
                  ))}
              </select>
              <input className={inputClass} name="display_name" placeholder="Dataset name" required />
              <input className={inputClass} name="instruments" placeholder="Comma-separated internal instruments" required />
              <div className="grid grid-cols-3 gap-2">
                <input className={inputClass} name="timeframe" defaultValue="1m" />
                <input className={inputClass} name="asset_class" defaultValue="FOREX" />
                <input className={inputClass} name="market_type" defaultValue="SPOT_FX" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input className={inputClass} name="start_at" type="datetime-local" required />
                <input className={inputClass} name="end_at" type="datetime-local" required />
              </div>
              <button className={buttonClass} disabled={pending !== null}>
                {pending === "provider" ? "Importing..." : "Request provider import"}
              </button>
            </form>
          </div>

          <select
            className={inputClass}
            value={selectedDataset?.id ?? ""}
            onChange={(event) => void loadDataset(event.target.value)}
          >
            <option value="">Select dataset</option>
            {readyDatasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.display_name} · {dataset.provider} · {dataset.candle_count} candles
              </option>
            ))}
          </select>

          {selectedDataset ? (
            <div className="grid grid-cols-2 gap-2 text-sm max-[720px]:grid-cols-1">
              <div>
                <strong>{selectedDataset.display_name}</strong>
                <p>{selectedDataset.venue} · {selectedDataset.market_type} · {selectedDataset.asset_class}</p>
                <p>{selectedDataset.earliest_at} to {selectedDataset.latest_at}</p>
                <p>Components: {selectedDataset.price_components.join(", ")}</p>
              </div>
              <div>
                <p>Checksum: <code>{selectedDataset.checksum}</code></p>
                <p>Storage: {selectedDataset.storage_format} · immutable</p>
                <p>Gaps: {selectedDataset.detected_gaps.length} · warnings: {selectedDataset.warnings.length}</p>
                <p>
                  Venue truth: {selectedDataset.provider === "BINANCE"
                    ? "Binance spot prices are not IG crypto CFD prices."
                    : "Provider provenance is persisted with this snapshot."}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-[color:var(--text-secondary)]">
              No ready dataset selected.
            </p>
          )}
        </Panel>

        <Panel
          title="Run one strategy"
          subtitle="A single production strategy implementation is evaluated independently across the complete shortlist."
          priority="primary"
        >
          <form
            key={selectedDataset?.id ?? "no-dataset"}
            className="flex flex-col gap-2"
            onSubmit={handleBacktest}
          >
            <div className="grid grid-cols-2 gap-2">
              <input className={inputClass} name="name" placeholder="Optional run name" />
              <select className={inputClass} name="strategy_identifier" defaultValue={selectedStrategy?.name}>
                {initialStrategies.map((strategy) => (
                  <option key={strategy.name} value={strategy.name}>
                    {strategy.name}
                  </option>
                ))}
              </select>
            </div>
            <textarea className={inputClass} name="notes" placeholder="Optional notes" />
            <input className={inputClass} name="profile_name" defaultValue="default" />

            <div className="rounded-[10px] border border-[color:var(--border)] p-3">
              <strong>Instrument shortlist</strong>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {(selectedDataset?.partitions ?? []).map((partition) => (
                  <label key={partition.instrument} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" name="shortlist" value={partition.instrument} defaultChecked />
                    {partition.instrument} · {partition.candle_count} candles
                  </label>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <select className={inputClass} name="timeframe" defaultValue={selectedDataset?.base_timeframe ?? "1m"}>
                {[selectedDataset?.base_timeframe, "5m", "15m", "30m", "1h"]
                  .filter((item, index, rows): item is string => Boolean(item) && rows.indexOf(item) === index)
                  .map((timeframe) => <option key={timeframe}>{timeframe}</option>)}
              </select>
              <input className={inputClass} name="start_at" type="datetime-local" defaultValue={localInputValue(selectedDataset?.earliest_at)} required />
              <input className={inputClass} name="end_at" type="datetime-local" defaultValue={coverageEndValue(selectedDataset)} required />
            </div>

            <div className="grid grid-cols-4 gap-2 max-[720px]:grid-cols-2">
              <input className={inputClass} name="starting_capital" type="number" min="1" step="0.01" defaultValue="100000" />
              <select className={inputClass} name="position_sizing_mode" defaultValue="FIXED_UNITS">
                <option>FIXED_UNITS</option>
                <option>PERCENT_RISK</option>
              </select>
              <input className={inputClass} name="fixed_size" type="number" min="0.000001" step="any" defaultValue="1" />
              <input className={inputClass} name="max_open_positions" type="number" min="1" step="1" defaultValue="3" />
              <input className={inputClass} name="risk_per_trade_percent" type="number" min="0" step="0.01" defaultValue="0.5" />
              <input className={inputClass} name="fallback_stop_percent" type="number" min="0.0001" step="0.01" defaultValue="0.5" />
              <select className={inputClass} name="open_position_treatment" defaultValue="CLOSE_AT_END">
                <option>CLOSE_AT_END</option>
                <option>MARK_TO_MARKET</option>
              </select>
            </div>

            <div className="grid grid-cols-3 gap-2 max-[720px]:grid-cols-1">
              <label className="text-xs">
                Spread
                <div className="mt-1 flex gap-1">
                  <select className={inputClass} name="spread_model" defaultValue={selectedDataset?.price_components.includes("bid") && selectedDataset.price_components.includes("ask") ? "DATASET" : "FIXED_BPS"}>
                    <option>DATASET</option>
                    <option>FIXED_BPS</option>
                    <option>FIXED_PRICE</option>
                    <option>NONE</option>
                  </select>
                  <input className={inputClass} name="spread_value" type="number" min="0" step="any" defaultValue="1" />
                </div>
              </label>
              <label className="text-xs">
                Slippage
                <div className="mt-1 flex gap-1">
                  <select className={inputClass} name="slippage_model" defaultValue="NONE">
                    <option>NONE</option>
                    <option>FIXED_BPS</option>
                    <option>FIXED_PRICE</option>
                  </select>
                  <input className={inputClass} name="slippage_value" type="number" min="0" step="any" defaultValue="0" />
                </div>
              </label>
              <label className="text-xs">
                Fees
                <div className="mt-1 flex gap-1">
                  <select className={inputClass} name="fee_model" defaultValue="NONE">
                    <option>NONE</option>
                    <option>FIXED_PER_ORDER</option>
                    <option>PER_UNIT</option>
                    <option>BPS_NOTIONAL</option>
                  </select>
                  <input className={inputClass} name="fee_value" type="number" min="0" step="any" defaultValue="0" />
                </div>
              </label>
            </div>

            <button className={buttonClass} disabled={pending !== null || !selectedDataset}>
              {pending === "backtest" ? "Running bounded simulation..." : "Start manual backtest"}
            </button>
                <p className="text-xs text-[color:var(--text-secondary)]">
                  Synchronous MVP runs are bounded by the backend candle limit. Historical
                  replay never calls IG, OANDA, or Binance and never writes live trading tables.
                  Midpoint or trade-price datasets require an explicit synthetic spread
                  assumption.
                </p>
          </form>
        </Panel>
      </section>

      <Panel title="Persisted runs" subtitle="Completed and failed simulations remain auditable.">
        <select className={inputClass} value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
          <option value="">Select run</option>
          {runs.map((run) => (
            <option key={run.id} value={run.id}>
              {run.name || run.strategy_identifier} · {run.status} · {utcTimestampLabel(run.created_at)}
            </option>
          ))}
        </select>
        <CompactTable
          rows={runs}
          emptyLabel="No backtest runs have been created."
          columns={[
            { key: "run", header: "Run", render: (run) => run.name || run.id.slice(0, 8) },
            { key: "strategy", header: "Strategy", render: (run) => `${run.strategy_identifier} v${run.strategy_version}` },
            { key: "status", header: "Status", render: (run) => <StatusPill label={run.status} tone={run.status === "COMPLETED" ? "positive" : run.status === "FAILED" ? "negative" : "warning"} /> },
            { key: "dataset", header: "Dataset checksum", render: (run) => <code>{run.dataset_checksum.slice(0, 16)}</code> },
            { key: "pricing", header: "Pricing", render: (run) => run.pricing_mode },
          ]}
        />
      </Panel>

      {pending === "result" ? <DataIndicator state="loading" message="Loading persisted result..." /> : null}
      {result ? (
        <>
          <StatusStrip
            items={[
              { label: "Ending capital", value: money(result.metrics.run.ending_capital), tone: "neutral" },
              { label: "Net P&L", value: money(result.metrics.run.net_pnl), tone: (numberValue(result.metrics.run.net_pnl) ?? 0) >= 0 ? "positive" : "negative" },
              { label: "Return", value: numberValue(result.metrics.run.percentage_return) == null ? "Undefined" : `${numberValue(result.metrics.run.percentage_return)?.toFixed(2)}%`, tone: "neutral" },
              { label: "Trades", value: numberValue(result.metrics.run.total_trades) ?? 0, tone: "neutral" },
              { label: "Max drawdown", value: money(result.metrics.run.maximum_drawdown), tone: "warning" },
              { label: "Warnings", value: result.warnings.length, tone: result.warnings.length ? "warning" : "positive" },
            ]}
          />

          <section className="grid grid-cols-2 gap-3 max-[1100px]:grid-cols-1">
            <LineChart
              title="Equity curve"
              subtitle="Persisted simulated equity; candle-resolution marks only."
              points={chartPoints}
              latestValue={money(result.metrics.run.ending_capital)}
              delta={numberValue(result.metrics.run.percentage_return) == null ? undefined : `${numberValue(result.metrics.run.percentage_return)?.toFixed(2)}%`}
              tone={(numberValue(result.metrics.run.absolute_return) ?? 0) >= 0 ? "positive" : "negative"}
            />
            <LineChart
              title="Drawdown"
              subtitle="Peak-to-trough drawdown from persisted equity points."
              points={result.equity
                .filter((_, index) => index % Math.max(Math.ceil(result.equity.length / 8), 1) === 0 || index === result.equity.length - 1)
                .map((point) => ({ label: utcChartLabel(point.timestamp), value: point.drawdown }))}
              latestValue={money(result.metrics.run.maximum_drawdown)}
              tone="negative"
            />
          </section>

          <section className="grid grid-cols-2 gap-3 max-[1100px]:grid-cols-1">
            <Panel title="Trades" subtitle="Deterministic simulated fills, never broker executions.">
              <CompactTable
                rows={result.trades}
                emptyLabel="The strategy produced no completed trades."
                columns={[
                  { key: "instrument", header: "Instrument", render: (trade) => trade.instrument },
                  { key: "direction", header: "Side", render: (trade) => trade.direction },
                  { key: "open", header: "Open", render: (trade) => trade.open_price.toFixed(5) },
                  { key: "close", header: "Close", render: (trade) => trade.close_price.toFixed(5) },
                  { key: "pnl", header: "Net P&L", render: (trade) => money(trade.net_pnl) },
                  { key: "reason", header: "Exit", render: (trade) => trade.exit_reason },
                ]}
              />
            </Panel>

            <Panel title="Per instrument" subtitle="The selected strategy is isolated per shortlist instrument.">
              <CompactTable
                rows={result.instruments}
                emptyLabel="No instrument breakdown is available."
                columns={[
                  { key: "instrument", header: "Instrument", render: (item) => item.instrument },
                  { key: "candles", header: "Candles", render: (item) => item.candle_count },
                  { key: "trades", header: "Trades", render: (item) => item.metrics.total_trades ?? 0 },
                  { key: "pnl", header: "Net P&L", render: (item) => money(item.metrics.net_pnl) },
                ]}
              />
            </Panel>
          </section>

          <section className="grid grid-cols-2 gap-3 max-[1100px]:grid-cols-1">
            <Panel title="Assumptions and provenance" tone={result.run.pricing_mode.includes("SYNTHETIC") ? "warning" : "neutral"}>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <p>Dataset: <code>{result.run.dataset_id}</code></p>
                <p>Checksum: <code>{result.run.dataset_checksum}</code></p>
                <p>Pricing: {result.run.pricing_mode}</p>
                <p>Boundary: {result.run.evaluation_boundary}</p>
                <p>Spread: {result.run.spread_model} · {JSON.stringify(result.run.spread_assumption)}</p>
                <p>Slippage: {result.run.slippage_model} · {JSON.stringify(result.run.slippage_assumption)}</p>
                <p>Fees: {result.run.fee_model} · {JSON.stringify(result.run.fee_assumption)}</p>
                <p>End treatment: {result.run.open_position_treatment}</p>
              </div>
              <p className="text-sm text-[color:var(--text-secondary)]">
                One-minute OHLC cannot establish tick order or exact sub-minute fills.
                Same-candle stop/target ambiguity is resolved against the strategy.
              </p>
            </Panel>

            <Panel title="Warnings and failure truth" tone={result.run.status === "FAILED" ? "negative" : result.warnings.length ? "warning" : "positive"}>
              {result.run.failure_reason ? (
                <p className="text-sm">{result.run.failure_reason}</p>
              ) : null}
              {result.warnings.length ? (
                <ul className="flex flex-col gap-2 text-sm">
                  {result.warnings.map((warning) => (
                    <li key={warning.id}>
                      <strong>{warning.code}</strong> · {warning.message}
                      {warning.instrument ? ` · ${warning.instrument}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm">No run-specific warnings were persisted.</p>
              )}
            </Panel>
          </section>
        </>
      ) : null}
    </main>
  );
}
