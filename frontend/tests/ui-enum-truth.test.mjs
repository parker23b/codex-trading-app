import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
let riskAllocationModuleCache = null;

function compileRiskAllocationModule() {
  if (riskAllocationModuleCache) {
    return riskAllocationModuleCache;
  }

  const outDir = mkdtempSync(path.join(tmpdir(), "ui-enum-truth-"));
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
  riskAllocationModuleCache = {
    outDir,
    risk: require(path.join(outDir, "lib", "risk-allocation.js")),
  };
  return riskAllocationModuleCache;
}

after(() => {
  if (!riskAllocationModuleCache) {
    return;
  }
  rmSync(riskAllocationModuleCache.outDir, { recursive: true, force: true });
  riskAllocationModuleCache = null;
});

function baseRiskInputs(intents) {
  return {
    exposure: {
      totals: {
        live_risk_percent: 0,
        provisional_live_risk_percent: 0,
        reserved_risk_percent: 0,
        reserved_intent_count: 0,
        remaining_portfolio_risk_percent: 5,
      },
      hotspots: [],
      currency_directional: [],
    },
    alerts: [],
    drift: {
      material_drift_count: 0,
      drift_warning_percent: 10,
      drift_critical_percent: 25,
    },
    cycles: [],
    intents,
  };
}

test("AUDIT-UI-002 pending execution statuses render as pending, not positive activity", () => {
  const source = readFileSync(path.join(frontendRoot, "lib", "live-system-view.ts"), "utf8");

  assert.match(source, /case "SUBMISSION_PENDING":[\s\S]*pending broker submission/i);
  assert.match(source, /case "ORDER_SUBMITTED":[\s\S]*case "ORDER_ACKNOWLEDGED":[\s\S]*return "warning"/);
  assert.doesNotMatch(source, /return "positive";\s*\}\s*function executionMessage/);
});

test("AUDIT-UI-002 unknown and simulated risk confidence render degraded, not estimated", () => {
  const { risk } = compileRiskAllocationModule();
  assert.deepEqual(risk.truthConfidenceMeta("UNKNOWN"), {
    label: "Unknown",
    tone: "negative",
    detail: "Risk truth confidence is explicitly unknown or unavailable.",
  });
  assert.deepEqual(risk.truthConfidenceMeta("SIMULATED_LOCAL_FILL"), {
    label: "Simulated",
    tone: "warning",
    detail: "Risk comes from a local simulated fill and is not broker-confirmed truth.",
  });

  const summary = risk.buildRiskConsoleSummary(baseRiskInputs([
    {
      id: 1,
      risk_truth_confidence: "UNKNOWN",
      position: { is_open: true, risk_truth_confidence: "UNKNOWN" },
    },
    {
      id: 2,
      risk_truth_confidence: "SIMULATED_LOCAL_FILL",
      position: { is_open: true, risk_truth_confidence: "SIMULATED_LOCAL_FILL" },
    },
    {
      id: 3,
      risk_truth_confidence: null,
      position: { is_open: true, risk_truth_confidence: null },
    },
  ]));
  const riskTruthMetric = summary.metrics.find((item) => item.label === "Risk Truth");

  assert.deepEqual(summary.truthMix, {
    exact: 0,
    provisional: 0,
    estimated: 0,
    degraded: 3,
  });
  assert.equal(riskTruthMetric.value, "3 degraded");
  assert.equal(riskTruthMetric.tone, "negative");
  assert.doesNotMatch(riskTruthMetric.value, /no live book/i);
});
