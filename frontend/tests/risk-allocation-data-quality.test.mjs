import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function compileRiskAllocationHelpers() {
  const outDir = mkdtempSync(path.join(tmpdir(), "risk-allocation-"));
  execFileSync(
    path.join(frontendRoot, "node_modules", ".bin", "tsc"),
    [
      "lib/risk-allocation.ts",
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
  const compiled = require(path.join(outDir, "lib", "risk-allocation.js"));
  return { outDir, buildRiskLoadQuality: compiled.buildRiskLoadQuality };
}

test("AUDIT-RISK-003 risk load failures render as unavailable instead of zero-risk truth", () => {
  const { outDir, buildRiskLoadQuality } = compileRiskAllocationHelpers();
  try {
    const quality = buildRiskLoadQuality({
      exposure: "Backend unavailable",
      alerts: "Request timed out",
      drift: null,
      cycles: null,
      intents: null,
      selectedCycle: null,
    });

    assert.equal(quality.degraded, true);
    assert.equal(quality.sectionUnavailable("exposure"), true);
    assert.equal(quality.sectionUnavailable("alerts"), true);
    assert.equal(quality.sectionUnavailable("drift"), false);
    assert.match(quality.headline, /risk data unavailable/i);
    assert.match(quality.detail, /exposure/i);
    assert.match(quality.detail, /alerts/i);
    assert.doesNotMatch(quality.headline, /nominal|exact|zero/i);
  } finally {
    rmSync(outDir, { recursive: true, force: true });
  }
});

test("AUDIT-RISK-003 risk page passes load-error metadata to the risk console", () => {
  const riskPageSource = readFileSync(path.join(frontendRoot, "app", "risk", "page.tsx"), "utf8");

  assert.match(riskPageSource, /initialLoadErrors=\{\{/);
  assert.match(riskPageSource, /exposure:\s*exposure\.error/);
  assert.match(riskPageSource, /alerts:\s*alerts\.error/);
  assert.match(riskPageSource, /drift:\s*drift\.error/);
  assert.match(riskPageSource, /cycles:\s*cycles\.error/);
  assert.match(riskPageSource, /intents:\s*intents\.error/);
});
