import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

test("API-003 risk allocation chart route uses a backend-owned response model", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "charts.py"),
    "utf8",
  );

  for (const className of [
    "RiskAllocationChartResponse",
    "RiskAllocationChartSummaryResponse",
    "RiskAllocationChartBucketResponse",
    "RiskAllocationTruthCountResponse",
  ]) {
    assert.match(backendSource, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
});

test("API-004 frontend API client exposes a typed risk allocation chart loader", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "api.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export async function getRiskAllocationChart\(\): Promise<RiskAllocationChart>/,
  );
  assert.match(
    frontendSource,
    /request<RiskAllocationChart>\("\/charts\/risk-allocation"\)/,
  );
});

test("RISK-006 and RISK-017 frontend chart types keep unavailable and provisional truth explicit", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type RiskAllocationChartDataStatus =[\s\S]*"READY"[\s\S]*"PARTIAL"[\s\S]*"DEGRADED"[\s\S]*"UNAVAILABLE"/s,
  );
  assert.match(
    frontendSource,
    /export type RiskAllocationChartSummary = \{[\s\S]*reserved_risk_percent\?: number \| null;[\s\S]*live_risk_percent\?: number \| null;[\s\S]*provisional_live_risk_percent\?: number \| null;[\s\S]*has_provisional_risk: boolean;[\s\S]*has_simulated_risk: boolean;[\s\S]*has_unknown_risk: boolean;[\s\S]*has_degraded_risk: boolean;/s,
  );
  assert.match(
    frontendSource,
    /export type RiskAllocationChartBucket = \{[\s\S]*data_status: RiskAllocationChartDataStatus \| string;[\s\S]*risk_truth_confidence_mix: RiskAllocationChartTruthCount\[];[\s\S]*reasons: string\[];/s,
  );
});
