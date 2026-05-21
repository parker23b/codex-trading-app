import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");
let operatorVocabularyModuleCache = null;

function extractQuotedValues(source, blockPattern) {
  const block = source.match(blockPattern)?.[0] ?? "";
  return [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

function extractPythonEnumValues(source, blockPattern) {
  const block = source.match(blockPattern)?.[0] ?? "";
  return [...block.matchAll(/\b[A-Z_]+\s*=\s*"([^"]+)"/g)].map((match) => match[1]);
}

function compileOperatorVocabularyModule() {
  if (operatorVocabularyModuleCache) {
    return operatorVocabularyModuleCache;
  }

  const outDir = mkdtempSync(path.join(tmpdir(), "operator-vocabulary-"));
  execFileSync(
    path.join(frontendRoot, "node_modules", ".bin", "tsc"),
    [
      "lib/operator-vocabulary.ts",
      "lib/types.ts",
      "--target",
      "ES2021",
      "--lib",
      "ES2021",
      "--module",
      "CommonJS",
      "--moduleResolution",
      "node",
      "--rootDir",
      frontendRoot,
      "--outDir",
      outDir,
      "--skipLibCheck",
      "--esModuleInterop",
    ],
    { cwd: frontendRoot, stdio: "pipe" },
  );
  const require = createRequire(import.meta.url);
  operatorVocabularyModuleCache = {
    outDir,
    vocabulary: require(path.join(outDir, "lib", "operator-vocabulary.js")),
  };
  return operatorVocabularyModuleCache;
}

after(() => {
  if (!operatorVocabularyModuleCache) {
    return;
  }
  rmSync(operatorVocabularyModuleCache.outDir, { recursive: true, force: true });
  operatorVocabularyModuleCache = null;
});

test("AUDIT-005 backend and frontend keep broker execution source parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "core", "broker.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractQuotedValues(
    backendSource,
    /class BrokerExecutionSource[\s\S]*?class BrokerSizingPrecision/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type BrokerExecutionSource =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("AUDIT-005 backend and frontend keep broker sync status parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "models", "trade.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractQuotedValues(
    backendSource,
    /class BrokerSyncStatus[\s\S]*?class ExecutionStatus/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type BrokerSyncStatus =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("AUDIT-005 backend and frontend keep execution status parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "models", "trade.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractPythonEnumValues(
    backendSource,
    /class ExecutionStatus[\s\S]*?class TradeIntentState/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type ExecutionStatus =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("AUDIT-005 backend and frontend keep trade intent state parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "models", "trade.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractQuotedValues(
    backendSource,
    /class TradeIntentState[\s\S]*?ACTIVE_INSTRUMENT_OWNERSHIP_STATES/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type TradeIntentState =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("UI-005 unknown backend provenance values render unknown or degraded instead of healthy truth", () => {
  const { vocabulary } = compileOperatorVocabularyModule();

  assert.deepEqual(vocabulary.closeExecutionSourceMeta("BROKER_MAGIC"), {
    label: "Close source unknown",
    tone: "warning",
    detail: "Backend did not provide broker-confirmed or simulated close provenance.",
  });
  assert.deepEqual(vocabulary.brokerSyncStatusMeta("BROKER_MAGIC"), {
    label: "Sync unknown",
    tone: "negative",
    detail: "Broker sync state is unknown and must not be treated as confirmed.",
  });
  assert.deepEqual(vocabulary.executionStatusMeta("BROKER_MAGIC"), {
    label: "Unknown execution state",
    tone: "negative",
    detail: "Backend returned an unsupported execution state; do not treat it as healthy or final.",
  });
  assert.deepEqual(vocabulary.tradeIntentStateMeta("BROKER_MAGIC"), {
    label: "Broker Magic",
    tone: "negative",
    detail: "Backend returned an unsupported intent state; do not treat it as healthy or exact.",
  });
});
