import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function compileNotificationHelpers() {
  const outDir = mkdtempSync(path.join(tmpdir(), "execution-notifications-"));
  execFileSync(
    path.join(frontendRoot, "node_modules", ".bin", "tsc"),
    [
      "lib/execution-notifications.ts",
      "lib/format.ts",
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
  const compiled = require(path.join(outDir, "lib", "execution-notifications.js"));
  return { outDir, buildExecutionDetail: compiled.buildExecutionDetail };
}

function executionWithDriftFlags({ material, critical }) {
  return {
    id: 8,
    trade_intent_id: 4,
    strategy_name: "smoke_test_hold",
    instrument: "CS.D.EURUSD.MINI.IP",
    phase: "ENTRY",
    status: "POSITION_OPENED",
    client_request_id: "ent-fill-drift-route-1",
    broker_reference: "entry-fill-drift-route-1",
    signal_time: "2026-04-07T12:00:00Z",
    last_transition_at: "2026-04-07T12:00:01Z",
    requested_size: 0.2,
    filled_size: 0.2,
    requested_price: 100,
    average_fill_price: 120,
    intended_risk_amount: 20,
    submitted_risk_amount: 20,
    fill_derived_risk_amount: 30,
    risk_truth_confidence: "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
    risk_reconciliation: {
      flags: {
        material_execution_drift: material,
        critical_execution_drift: critical,
      },
    },
    material_execution_drift: material,
    critical_execution_drift: critical,
    reason: "Position opened",
    error_code: null,
    error_message: null,
    requires_manual_review: false,
    details: {},
    created_at: "2026-04-07T12:00:00Z",
    updated_at: "2026-04-07T12:00:01Z",
  };
}

test("AUDIT-RISK-002 execution notification displays material submitted/fill risk drift", () => {
  const { outDir, buildExecutionDetail } = compileNotificationHelpers();
  try {
    const detail = buildExecutionDetail(
      executionWithDriftFlags({ material: true, critical: false }),
    );

    assert.match(detail, /material risk drift detected/);
    assert.doesNotMatch(detail, /critical risk drift detected/);
  } finally {
    rmSync(outDir, { recursive: true, force: true });
  }
});

test("AUDIT-RISK-002 execution notification displays critical submitted/fill risk drift", () => {
  const { outDir, buildExecutionDetail } = compileNotificationHelpers();
  try {
    const detail = buildExecutionDetail(
      executionWithDriftFlags({ material: true, critical: true }),
    );

    assert.match(detail, /critical risk drift detected/);
    assert.doesNotMatch(detail, /material risk drift detected/);
  } finally {
    rmSync(outDir, { recursive: true, force: true });
  }
});

test("AUDIT-RISK-002 execution notification omits drift text without drift flags", () => {
  const { outDir, buildExecutionDetail } = compileNotificationHelpers();
  try {
    const detail = buildExecutionDetail(
      executionWithDriftFlags({ material: false, critical: false }),
    );

    assert.doesNotMatch(detail, /material risk drift detected/);
    assert.doesNotMatch(detail, /critical risk drift detected/);
  } finally {
    rmSync(outDir, { recursive: true, force: true });
  }
});
