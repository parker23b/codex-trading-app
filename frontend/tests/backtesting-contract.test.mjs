import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("backtesting client keeps typed dataset and result APIs explicit", () => {
  const api = readFileSync(path.join(frontendRoot, "lib", "api.ts"), "utf8");
  const types = readFileSync(path.join(frontendRoot, "lib", "types.ts"), "utf8");

  for (const functionName of [
    "getHistoricalProviders",
    "getHistoricalDatasets",
    "importHistoricalCsv",
    "importHistoricalProviderData",
    "createBacktest",
    "getBacktestMetrics",
    "getBacktestTrades",
    "getBacktestEquity",
    "getBacktestWarnings",
    "getBacktestInstruments",
  ]) {
    assert.match(api, new RegExp(`export async function ${functionName}`));
  }
  for (const typeName of [
    "HistoricalDataset",
    "BacktestRun",
    "BacktestTrade",
    "BacktestEquityPoint",
    "BacktestWarning",
    "BacktestMetrics",
  ]) {
    assert.match(types, new RegExp(`export type ${typeName} =`));
  }
});

test("backtesting UI renders empty, failed, warning, provenance, and limitation truth", () => {
  const source = readFileSync(
    path.join(frontendRoot, "components", "backtests", "backtests-live.tsx"),
    "utf8",
  );

  assert.match(source, /No backtest runs have been created\./);
  assert.match(source, /Warnings and failure truth/);
  assert.match(source, /result\.run\.failure_reason/);
  assert.match(source, /Dataset checksum/);
  assert.match(source, /synthetic spread/i);
  assert.match(source, /not tick-level execution/i);
  assert.match(source, /Same-candle stop\/target ambiguity uses the less favorable stop/);
  assert.match(source, /Binance spot prices are not IG crypto CFD prices/);
  assert.match(source, /Run did not produce analytics/);
  assert.match(source, /no result metrics are inferred/);
  for (const label of [
    "Ending equity",
    "Realised P&L",
    "Unrealised P&L",
    "Total P&L",
    "Closed-trade win rate",
    "Open positions at end",
  ]) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /Result checksum/);
  assert.match(source, /Exposure: wall-clock union across open intervals/);
  assert.doesNotMatch(source, /label: "Ending capital"/);
  assert.doesNotMatch(source, /label: "Net P&L"/);
  assert.match(source, /selectedProvider\.quota_warnings/);
  assert.match(source, /Detected gaps/);
  assert.match(source, /Dataset warnings/);
  assert.match(source, /setResult\(null\);\s+setPending\("result"\)/);
  assert.match(source, /utcTimestampLabel/);
  assert.match(source, /Backend timestamp must include an explicit UTC offset/);
  assert.match(source, /function localFormValueToUtcIso/);
  assert.match(source, /localFormValueToUtcIso\(String\(form\.get\("start_at"\)\)\)/);
  assert.match(source, /dataset\.availability === "AVAILABLE"/);
  assert.match(source, /dataset\.selectable/);
  assert.match(
    source,
    /name="fallback_stop_percent" type="number" min="0\.0001" step="any"/,
  );
  assert.doesNotMatch(source, /`\$\{value\}Z`/);
  assert.doesNotMatch(source, /utcDate\(String\(form\.get\("(?:start_at|end_at)"\)\)\)/);
  assert.doesNotMatch(source, /toLocale(?:DateString|String)/);
});
