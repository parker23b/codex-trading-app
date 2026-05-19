import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const frontendRoot = path.resolve(import.meta.dirname, "..");

test("AUDIT-UI-004 allocation alert mutation failures keep backend error detail visible", () => {
  const source = readFileSync(path.join(frontendRoot, "components", "risk", "risk-allocation-live.tsx"), "utf8");

  assert.match(source, /alertMutationState/);
  assert.match(source, /setAlertMutationState/);
  assert.match(source, /catch\s*\(\s*error\s*\)/);
  assert.match(source, /mutationErrorMessage/);
  assert.match(source, /mutation\?\.error/);
  assert.match(source, /RiskAlertCard/);
  assert.match(source, /Mutation failed/);
  assert.doesNotMatch(source, /startTransition\s*\(\s*async\s*\(\s*\)\s*=>/);
});

test("AUDIT-UI-004 allocation alert mutation success refreshes backend truth before success copy", () => {
  const source = readFileSync(path.join(frontendRoot, "components", "risk", "risk-allocation-live.tsx"), "utf8");

  assert.match(source, /await\s+getAllocationAlerts\(\{\s*limit:\s*60,\s*refresh:\s*true\s*\}\)/);
  assert.match(source, /Mutation confirmed/);
  assert.match(source, /setAlerts\(nextAlerts\)/);
});

test("AUDIT-UI-004 allocation alert refresh failures do not render clean success", () => {
  const source = readFileSync(path.join(frontendRoot, "components", "risk", "risk-allocation-live.tsx"), "utf8");

  assert.match(source, /refreshError/);
  assert.match(source, /Refresh failed/);
  assert.match(source, /Mutation submitted/);
  assert.match(source, /backend alert truth could not be refreshed/);
  assert.doesNotMatch(source, /success:\s*"Mutation confirmed[^"]*"\s*,\s*refreshError:\s*`Refresh failed/s);
});
