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
    path.join(tempRoot, "next-link-stub.js"),
    [
      'const React = require("react");',
      'function Link({ href, children, ...props }) { return React.createElement("a", { ...props, href }, children); }',
      "module.exports = Link;",
      "module.exports.default = Link;",
      "",
    ].join("\n"),
  );
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
        path.join(frontendRoot, "components", "aimee", "aimee-overview.tsx"),
        path.join(frontendRoot, "components", "aimee", "utils.ts"),
        path.join(frontendRoot, "components", "aimee", "types.ts"),
        path.join(frontendRoot, "components", "control-plane", "control-plane-live.tsx"),
        path.join(frontendRoot, "components", "coverage", "coverage-live.tsx"),
        path.join(frontendRoot, "components", "dashboard", "dashboard-live.tsx"),
        path.join(frontendRoot, "components", "live", "live-system-view.tsx"),
        path.join(frontendRoot, "components", "markets", "market-overview-dashboard.tsx"),
        path.join(frontendRoot, "components", "dashboard", "notification-center.tsx"),
        path.join(frontendRoot, "components", "risk", "risk-allocation-live.tsx"),
        path.join(frontendRoot, "components", "console", "primitives.tsx"),
        path.join(frontendRoot, "lib", "api.ts"),
        path.join(frontendRoot, "lib", "execution-notifications.ts"),
        path.join(frontendRoot, "lib", "format.ts"),
        path.join(frontendRoot, "lib", "live-system-view.ts"),
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
    if (request === "next/link") {
      return path.join(path.dirname(outDir), "next-link-stub.js");
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

function unavailableAimeeSnapshot(overrides = {}) {
  return {
    review: null,
    history: [],
    controlPlane: null,
    coverage: null,
    telemetry: null,
    events: [],
    strategies: [],
    updatedAt: null,
    ...overrides,
  };
}

function baseOperatorReview(overrides = {}) {
  const timestamp = "2026-05-17T10:00:00.000Z";
  return {
    metadata: {
      review_id: 101,
      review_type: "operator_summary",
      generated_at: timestamp,
      requested_date: null,
      scope: {},
      source_coverage: {
        trades_available: true,
        positions_available: true,
        executions_available: true,
        runtimes_available: true,
        reconciliation_available: true,
        broker_summary_available: false,
        stream_health_available: false,
        coverage_notes: ["Telemetry unavailable"],
      },
      generation_mode: "deterministic_only",
    },
    facts: {
      account_value: 10000,
      account_value_change_percent: 0,
      daily_pnl: 0,
      daily_pnl_percent: 0,
      open_risk_percent: 0,
      open_positions_count: 0,
      active_runtimes: 0,
      main_open_risk: null,
      largest_risk_share_percent: 0,
      top_risk_exposures: [],
      strategy_health: [],
      risk_rejections_24h: 0,
      execution_failures_24h: 0,
      reconciliation_issues_24h: 0,
      stale_runtimes: 0,
      stream_connected: null,
      stream_last_tick_at: null,
      baseline_open_risk_percent: null,
      baseline_largest_risk_share_percent: null,
      baseline_trade_count_24h: null,
      baseline_win_rate_24h: null,
    },
    derived_observations: [
      {
        code: "steady",
        label: "No immediate anomalies detected.",
        detail: "Reviewer records do not show an active anomaly.",
        severity: "info",
      },
    ],
    possible_contributors: [],
    warnings: [],
    supporting_metrics: [],
    ai_summary: null,
    provenance: null,
    ...overrides,
  };
}

function baseControlPlaneFamily(overrides = {}) {
  const timestamp = "2026-05-17T10:00:00.000Z";
  return {
    strategy_name: "Breakout",
    display_name: "Breakout",
    description: "Momentum breakout strategy",
    governance: {
      approval_state: "APPROVED",
      autonomous_operation_allowed: true,
      emergency_stop: false,
      approved_asset_classes: ["FOREX"],
      approved_instruments: ["CS.D.EURUSD.MINI.IP"],
      approved_profile_names: ["default"],
      supported_asset_classes: ["FOREX"],
      available_profile_names: ["default"],
      updated_at: timestamp,
    },
    deployment: {
      state: "AUTO_DEPLOYED",
      selected_profile: "default",
      selected_profile_parameters: {},
      selected_instrument: "CS.D.EURUSD.MINI.IP",
      selected_asset_class: "FOREX",
      suitability_score: 1,
      suitability_reason: "eligible",
      profile_selected_at: timestamp,
      profile_change_reason: null,
      last_restart_reason: null,
      blocked_reason: null,
      degraded_reason: null,
      last_evaluated_at: timestamp,
      last_deployed_at: timestamp,
      updated_at: timestamp,
    },
    runtime: {
      is_running: true,
      active_runtime_id: "runtime-1",
      active_instrument: "CS.D.EURUSD.MINI.IP",
      active_profile_name: "default",
      active_parameters: {},
      control_mode: "AUTO",
      runtime_mode: "NORMAL",
      recovery_state: null,
      updated_at: timestamp,
      persisted_runtimes: [],
    },
    alignment: {
      is_aligned: true,
      status: "ALIGNED",
      reason: "Runtime matches deployment.",
      checks: [],
    },
    recent_events: [],
    ...overrides,
  };
}

function baseControlPlaneSummary(overrides = {}) {
  return {
    autonomous_control_enabled: true,
    configured_autonomous_control_enabled: true,
    effective_autonomous_control_enabled: true,
    autonomy_override_active: false,
    autonomy_override_value: null,
    autonomy_override_reason: null,
    autonomy_updated_at: "2026-05-17T10:00:00.000Z",
    feed_source_state: "LIVE",
    feed_health_state: "HEALTHY",
    broker_connectivity_state: "CONNECTED",
    entry_eligible: true,
    exit_eligible: true,
    entry_block_reason: null,
    exit_block_reason: null,
    open_risk_management_state: "MANAGED",
    open_risk_management_reason: "Global open-risk state is managed.",
    counts: {
      AUTO_DEPLOYED: 1,
    },
    misaligned_count: 0,
    families: [baseControlPlaneFamily()],
    ...overrides,
  };
}

function unavailableLiveErrors(message = "Backend source unavailable.") {
  return {
    positions: message,
    executions: message,
    strategies: message,
    brokerAuth: message,
    streamHealth: message,
    coverage: message,
    controlPlane: message,
    telemetry: message,
    exposure: message,
    alerts: message,
    events: message,
  };
}

function baseDashboardErrors() {
  return {
    positions: null,
    trades: null,
    executions: null,
    brokerAuth: null,
    dashboard: null,
    streamHealth: null,
    coverage: null,
    controlPlane: null,
    operatingLimits: null,
    allocationExposure: null,
    allocationAlerts: null,
    allocationDrift: null,
    allocationCycles: null,
    allocationIntents: null,
  };
}

function baseCoverageErrors() {
  return {
    coverage: null,
    telemetry: null,
    operatingLimits: null,
    feedState: null,
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

test("AUDIT-UI-006 rendered AIMEE control-plane summary treats missing source as unavailable truth", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const aimee = require(path.join(outDir, "components", "aimee", "aimee-overview.js"));
      const utils = require(path.join(outDir, "components", "aimee", "utils.js"));
      const snapshot = unavailableAimeeSnapshot();

      const html = renderComponent(aimee.AimeeOverview, {
        isExpanded: true,
        onToggle: () => {},
        systemSummary: utils.buildSystemSummary(snapshot, "control-plane"),
        compactMetric: "Context unavailable",
        attentionCount: utils.buildWarningItems(snapshot, "control-plane").length,
        updatedAt: snapshot.updatedAt,
        whatMatters: utils.buildWhatMatters(snapshot, "control-plane"),
        warningItems: utils.buildWarningItems(snapshot, "control-plane"),
        recentChanges: utils.buildRecentChanges(snapshot),
      });

      assert.match(html, /Control-plane source unavailable/i);
      assert.match(html, /Mismatches[\s\S]*Unknown/i);
      assert.match(html, /AIMEE cannot verify governance, runtime alignment, or open-risk state/i);
      assert.doesNotMatch(html, /0 mismatches/i);
      assert.doesNotMatch(html, /No high-signal warnings are currently active/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered AIMEE open-risk card does not convert unavailable state to no open risk", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const aimee = require(path.join(outDir, "components", "aimee", "aimee-overview.js"));
      const utils = require(path.join(outDir, "components", "aimee", "utils.js"));
      const snapshot = unavailableAimeeSnapshot({
        controlPlane: {
          misaligned_count: 0,
          effective_autonomous_control_enabled: false,
          entry_eligible: false,
          exit_eligible: false,
          entry_block_reason: "backend_unavailable",
          exit_block_reason: "backend_unavailable",
          open_risk_management_state: "UNAVAILABLE",
          open_risk_management_reason: "Control-plane state could not be loaded.",
          families: [],
        },
      });

      const html = renderComponent(aimee.AimeeOverview, {
        isExpanded: true,
        onToggle: () => {},
        systemSummary: utils.buildSystemSummary(snapshot, "control-plane"),
        compactMetric: "Context unavailable",
        attentionCount: utils.buildWarningItems(snapshot, "control-plane").length,
        updatedAt: snapshot.updatedAt,
        whatMatters: utils.buildWhatMatters(snapshot, "control-plane"),
        warningItems: utils.buildWarningItems(snapshot, "control-plane"),
        recentChanges: utils.buildRecentChanges(snapshot),
      });

      assert.match(html, /Open-risk state unavailable/i);
      assert.match(html, /Control-plane state could not be loaded/i);
      assert.match(html, /UNAVAILABLE/);
      assert.doesNotMatch(html, /No unmanaged or exit-only open risk is currently surfaced/i);
      assert.doesNotMatch(html, /NO_OPEN_RISK/);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered AIMEE operate summary does not look healthy without telemetry source", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const aimee = require(path.join(outDir, "components", "aimee", "aimee-overview.js"));
      const utils = require(path.join(outDir, "components", "aimee", "utils.js"));
      const snapshot = unavailableAimeeSnapshot({
        review: baseOperatorReview(),
      });

      const html = renderComponent(aimee.AimeeOverview, {
        isExpanded: true,
        onToggle: () => {},
        systemSummary: utils.buildSystemSummary(snapshot, "operate"),
        compactMetric: "0% risk",
        attentionCount: utils.buildWarningItems(snapshot, "operate").length,
        updatedAt: snapshot.updatedAt,
        whatMatters: utils.buildWhatMatters(snapshot, "operate"),
        warningItems: utils.buildWarningItems(snapshot, "operate"),
        recentChanges: utils.buildRecentChanges(snapshot),
      });

      assert.match(html, /Telemetry source unavailable/i);
      assert.match(html, /stream, broker, and freshness truth cannot be verified/i);
      assert.match(html, /Market data freshness/i);
      assert.match(html, /Telemetry unavailable/i);
      assert.match(html, /Degraded/i);
      assert.doesNotMatch(html, /Healthy/);
      assert.doesNotMatch(html, /Streaming disconnected/);
      assert.doesNotMatch(html, /No high-signal warnings are currently active/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered control-plane family does not default missing open-risk state to no open risk", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const controlPlane = require(path.join(outDir, "components", "control-plane", "control-plane-live.js"));
      const summary = baseControlPlaneSummary({
        families: [
          baseControlPlaneFamily({
            deployment: {
              ...baseControlPlaneFamily().deployment,
              open_risk_management_state: null,
              open_risk_management_reason: null,
            },
          }),
        ],
      });

      const html = renderComponent(controlPlane.ControlPlaneLive, {
        initialSummary: summary,
        initialSummaryError: null,
      });

      assert.match(html, /Open-risk state unavailable/i);
      assert.match(html, /families need action/i);
      assert.match(html, /compact-table__row--warning/i);
      assert.doesNotMatch(html, /NO_OPEN_RISK/);
      assert.doesNotMatch(html, /No families currently need intervention/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered live view does not call all-source outage nominal or observation-only", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const live = require(path.join(outDir, "components", "live", "live-system-view.js"));
      const api = require(path.join(outDir, "lib", "api.js"));

      const html = renderComponent(live.LiveSystemView, {
        initialData: {
          positions: [],
          executions: [],
          strategies: [],
          brokerAuth: api.UNAVAILABLE_BROKER_AUTH_STATUS,
          streamHealth: api.UNAVAILABLE_STREAM_HEALTH_STATUS,
          coverage: api.UNAVAILABLE_COVERAGE_SUMMARY,
          controlPlane: api.UNAVAILABLE_CONTROL_PLANE_SUMMARY,
          telemetry: api.UNAVAILABLE_OPERATIONAL_TELEMETRY,
          exposure: api.UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
          alerts: [],
          events: [],
        },
        initialErrors: unavailableLiveErrors("Backend source unavailable."),
      });

      assert.match(html, /live sources degraded/i);
      assert.match(html, /Some live sources are degraded/i);
      assert.match(html, /Action Required[\s\S]*UNKNOWN/i);
      assert.match(html, /Source coverage degraded/i);
      assert.match(html, /Unusual activity cannot be fully evaluated/i);
      assert.doesNotMatch(html, /Nominal live posture/i);
      assert.doesNotMatch(html, /Observation only/i);
      assert.doesNotMatch(html, /No unusual activity is currently ranked above/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered dashboard stream strip preserves stale feed truth over connected stream", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const dashboard = require(path.join(outDir, "components", "dashboard", "dashboard-live.js"));
      const api = require(path.join(outDir, "lib", "api.js"));
      const timestamp = "2026-05-17T10:00:00.000Z";
      const controlPlane = {
        ...api.UNAVAILABLE_CONTROL_PLANE_SUMMARY,
        effective_autonomous_control_enabled: true,
        feed_source_state: "STALE",
        feed_health_state: "DEGRADED",
        entry_eligible: false,
        exit_eligible: true,
        entry_block_reason: "stale_market_data",
        open_risk_management_state: "MANAGED",
        open_risk_management_reason: "Open risk is managed.",
      };
      const streamHealth = {
        enabled: true,
        connected: true,
        dependency_ready: true,
        subscribed_instruments: ["CS.D.EURUSD.MINI.IP"],
        last_tick_at: timestamp,
        last_status: "Connected",
        last_error: null,
      };

      const html = renderComponent(dashboard.DashboardLive, {
        initialPositions: [],
        initialTrades: [],
        initialExecutions: [],
        initialBrokerAuth: {
          state: "connected",
          label: "Telemetry Connected",
          detail: "Connectivity derived from system telemetry",
          position_count: 0,
        },
        initialDashboard: {
          accountValue: null,
          accountValuePercent: null,
          dailyPnl: null,
          dailyPnlPercent: null,
          openRisk: 0,
          winRate: null,
          riskReward: null,
          brokerInfo: null,
          runningStrategies: [],
        },
        initialStreamHealth: streamHealth,
        initialCoverage: {
          ...api.UNAVAILABLE_COVERAGE_SUMMARY,
          streaming: {
            ...api.UNAVAILABLE_COVERAGE_SUMMARY.streaming,
            desired_instruments: ["CS.D.EURUSD.MINI.IP"],
            execution_readiness: [
              {
                instrument: "CS.D.EURUSD.MINI.IP",
                is_ok: false,
                market_open: true,
                tradable: true,
                quote_fresh: false,
                spread_ok: true,
                session_valid: true,
                dealing_allowed: true,
                last_price_age_ms: 120000,
                spread: null,
                reason: "stale_market_data",
              },
            ],
          },
        },
        initialControlPlane: controlPlane,
        initialOperatingLimits: {
          ...api.UNAVAILABLE_SYSTEM_OPERATING_LIMITS,
          execution: {
            ...api.UNAVAILABLE_SYSTEM_OPERATING_LIMITS.execution,
            max_price_age_ms: 15000,
          },
          risk: {
            ...api.UNAVAILABLE_SYSTEM_OPERATING_LIMITS.risk,
            max_open_risk_percent: 5,
          },
        },
        initialAllocationExposure: api.UNAVAILABLE_ALLOCATION_EXPOSURE_SUMMARY,
        initialAllocationAlerts: [],
        initialAllocationDrift: api.UNAVAILABLE_ALLOCATION_DRIFT_SUMMARY,
        initialAllocationCycles: [],
        initialAllocationIntents: [],
        initialErrors: baseDashboardErrors(),
      });

      assert.match(html, /Stream[\s\S]{0,240}Stale/i);
      assert.match(html, /Feed stale/i);
      assert.doesNotMatch(html, /Stream[\s\S]{0,240}Live/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered coverage watchlist does not tone polling fallback as healthy streaming", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const coverage = require(path.join(outDir, "components", "coverage", "coverage-live.js"));
      const api = require(path.join(outDir, "lib", "api.js"));
      const timestamp = "2026-05-17T10:00:00.000Z";
      const instrument = "CS.D.EURUSD.MINI.IP";

      const html = renderComponent(coverage.CoverageLive, {
        initialCoverage: {
          ...api.UNAVAILABLE_COVERAGE_SUMMARY,
          streaming: {
            ...api.UNAVAILABLE_COVERAGE_SUMMARY.streaming,
            active_instruments: [
              {
                instrument,
                tier: "TIER1",
                status: "ACTIVE",
                asset_class: "FOREX",
                pinned: false,
                reason: "strategy_watchlist",
                reason_detail: null,
                protective: false,
                priority_score: 1,
                requested_frequency: "1s",
                promotion_expires_at: null,
                last_streamed_at: timestamp,
                last_refreshed_at: timestamp,
                streamed: true,
              },
            ],
            execution_readiness: [
              {
                instrument,
                is_ok: false,
                market_open: true,
                tradable: true,
                quote_fresh: false,
                spread_ok: true,
                session_valid: true,
                dealing_allowed: true,
                last_price_age_ms: 45000,
                spread: null,
                reason: "polling_fallback",
              },
            ],
            desired_instruments: [instrument],
          },
        },
        initialTelemetry: {
          ...api.UNAVAILABLE_OPERATIONAL_TELEMETRY,
          status: "degraded",
          feed_source_state: "POLLING_FALLBACK",
          feed_health_state: "DEGRADED",
          stream_connected: false,
          stream_last_tick_at: null,
          stream_last_tick_age_ms: null,
          entry_eligible: false,
          entry_block_reason: "polling_fallback",
        },
        initialOperatingLimits: api.UNAVAILABLE_SYSTEM_OPERATING_LIMITS,
        initialFeedState: {
          generated_at: timestamp,
          instruments: [
            {
              instrument,
              stream_status: "POLLING_FALLBACK",
              stream_connected: false,
              stream_enabled: true,
              streaming_now: false,
              desired: true,
              capped: false,
              last_tick_at: null,
              last_tick_age_ms: null,
              spread: null,
              price_source: "FALLBACK",
              stream_reason: {
                code: "polling_fallback",
                label: "Polling fallback",
                operator_action: "Live stream is unavailable; fallback polling is active.",
              },
              market_status: null,
              market_error: null,
              entry_eligibility: "BLOCKED",
              entry_eligibility_reason: {
                code: "polling_fallback",
                label: "Polling fallback",
                operator_action: "Entry is blocked while fallback polling is active.",
              },
              strategies_may_evaluate: false,
              active_strategy_runtime_count: 1,
              watchlist_entry: null,
            },
          ],
        },
        initialErrors: baseCoverageErrors(),
      });

      assert.match(html, /compact-table__row--warning[\s\S]{0,520}Polling fallback/i);
      assert.match(html, /Live stream is unavailable; fallback polling is active/i);
      assert.doesNotMatch(html, /compact-table__row--positive[\s\S]{0,520}Polling fallback/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("AUDIT-UI-006 rendered markets dashboard does not turn unavailable sources into market counts", () => {
  const { tempRoot, outDir } = compileRenderedModules();
  try {
    withCompiledAliases(outDir, () => {
      const markets = require(path.join(outDir, "components", "markets", "market-overview-dashboard.js"));
      const api = require(path.join(outDir, "lib", "api.js"));

      const html = renderComponent(markets.MarketOverviewDashboard, {
        initialOverview: {
          generatedAt: "1970-01-01T00:00:00.000Z",
          summary: {
            category: "forex",
            label: "Forex",
            description: "Market overview backend data is unavailable.",
            status: "UNAVAILABLE",
            headline: "Backend unavailable",
            detail: "Market overview could not be loaded. Counts are unavailable, not zero market truth.",
            nextTransitionAt: "1970-01-01T00:00:00.000Z",
            nextTransitionLabel: "Unavailable",
            tradableCount: 0,
            activeCount: 0,
            totalCount: 0,
          },
          instruments: [],
        },
        initialOverviewError: "Market overview unavailable.",
        initialCatalogue: api.UNAVAILABLE_MARKET_CATALOGUE,
        initialCatalogueError: "Catalogue unavailable.",
        initialStrategyWatchlist: api.UNAVAILABLE_STRATEGY_WATCHLIST,
        initialStrategyWatchlistError: "Strategy watchlist unavailable.",
      });

      assert.match(html, /Catalogue[\s\S]{0,260}Unavailable/i);
      assert.match(html, /Shortlist[\s\S]{0,260}Unavailable/i);
      assert.match(html, /Live[\s\S]{0,260}Unavailable/i);
      assert.match(html, /Market overview could not be loaded/i);
      assert.match(html, /Counts are unavailable, not zero market truth/i);
      assert.doesNotMatch(html, /Catalogue[\s\S]{0,260}Available markets/i);
      assert.doesNotMatch(html, /Shortlist[\s\S]{0,260}operator interest/i);
      assert.doesNotMatch(html, /Live[\s\S]{0,260}Streaming\/evaluating/i);
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});
