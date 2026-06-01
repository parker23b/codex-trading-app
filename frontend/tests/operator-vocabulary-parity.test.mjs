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

test("AUDIT-005 backend and frontend keep governance approval state parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "models", "strategy_governance.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractPythonEnumValues(
    backendSource,
    /class GovernanceApprovalState[\s\S]*?class StrategyFamilyGovernance/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type GovernanceApprovalState =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("AUDIT-005 backend and frontend keep deployment state parity", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "models", "strategy_deployment.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractPythonEnumValues(
    backendSource,
    /class StrategyDeploymentState[\s\S]*?class StrategyDeployment/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type StrategyDeploymentState =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("AUDIT-005 frontend alignment and open-risk vocabularies match current backend read-model states", () => {
  const controlPlaneSource = readFileSync(
    path.join(repoRoot, "backend", "app", "services", "control_plane_service.py"),
    "utf8",
  );
  const operationalStateSource = readFileSync(
    path.join(repoRoot, "backend", "app", "services", "operational_state_service.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendAlignmentValues = new Set(
    [...controlPlaneSource.matchAll(/"status": "(ALIGNED|MISMATCH|NO_DEPLOYMENT)"/g)].map((match) => match[1]),
  );
  const frontendAlignmentValues = new Set(
    extractQuotedValues(frontendSource, /export type AlignmentStatus =[\s\S]*?;/s),
  );

  assert.deepEqual(frontendAlignmentValues, backendAlignmentValues);

  const backendOpenRiskValues = new Set(extractPythonEnumValues(
    operationalStateSource,
    /class OpenRiskManagementState[\s\S]*?class OperationalStateSnapshot/s,
  ));
  const frontendOpenRiskValues = new Set(
    extractQuotedValues(frontendSource, /export type OpenRiskManagementState =[\s\S]*?;/s),
  );

  assert.deepEqual(
    frontendOpenRiskValues,
    new Set([...backendOpenRiskValues, "UNAVAILABLE", "UNKNOWN"]),
  );
});

test("AUDIT-005 frontend runtime and control vocabularies match documented backend states", () => {
  const stateMachineSource = readFileSync(
    path.join(repoRoot, "docs", "spec", "07-state-machines.md"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendRuntimeValues = new Set(
    [...stateMachineSource.matchAll(/- `(NORMAL|EXITS_ONLY|STOPPED)`/g)].map((match) => match[1]),
  );
  const frontendRuntimeValues = new Set(
    extractQuotedValues(frontendSource, /export type RuntimeMode =[\s\S]*?;/s),
  );
  assert.deepEqual(frontendRuntimeValues, backendRuntimeValues);

  const frontendControlValues = new Set(
    extractQuotedValues(frontendSource, /export type ControlMode =[\s\S]*?;/s),
  );
  assert.deepEqual(frontendControlValues, new Set(["MANUAL", "AUTO"]));
});

test("AUDIT-005 browser-covered control-plane and strategy surfaces use shared operator vocabulary helpers", () => {
  const strategySource = readFileSync(
    path.join(frontendRoot, "components", "strategy", "strategy-live.tsx"),
    "utf8",
  );
  const controlPlaneSource = readFileSync(
    path.join(frontendRoot, "components", "control-plane", "control-plane-live.tsx"),
    "utf8",
  );

  assert.match(strategySource, /controlModeMeta\(row\.control_mode\)/);
  assert.match(strategySource, /runtimeModeMeta\(row\.runtime_mode\)/);
  assert.match(controlPlaneSource, /alignmentStatusMeta\(family\.alignment\.status\)/);
  assert.match(controlPlaneSource, /governanceApprovalStateMeta\(selectedFamily\.governance\.approval_state\)/);
  assert.match(controlPlaneSource, /deploymentStateMeta\(selectedFamily\.deployment\?\.state/);
  assert.match(controlPlaneSource, /openRiskManagementStateMeta\(familyOpenRiskState\(family\)\)/);
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
  assert.deepEqual(vocabulary.controlModeMeta("BROKER_MAGIC"), {
    label: "Control mode unknown",
    tone: "negative",
    detail: "Backend did not provide a supported control mode; do not assume manual or autonomous ownership.",
  });
  assert.deepEqual(vocabulary.runtimeModeMeta("BROKER_MAGIC"), {
    label: "Runtime mode unknown",
    tone: "negative",
    detail: "Backend did not provide a supported runtime mode; do not assume normal, exits-only, or stopped state.",
  });
  assert.deepEqual(vocabulary.governanceApprovalStateMeta("BROKER_MAGIC"), {
    label: "Governance unknown",
    tone: "negative",
    detail: "Backend returned an unsupported governance state; do not treat it as approved.",
  });
  assert.deepEqual(vocabulary.deploymentStateMeta("BROKER_MAGIC"), {
    label: "Deployment unknown",
    tone: "negative",
    detail: "Backend returned an unsupported deployment state; do not treat it as healthy or active.",
  });
  assert.deepEqual(vocabulary.alignmentStatusMeta("BROKER_MAGIC"), {
    label: "Alignment unknown",
    tone: "negative",
    detail: "Backend returned an unsupported alignment state; do not treat it as aligned.",
  });
  assert.deepEqual(vocabulary.openRiskManagementStateMeta("BROKER_MAGIC"), {
    label: "Open-risk state unknown",
    tone: "negative",
    detail: "Open-risk management truth is unknown or unsupported and must not be treated as safe.",
  });
});
