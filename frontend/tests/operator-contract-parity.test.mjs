import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

test("API-003 operator summary route family uses backend-owned response models", () => {
  const controlPlaneContracts = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "control_plane.py"),
    "utf8",
  );
  const dashboardContracts = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "dashboard.py"),
    "utf8",
  );
  const strategyContracts = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "strategies.py"),
    "utf8",
  );

  for (const className of [
    "ControlPlaneSummaryResponse",
    "ControlPlaneFamilyResponse",
    "GovernanceMutationResponse",
    "ControlPlaneReconcileResponse",
    "StrategyMutationStatusResponse",
  ]) {
    assert.match(controlPlaneContracts, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
  for (const className of ["DashboardSnapshotResponse"]) {
    assert.match(dashboardContracts, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
  for (const className of ["StrategySummaryResponse"]) {
    assert.match(strategyContracts, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
});

test("API-004 frontend API client uses typed operator summary and strategy mutation responses", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "api.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export async function updateStrategyGovernance\([\s\S]*\): Promise<StrategyGovernanceMutationResponse>/,
  );
  assert.match(
    frontendSource,
    /export async function startStrategy\(strategyName: string, instrument: string\): Promise<StrategyMutationStatus>/,
  );
  assert.match(
    frontendSource,
    /export async function stopStrategy\(params: \{ instrument\?: string; strategyName\?: string \}\): Promise<StrategyMutationStatus>/,
  );
  assert.match(
    frontendSource,
    /export async function getDashboardSnapshot\(\): Promise<DashboardSnapshot>/,
  );
  assert.match(
    frontendSource,
    /export async function getStrategies\(\): Promise<StrategyDefinition\[]>/,
  );
});

test("ARCH-009 operator summary frontend types keep governance, deployment, runtime, and open-risk fields explicit", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type ControlPlaneFamily = \{[\s\S]*governance: \{[\s\S]*approval_state: string;[\s\S]*max_concurrent_deployments\?: number \| null;[\s\S]*notes\?: string \| null;[\s\S]*\};[\s\S]*deployment: \{[\s\S]*open_risk_management_state\?: string \| null;[\s\S]*open_risk_management_reason\?: string \| null;[\s\S]*\} \| null;[\s\S]*runtime: \{[\s\S]*control_mode\?: string \| null;[\s\S]*runtime_mode\?: "NORMAL" \| "EXITS_ONLY" \| "STOPPED" \| string \| null;[\s\S]*recovery_state\?: string \| null;/s,
  );
  assert.match(
    frontendSource,
    /export type StrategyRuntime = \{[\s\S]*recovery_state\?: string \| null;[\s\S]*runtime_mode\?: "NORMAL" \| "EXITS_ONLY" \| "STOPPED" \| string \| null;[\s\S]*control_mode\?: "MANUAL" \| "AUTO" \| string \| null;/s,
  );
  assert.match(
    frontendSource,
    /export type StrategyDefinition = \{[\s\S]*governance_approval_state\?: string;[\s\S]*deployment_state\?: string;[\s\S]*persisted_runtimes\?: Array<\{[\s\S]*runtime_mode\?: "NORMAL" \| "EXITS_ONLY" \| "STOPPED" \| string \| null;[\s\S]*parameters: Record<string, number>;/s,
  );
});

test("UI-001 and UI-007 control-plane UI keeps missing open-risk truth explicitly unavailable", () => {
  const controlPlaneSource = readFileSync(
    path.join(frontendRoot, "components", "control-plane", "control-plane-live.tsx"),
    "utf8",
  );

  assert.match(
    controlPlaneSource,
    /family\.deployment\?\.open_risk_management_state \?\? "UNAVAILABLE"/,
  );
  assert.match(
    controlPlaneSource,
    /Open-risk state unavailable; do not treat this family as having no open risk\./,
  );
});
