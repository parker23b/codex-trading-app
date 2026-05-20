import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

function extractQuotedValues(source, blockPattern) {
  const block = source.match(blockPattern)?.[0] ?? "";
  return [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

test("allocation contract parity keeps frontend risk truth confidence aligned with backend vocabulary", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "core", "risk_truth.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  const backendValues = extractQuotedValues(
    backendSource,
    /class RiskTruthConfidence[\s\S]*?RISK_TRUTH_CONFIDENCE_VALUES/s,
  );
  const frontendValues = extractQuotedValues(
    frontendSource,
    /export type RiskTruthConfidence =[\s\S]*?;/s,
  );

  assert.deepEqual(new Set(frontendValues), new Set(backendValues));
});

test("allocation alert parity uses backend escalation vocabulary instead of numeric levels", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type AllocationAlertEscalationLevel = "none" \| "warning" \| "critical";/,
  );
  assert.match(frontendSource, /escalation_level: AllocationAlertEscalationLevel;/);
  assert.doesNotMatch(frontendSource, /escalation_level: number;/);
});
