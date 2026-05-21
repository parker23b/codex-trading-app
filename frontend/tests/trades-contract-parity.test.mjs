import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

test("API-003 trades and positions route family uses backend-owned response models", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "trading.py"),
    "utf8",
  );

  for (const className of ["TradeResponse", "OpenPositionResponse"]) {
    assert.match(backendSource, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
});

test("API-004 frontend API client uses typed trade and open-position responses", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "api.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export async function getTrades\(\): Promise<Trade\[]>/,
  );
  assert.match(
    frontendSource,
    /export async function getOpenPositions\(\): Promise<Position\[]>/,
  );
  assert.match(frontendSource, /request<Trade\[]>\("\/trades"\)/);
  assert.match(frontendSource, /request<Position\[]>\("\/trades\/positions"\)/);
});

test("ARCH-009 and API-004 frontend trade and position types keep provenance fields explicit", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type Trade = \{[\s\S]*entry_risk_amount\?: number \| null;[\s\S]*risk_truth_confidence\?: RiskTruthConfidence \| string \| null;[\s\S]*close_execution_source\?: BrokerExecutionSource \| string \| null;[\s\S]*outcome\?: string \| null;/s,
  );
  assert.match(
    frontendSource,
    /export type Position = \{[\s\S]*risk_truth_confidence\?: RiskTruthConfidence \| string \| null;[\s\S]*broker_sync_status\?: BrokerSyncStatus \| string \| null;[\s\S]*close_execution_source\?: BrokerExecutionSource \| string \| null;[\s\S]*time_in_trade_seconds\?: number;/s,
  );
  assert.match(
    frontendSource,
    /export type BrokerSyncStatus =[\s\S]*"CONFIRMED"[\s\S]*"PENDING"[\s\S]*"MISSING_AT_BROKER"[\s\S]*"UNKNOWN"[\s\S]*"UNAVAILABLE"/s,
  );
});
