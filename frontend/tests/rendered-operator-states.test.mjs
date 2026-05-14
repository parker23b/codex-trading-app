import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const frontendRequire = createRequire(path.join(frontendRoot, "package.json"));
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const Module = require("node:module");
const runtimeModulePaths = new Map(
  ["react", "react-dom/server", "react/jsx-runtime"].map((request) => [request, frontendRequire.resolve(request)]),
);

function compileRenderedModules() {
  const tempRoot = mkdtempSync(path.join(tmpdir(), "rendered-operator-states-"));
  const outDir = path.join(tempRoot, "out");
  const configPath = path.join(tempRoot, "tsconfig.json");
  writeFileSync(
    configPath,
    JSON.stringify({
      compilerOptions: {
        target: "ES2021",
        lib: ["ES2021", "DOM"],
        module: "CommonJS",
        moduleResolution: "node",
        rootDir: frontendRoot,
        outDir,
        jsx: "react-jsx",
        skipLibCheck: true,
        esModuleInterop: true,
        strict: false,
        types: ["node", "react", "react-dom"],
        typeRoots: [path.join(frontendRoot, "node_modules", "@types")],
        baseUrl: frontendRoot,
        paths: {
          "@/*": ["*"],
        },
      },
      files: [
        path.join(frontendRoot, "components", "dashboard", "notification-center.tsx"),
        path.join(frontendRoot, "components", "risk", "risk-allocation-live.tsx"),
        path.join(frontendRoot, "components", "console", "primitives.tsx"),
        path.join(frontendRoot, "lib", "api.ts"),
        path.join(frontendRoot, "lib", "execution-notifications.ts"),
        path.join(frontendRoot, "lib", "format.ts"),
        path.join(frontendRoot, "lib", "risk-allocation.ts"),
        path.join(frontendRoot, "lib", "types.ts"),
      ],
    }),
  );
  try {
    execFileSync(path.join(frontendRoot, "node_modules", ".bin", "tsc"), ["--project", configPath], {
      cwd: frontendRoot,
      stdio: "pipe",
    });
  } catch (error) {
    const stderr = error?.stderr?.toString?.() ?? "";
    const stdout = error?.stdout?.toString?.() ?? "";
    throw new Error(`TypeScript render-fixture compilation failed.\n${stdout}${stderr}`);
  }
  return { tempRoot, outDir };
}

function withCompiledAliases(outDir, fn) {
  const originalResolveFilename = Module._resolveFilename;
  Module._resolveFilename = function resolveAlias(request, parent, isMain, options) {
    if (request.startsWith("@/")) {
      return originalResolveFilename.call(this, path.join(outDir, request.slice(2)), parent, isMain, options);
    }
    if (request === "react" || request === "react-dom/server" || request === "react/jsx-runtime") {
      return runtimeModulePaths.get(request);
    }
    return originalResolveFilename.call(this, request, parent, isMain, options);
  };
  try {
    return fn();
  } finally {
    Module._resolveFilename = originalResolveFilename;
  }
}

function renderComponent(component, props) {
  return renderToStaticMarkup(React.createElement(component, props));
}

function baseExecution(overrides = {}) {
  const timestamp = "2026-05-14T10:00:00.000Z";
  return {
    id: 42,
    trade_intent_id: 7,
    strategy_name: "Breakout",
    instrument: "CS.D.EURUSD.MINI.IP",
    phase: "ENTRY",
    status: "SUBMISSION_PENDING",
    client_request_id: "intent-7-entry",
    broker_reference: null,
    local_position_id: null,
    local_trade_id: null,
    signal_time: timestamp,
    submitted_at: null,
    acknowledged_at: null,
    completed_at: null,
    last_transition_at: timestamp,
    requested_size: 1,
    filled_size: null,
    requested_price: 1.08,
    average_fill_price: null,
    intended_risk_amount: 20,
    submitted_risk_amount: null,
    fill_derived_risk_amount: null,
    risk_truth_confidence: "UNKNOWN",
    risk_reconciliation: null,
    material_execution_drift: false,
    critical_execution_drift: false,
    reason: "Broker submission is not confirmed yet.",
    error_code: null,
    error_message: null,
    requires_manual_review: false,
    details: {},
    created_at: timestamp,
    updated_at: timestamp,
    ...overrides,
  };
}

function baseAlert(overrides = {}) {
  const timestamp = "2026-05-14T10:00:00.000Z";
  return {
    id: 5,
    alert_key: "risk-drift-5",
    alert_type: "material_execution_drift",
    severity: "error",
    state: "OPEN",
    escalation_level: 2,
    title: "Material execution drift",
    message: "Submitted risk moved materially from approved allocation.",
    count: 1,
    recurrence_count: 1,
    first_seen_at: timestamp,
    last_seen_at: timestamp,
    acknowledged_at: null,
    resolved_at: null,
    related_intent_ids: [7],
    related_cycle_ids: ["cycle-1"],
    related_execution_ids: [42],
    details: {},
    ...overrides,
  };
}

test("AUDIT-UI-006 rendered pending execution notification is degraded and not raw healthy truth", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const notifications = require(path.join(outDir, "components", "dashboard", "notification-center.js"));
      assert.equal(typeof notifications.buildExecutionNotification, "function");
      assert.equal(typeof notifications.NotificationCard, "function");

      const notification = notifications.buildExecutionNotification(baseExecution());
      const html = renderComponent(notifications.NotificationCard, {
        notification,
        onDismiss: () => {},
      });

      assert.match(html, /Entry pending broker submission/i);
      assert.match(html, /Manual review if this does not resolve/i);
      assert.match(html, /notification-item--warning/);
      assert.doesNotMatch(html, /SUBMISSION_PENDING/);
      assert.doesNotMatch(html, /Position opened/);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-004 rendered allocation alert mutation failure preserves backend detail", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const risk = require(path.join(outDir, "components", "risk", "risk-allocation-live.js"));
      assert.equal(typeof risk.RiskAlertCard, "function");

      const html = renderComponent(risk.RiskAlertCard, {
        alert: baseAlert(),
        mutation: {
          action: "acknowledge",
          error: "Mutation failed: backend domain-event persistence failed for alert 5",
          pending: false,
          success: null,
        },
        onAcknowledge: () => {},
        onResolve: () => {},
      });

      assert.match(html, /Mutation failed: backend domain-event persistence failed for alert 5/);
      assert.match(html, /Material execution drift/);
      assert.doesNotMatch(html, /Mutation confirmed/);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-002 rendered allocation risk truth marks simulated and unknown as non-exact", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const risk = require(path.join(outDir, "components", "risk", "risk-allocation-live.js"));
      assert.equal(typeof risk.RiskTruthConfidencePill, "function");

      const simulated = renderComponent(risk.RiskTruthConfidencePill, { confidence: "SIMULATED_LOCAL_FILL" });
      const unknown = renderComponent(risk.RiskTruthConfidencePill, { confidence: "UNKNOWN" });

      assert.match(simulated, /Simulated/);
      assert.match(simulated, /local simulated fill/);
      assert.match(simulated, /warning/);
      assert.match(unknown, /Unknown/);
      assert.match(unknown, /unknown or unavailable/);
      assert.match(unknown, /negative/);
      assert.doesNotMatch(`${simulated}\n${unknown}`, /Broker Confirmed|Exact/);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});
