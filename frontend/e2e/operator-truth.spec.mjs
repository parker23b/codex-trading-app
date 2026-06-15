import assert from "node:assert/strict";

import { test, expect } from "@playwright/test";

const mockApiURL = "http://127.0.0.1:4010";

async function setScenario(request, name) {
  const response = await request.post(`${mockApiURL}/__admin/scenario`, {
    data: { name },
  });
  expect(response.ok()).toBeTruthy();
}

async function getRequests(request) {
  const response = await request.get(`${mockApiURL}/__admin/requests`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  return payload.requests;
}

async function waitForAimeeSnapshotLog(request) {
  await expect
    .poll(async () => {
      const requests = await getRequests(request);
      return requests.some((entry) => entry.pathname === "/aimee/snapshot");
    })
    .toBeTruthy();
}

test("BT-DATA-001 backtests page renders explicit UTC timestamps without repairing ambiguous values", async ({ page, request }) => {
  await setScenario(request, "backtests-utc-dataset");

  await page.goto("/backtests");

  await expect(page.getByText("2026-01-01T00:00:00Z to 2026-01-01T00:05:00+00:00")).toBeVisible();
  const runForm = page.locator("form").filter({
    has: page.locator('select[name="strategy_identifier"]'),
  });
  await expect(runForm.locator('input[name="start_at"]')).toHaveValue("2026-01-01T00:00");
  await expect(runForm.locator('input[name="end_at"]')).toHaveValue("2026-01-01T00:06");
});

test("BT-ACCOUNTING-001 backtest results render explicit accounting labels", async ({ page, request }) => {
  await setScenario(request, "backtests-utc-dataset");

  await page.goto("/backtests");
  const resultSummary = page.getByLabel("System status strip").last();

  for (const label of [
    "Ending equity",
    "Realised P&L",
    "Unrealised P&L",
    "Total P&L",
    "Closed-trade win rate",
    "Open positions at end",
  ]) {
    await expect(resultSummary.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(resultSummary).not.toContainText("£");
  await expect(resultSummary).toContainText("account units");
  await expect(page.getByText("65000.12", { exact: true })).toBeVisible();
  await expect(page.getByText("1.08456", { exact: true })).toBeVisible();
  await expect(page.getByText("Result checksum:", { exact: false })).toBeVisible();
  await expect(page.getByText("Exposure: wall-clock union across open intervals")).toBeVisible();
  await expect(page.getByText(/Price decimals are adaptive display formatting/)).toBeVisible();
});

test("BT-DATA-001 provider and backtest datetime-local submissions send explicit UTC instants", async ({ browser, request, baseURL }) => {
  await setScenario(request, "backtests-utc-dataset");
  const context = await browser.newContext({
    baseURL,
    timezoneId: "America/New_York",
  });
  const page = await context.newPage();

  try {
    await page.goto("/backtests");

    const providerForm = page.locator("form").filter({
      has: page.getByRole("button", { name: "Request provider import" }),
    });
    await providerForm.locator('input[name="display_name"]').fill("Provider UTC");
    await providerForm.locator('input[name="instruments"]').fill("TEST_FX");
    await providerForm.locator('input[name="start_at"]').fill("2026-01-01T00:00");
    await providerForm.locator('input[name="end_at"]').fill("2026-01-01T01:00");
    await providerForm.getByRole("button", { name: "Request provider import" }).click();

    await expect
      .poll(async () => {
        const requests = await getRequests(request);
        return requests.find(
          (entry) =>
            entry.method === "POST" &&
            entry.pathname === "/historical-data/imports",
        )?.body;
      })
      .toMatchObject({
        start_at: "2026-01-01T05:00:00.000Z",
        end_at: "2026-01-01T06:00:00.000Z",
      });

    const runForm = page.locator("form").filter({
      has: page.locator('select[name="strategy_identifier"]'),
    });
    await expect(runForm.locator('input[name="start_at"]')).toHaveValue(
      "2025-12-31T19:00",
    );
    await runForm.locator('input[name="start_at"]').fill("2026-01-02T00:00");
    await runForm.locator('input[name="end_at"]').fill("2026-01-02T00:06");
    const runButton = runForm.getByRole("button", { name: "Start manual backtest" });
    await expect(runButton).toBeEnabled();
    const invalidFields = await runForm.evaluate((form) =>
      Array.from(form.elements)
        .filter((element) => "checkValidity" in element && !element.checkValidity())
        .map((element) => ({
          name: element.getAttribute("name"),
          value: "value" in element ? element.value : null,
          message: "validationMessage" in element ? element.validationMessage : null,
        })),
    );
    assert.deepEqual(invalidFields, []);
    await runButton.click();

    await expect
      .poll(async () => {
        const requests = await getRequests(request);
        return requests.find(
          (entry) => entry.method === "POST" && entry.pathname === "/backtests",
        )?.body;
      })
      .toMatchObject({
        start_at: "2026-01-02T05:00:00.000Z",
        end_at: "2026-01-02T05:06:00.000Z",
      });
  } finally {
    await context.close();
  }
});

test("AUDIT-UI-006 dashboard shows stale feed truth and keeps simulated closes distinct from broker-confirmed closes", async ({ page, request }) => {
  await setScenario(request, "dashboard-stale-truth");

  await page.goto("/");

  await expect(page.getByLabel("System status strip")).toContainText("Stale");
  await expect(page.getByText("stale_market_data")).toBeVisible();
  await page.getByRole("button", { name: "Trades" }).click();
  await expect(page.getByText("Simulated local close")).toBeVisible();
  await expect(page.getByText("Broker confirmed")).toBeVisible();
});

test("AUDIT-UI-006 events view marks audit-write degradation as attention and keeps destructive reset hidden by default", async ({ page, request }) => {
  await setScenario(request, "events-audit-degraded");

  await page.goto("/events?selected=71");

  await expect(page.getByText("Operator Attention")).toBeVisible();
  await expect(page.getByText("Audit trail degraded. Required audit writes are failing", { exact: false })).toBeVisible();
  await expect(page.getByText("Simulated local close kept distinct from broker-confirmed truth")).toBeVisible();
  await expect(page.getByText("Broker confirmed close")).toBeVisible();
  await expect(page.getByText("Correlation · audit-71")).toBeVisible();
  await expect(page.getByText("Runtime · runtime-breakout-1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear Test History (Test Only)" })).toHaveCount(0);
});

test("AUDIT-UI-006 events detail keeps recovered and adopted lifecycle provenance explicit with safe identifier projections", async ({ page, request }) => {
  await setScenario(request, "events-lifecycle-provenance");

  await page.goto("/events?selected=401");

  await expect(page.getByText("Current lifecycle state: Recovered position attached")).toBeVisible();
  await expect(page.getByText("Execution provenance: Broker confirmed")).toBeVisible();
  await expect(page.getByText("Broker reference · BRK…RCV-401 (fp-broker-401)")).toBeVisible();
  await expect(page.getByText("Client request · req…RCV-401 (fp-request-401)")).toBeVisible();
  await expect(page.getByText("Account · acct…401 (fp-account-401)")).toBeVisible();
  await expect(page.getByText("Recovered broker-confirmed open risk remains live after restart.")).toBeVisible();

  await setScenario(request, "events-lifecycle-provenance");
  await page.goto("/events?selected=402");

  await expect(page.getByText("Current lifecycle state: External position adopted")).toBeVisible();
  await expect(page.getByText("Open-risk state: Unmanaged open risk")).toBeVisible();
  await expect(page.getByText("Broker reference · BRK…ADP-402 (fp-broker-402)")).toBeVisible();
  await expect(page.getByText("Broker position was adopted during reconciliation rather than opened by normal strategy entry.")).toBeVisible();
});

test("AUDIT-UI-006 events detail keeps partial, failed, and ambiguous close truth visibly open-risk aware", async ({ page, request }) => {
  await setScenario(request, "events-close-open-risk-truth");

  await page.goto("/events?selected=411");

  await expect(page.getByText("Current lifecycle state: Partial fill")).toBeVisible();
  await expect(page.getByText("Execution provenance: Broker confirmed")).toBeVisible();
  await expect(page.getByText("Open-risk state: Exits-only open risk")).toBeVisible();
  await expect(page.getByText("Close partially filled; remaining open risk stays live until broker reconciliation completes.")).toBeVisible();

  await page.goto("/events?selected=412");

  await expect(page.getByText("Current lifecycle state: Failed")).toBeVisible();
  await expect(page.getByText("Open-risk state: Unmanaged open risk")).toBeVisible();
  await expect(page.getByText("Close rejected by broker; position remains open and requires manual review.")).toBeVisible();

  await page.goto("/events?selected=413");

  await expect(page.getByText("Current lifecycle state: Needs manual review")).toBeVisible();
  await expect(page.getByText("Open-risk state: Unmanaged open risk")).toBeVisible();
  await expect(page.getByText("Broker close confirmation timed out; close remains ambiguous and requires manual review.")).toBeVisible();
});

test("AUDIT-UI-006 events detail keeps stopped runtime distinct from flat broker risk", async ({ page, request }) => {
  await setScenario(request, "events-runtime-stopped-open-risk");

  await page.goto("/events?selected=421");

  await expect(page.getByText("Runtime mode: Stopped runtime")).toBeVisible();
  await expect(page.getByText("Control mode: Manual control")).toBeVisible();
  await expect(page.getByText("Open-risk state: Exits-only open risk")).toBeVisible();
  await expect(page.getByText("Broker reference · BRK…STP-421 (fp-broker-421)")).toBeVisible();
  await expect(page.getByText("Stopping this runtime does not close broker-confirmed open risk.").first()).toBeVisible();
  await expect(page.getByText("No open risk")).toHaveCount(0);
});

test("UI-009 events reset control stays hidden until explicitly enabled and remains visibly test-only and destructive", async ({ page, request }) => {
  await setScenario(request, "events-audit-degraded");

  await page.goto("/events?testing_controls=enabled");

  await expect(page.getByRole("button", { name: "Clear Test History (Test Only)" })).toBeVisible();
  await expect(page.getByText("Test-only destructive reset.")).toBeVisible();
  await expect(page.getByText("Clears persisted trades, executions, reviews, events, closed positions, and stopped runtimes.")).toBeVisible();
  await expect(page.getByText("Explicitly enabled")).toBeVisible();
});

test("AUDIT-LIFE-005 dashboard positions keep simulated local fill provenance distinct from broker-synced truth", async ({ page, request }) => {
  await setScenario(request, "dashboard-stale-truth");

  await page.goto("/");

  await page.getByRole("button", { name: "Positions" }).click();
  await expect(page.getByText("Simulated local fill")).toBeVisible();
  await expect(
    page.getByText("Open-risk provenance comes from local simulated fill behavior, not broker truth."),
  ).toBeVisible();
  await expect(page.getByText("Broker synced")).toHaveCount(0);
});

test("AUDIT-UI-006 live view keeps all-source outage degraded instead of nominal", async ({ page, request }) => {
  await setScenario(request, "live-outage");

  await page.goto("/live");

  await expect(page.getByText("Live sources degraded", { exact: false })).toBeVisible();
  await expect(page.getByText("Some live sources are degraded", { exact: false })).toBeVisible();
  await expect(page.getByText("Source coverage degraded", { exact: false })).toBeVisible();
  await expect(page.getByText("Unusual activity cannot be fully evaluated", { exact: false })).toBeVisible();
  await expect(page.getByText("Nominal live posture")).toHaveCount(0);
});

test("AUDIT-UI-006 dashboard summary keeps disconnected and recovered stream truth distinct from live", async ({ page, request }) => {
  await setScenario(request, "dashboard-disconnected-truth");

  await page.goto("/");
  await expect(page.locator("section[aria-label='System status strip']")).toContainText("Disconnected");
  await expect(page.locator("section[aria-label='System status strip']")).not.toContainText("Recovered");

  await setScenario(request, "dashboard-recovered-truth");

  await page.goto("/");
  await expect(page.locator("section[aria-label='System status strip']")).toContainText("Recovered");
  await expect(page.locator("section[aria-label='System status strip']")).not.toContainText("Disconnected");
});

test("AUDIT-UI-006 live summary distinguishes polling-fallback and stale stream states", async ({ page, request }) => {
  await setScenario(request, "coverage-polling-fallback");

  await page.goto("/live");
  await expect(page.getByLabel("Live system trust rail")).toContainText("Polling fallback");

  await setScenario(request, "coverage-stale-stream");

  await page.goto("/live");
  await expect(page.getByLabel("Live system trust rail")).toContainText("Stale");
  await expect(page.getByLabel("Live system trust rail")).not.toContainText("Polling fallback");
});

test("AUDIT-UI-006 live summary distinguishes disconnected, recovered, and unknown-freshness truth", async ({ page, request }) => {
  await setScenario(request, "coverage-disconnected-stream");

  await page.goto("/live");
  await expect(page.getByLabel("Live system trust rail")).toContainText("Disconnected");

  await setScenario(request, "coverage-stream-recovered");

  await page.goto("/live");
  await expect(page.getByLabel("Live system trust rail")).toContainText("Recovered");
  await expect(page.getByLabel("Live system trust rail")).not.toContainText("Disconnected");

  await setScenario(request, "coverage-unknown-freshness");

  await page.goto("/live");
  await expect(page.getByLabel("Live system trust rail")).toContainText("Unknown");
});

test("AUDIT-OBS-001 live view renders audit-write, polling fallback, stale stream, stream, and runtime degradations as attention", async ({ page, request }) => {
  await setScenario(request, "live-telemetry-degradations");

  await page.goto("/live");

  await expect(page.getByRole("button", { name: /Audit trail persistence degraded/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Polling fallback is active/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Market-data stream stale/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Runtime health degraded/i })).toBeVisible();
  await expect(page.getByText("Telemetry degraded: audit trail persistence degraded, polling fallback active, market-data stream stale, stream path degraded, runtime price freshness stale.")).toBeVisible();
  await expect(page.getByText("Telemetry is per-process and not aggregated across multiple workers.")).toBeVisible();
  await expect(page.getByText("Nominal live posture")).toHaveCount(0);
});

test("AUDIT-UI-002 risk view keeps unavailable and provisional truth from collapsing into exact risk", async ({ page, request }) => {
  await setScenario(request, "risk-truth-degraded");

  await page.goto("/risk");

  await expect(page.getByText("Risk data unavailable", { exact: false })).toBeVisible();
  await expect(page.getByLabel(/Simulated\./)).toBeVisible();
  await expect(page.getByLabel(/Provisional\./)).toBeVisible();
  await expect(page.getByText("Total portfolio risk")).toBeVisible();
  await expect(page.getByText("Risk exposure unavailable.")).toBeVisible();
  await expect(page.getByText("Broker Confirmed")).toHaveCount(0);
  await expect(page.getByText("Exact")).toHaveCount(0);
});

test("AUDIT-UI-007 nav shows DEMO dealing disabled from backend-owned broker environment truth", async ({ page, request }) => {
  await setScenario(request, "default");

  await page.goto("/");

  await expect(page.getByText("DEMO · DEALING DISABLED")).toBeVisible();
});

test("AUDIT-UI-007 nav shows DEMO dealing enabled from backend-owned broker environment truth", async ({ page, request }) => {
  await setScenario(request, "nav-demo-dealing-enabled");

  await page.goto("/");

  await expect(page.getByText("DEMO · DEALING ENABLED")).toBeVisible();
});

test("AUDIT-UI-007 nav shows LIVE dealing disabled from backend-owned broker environment truth", async ({ page, request }) => {
  await setScenario(request, "nav-live-dealing-disabled");

  await page.goto("/");

  await expect(page.getByText("LIVE · DEALING DISABLED")).toBeVisible();
});

test("AUDIT-UI-007 nav shows LIVE dealing enabled unmistakably", async ({ page, request }) => {
  await setScenario(request, "nav-live-dealing-enabled");

  await page.goto("/");

  await expect(page.getByText("LIVE · DEALING ENABLED")).toBeVisible();
});

test("AUDIT-UI-007 nav fails closed when broker environment status is unavailable or invalid", async ({ page, request }) => {
  await setScenario(request, "nav-broker-environment-unavailable");

  await page.goto("/");

  await expect(page.getByText("ENVIRONMENT UNKNOWN")).toBeVisible();

  await setScenario(request, "nav-broker-environment-invalid");

  await page.goto("/");

  await expect(page.getByText("CONFIGURATION INVALID")).toBeVisible();
});

test("AUDIT-LIFE-005 risk view keeps recovered and adopted lifecycle provenance distinct from ordinary opened truth", async ({ page, request }) => {
  await setScenario(request, "risk-recovery-adoption-truth");

  await page.goto("/risk");

  await expect(page.getByText("Recovered position attached")).toBeVisible();
  await expect(page.getByText("External position adopted")).toBeVisible();
  await expect(page.getByText("Position opened")).toHaveCount(0);
});

test("AUDIT-UI-006 risk alert mutation failure preserves backend detail and does not show clean success", async ({ page, request }) => {
  await setScenario(request, "risk-alert-mutation-failure");

  await page.goto("/risk");
  await page.getByRole("button", { name: "Acknowledge" }).click();

  await expect(page.getByText("Mutation failed: backend domain-event persistence failed for alert 5")).toBeVisible();
  await expect(page.getByText("Mutation confirmed after backend alert truth refreshed.")).toHaveCount(0);
});

test("AUDIT-UI-004 risk alert acknowledge confirms refreshed backend truth before success copy", async ({ page, request }) => {
  await setScenario(request, "risk-alert-acknowledge-confirmed");

  await page.goto("/risk");
  await page.getByRole("button", { name: "Acknowledge" }).click();

  await expect(page.getByRole("button", { name: "Acknowledging..." })).toBeVisible();
  await expect(page.getByText("Mutation confirmed after backend alert truth refreshed.")).toBeVisible();
  await expect(page.getByLabel("acknowledged")).toBeVisible();
});

test("AUDIT-UI-004 strategies start runtime preserves backend detail during pending failure", async ({ page, request }) => {
  await setScenario(request, "strategies-start-failure-detail");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Start Runtime" }).click();

  await expect(page.getByRole("button", { name: "Starting..." })).toBeVisible();
  await expect(page.getByText("Runtime start failed: strategy runtime start failed because durable audit persistence is unavailable")).toBeVisible();
  await expect(page.getByText("Runtime start confirmed after backend truth refreshed")).toHaveCount(0);
});

test("AUDIT-UI-004 strategies start runtime refresh failure avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "strategies-start-refresh-failure");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Start Runtime" }).click();

  await expect(page.getByRole("button", { name: "Starting..." })).toBeVisible();
  await expect(page.getByText("Runtime start succeeded, but backend truth refresh failed: strategy truth refresh failed after runtime start")).toBeVisible();
  await expect(page.getByText("Runtime start confirmed after backend truth refreshed")).toHaveCount(0);
});

test("AUDIT-UI-004 strategies start runtime disabled reason is explicit when launch truth is unavailable", async ({ page, request }) => {
  await setScenario(request, "strategies-start-disabled-reason");

  await page.goto("/strategies");

  await expect(page.getByRole("button", { name: "Start Runtime" })).toBeDisabled();
  await expect(page.getByText("Start unavailable because backend launch instrument truth is unavailable.")).toBeVisible();
});

test("FLOW-EXIT-001 strategies view keeps broker-confirmed open-risk stop truth visible", async ({ page, request }) => {
  await setScenario(request, "strategies-open-risk");

  await page.goto("/strategies");

  await expect(page.getByLabel("BUY position").first()).toBeVisible();
  await expect(page.locator("span.muted").filter({ hasText: "BROKER-OPEN-1" }).first()).toBeVisible();
  await expect(page.getByText("Stopping this runtime does not close broker-confirmed open risk.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop Runtime" })).toBeVisible();
});

test("FLOW-EXIT-001 strategies stop runtime requires explicit open-risk confirmation and keeps stop side effects visible", async ({ page, request }) => {
  await setScenario(request, "strategies-stop-open-risk-confirmation");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Stop Runtime" }).click();

  await expect(page.getByText("Stop only ends the selected runtime process. Broker-confirmed open risk remains live and may still need an exit-capable runtime, recovery path, or manual review.")).toBeVisible();
  await page.getByRole("button", { name: "Confirm Stop Runtime" }).click();

  await expect(page.getByRole("button", { name: "Stopping..." }).first()).toBeVisible();
  await expect(page.getByText("Runtime stop confirmed after backend truth refreshed for Breakout on", { exact: false })).toBeVisible();
});

test("AUDIT-UI-006 strategies stop runtime failure preserves backend detail after open-risk confirmation", async ({ page, request }) => {
  await setScenario(request, "strategies-stop-failure-detail");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Stop Runtime" }).click();
  await page.getByRole("button", { name: "Confirm Stop Runtime" }).click();

  await expect(page.getByRole("button", { name: "Stopping..." }).first()).toBeVisible();
  await expect(page.getByText("Runtime stop failed: runtime stop failed because open-risk handoff audit persistence failed")).toBeVisible();
  await expect(page.getByText("Runtime stop confirmed after backend truth refreshed")).toHaveCount(0);
});

test("AUDIT-LIFE-005 strategies execution feed keeps simulated local fill provenance distinct from broker-confirmed truth", async ({ page, request }) => {
  await setScenario(request, "strategies-execution-simulated-provenance");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Execution Feed" }).click();

  await expect(page.getByText("Simulated local fill")).toBeVisible();
  await expect(page.getByText("Broker confirmed")).toHaveCount(0);
});

test("FLOW-AIMEE-001 passive AIMEE refresh stays read-only until explicit advisory submission", async ({ page, request }) => {
  await setScenario(request, "aimee-passive");

  await page.goto("/live");
  await waitForAimeeSnapshotLog(request);

  await page.getByRole("button", { name: "Open AIMEE assistant" }).click();
  await expect(page.getByText("Creates advisory review record. Passive AIMEE context stays read-only.")).toBeVisible();

  const requests = await getRequests(request);
  const aimeeReads = requests.filter((entry) => entry.pathname === "/aimee/snapshot");
  const reviewMutations = requests.filter((entry) => entry.pathname === "/reviews/questions");

  assert.ok(aimeeReads.length >= 1, "expected at least one passive AIMEE snapshot request");
  assert.equal(reviewMutations.length, 0, "passive AIMEE refresh should not submit advisory mutations");
});

test("AUDIT-UI-006 control-plane surfaces keep override and unsupported family states degraded", async ({ page, request }) => {
  await setScenario(request, "control-plane-unsupported-states");

  await page.goto("/control-plane");

  await expect(page.getByText("Override active: Operator forced governed autonomy pause while unsupported family state requires review.").first()).toBeVisible();
  await expect(page.getByText("Governance unknown").first()).toBeVisible();
  await expect(page.getByText("Alignment unknown").first()).toBeVisible();
  await expect(page.getByText("Deployment unknown").first()).toBeVisible();
  await expect(page.getByText("Control mode unknown / Runtime mode unknown active")).toBeVisible();
  await expect(page.getByText("Open-risk state unknown").first()).toBeVisible();
  await expect(page.getByText("Emergency Stops")).toBeVisible();
});

test("AUDIT-UI-006 live summary keeps unsupported feed-source state unknown instead of live", async ({ page, request }) => {
  await setScenario(request, "live-unsupported-feed-state");

  await page.goto("/live");

  await expect(page.getByLabel("Live system trust rail")).toContainText("Feed state unknown");
  await expect(page.getByLabel("Live system trust rail")).not.toContainText("Live");
});

test("AUDIT-UI-006 markets surface keeps unavailable truth from collapsing into nominal market state", async ({ page, request }) => {
  await setScenario(request, "markets-unavailable-truth");

  await page.goto("/markets");

  await expect(page.getByText("Market overview could not be loaded. Counts are unavailable, not zero market truth.")).toBeVisible();
  await expect(page.getByText("Catalogue unavailable.").first()).toBeVisible();
  await expect(page.getByText("Strategy watchlist unavailable.").first()).toBeVisible();
  await expect(page.getByLabel("System status strip")).toContainText("Live");
  await expect(page.getByLabel("System status strip")).toContainText("Unavailable");
  await expect(page.getByText("Available markets")).toHaveCount(0);
});

test("AUDIT-UI-004 AIMEE advisory submission signals persistence and surfaces backend failure detail", async ({ page, request }) => {
  await setScenario(request, "aimee-advisory-failure");

  await page.goto("/live");
  await page.getByRole("button", { name: "Open AIMEE assistant" }).click();

  await expect(page.getByText("Creates advisory review record. Passive AIMEE context stays read-only.")).toBeVisible();

  await page.getByLabel("Ask AIMEE a system question").fill("What needs my attention right now?");
  await page.getByRole("button", { name: "Ask & record" }).click();

  await expect(page.getByText("review persistence failed for advisory question", { exact: false })).toBeVisible();

  const requests = await getRequests(request);
  const reviewMutations = requests.filter((entry) => entry.pathname === "/reviews/questions");
  assert.equal(reviewMutations.length, 1, "explicit advisory submission should perform exactly one persistence mutation");
});

test("FLOW-ENTRY-001 dashboard keeps pending, manual-review, and risk-rejected entry truth distinct from filled activity", async ({ page, request }) => {
  await setScenario(request, "dashboard-entry-manual-review");

  await page.goto("/");

  await expect(page.getByText("Breakout needs manual review")).toBeVisible();
  await page.getByRole("button", { name: "Activity" }).click();
  await expect(page.getByRole("cell", { name: "NEEDS MANUAL REVIEW" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "RISK REJECTED" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "SUBMISSION PENDING" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "n/a" }).first()).toBeVisible();
  await expect(page.getByText("Position opened")).toHaveCount(0);
});

test("FLOW-EXIT-001 strategies keep ambiguous close manual-review truth tied to visible open risk", async ({ page, request }) => {
  await setScenario(request, "strategies-close-manual-review");

  await page.goto("/strategies");

  await expect(page.getByLabel("BUY position").first()).toBeVisible();
  await expect(page.getByText("BRK…OPEN-2").first()).toBeVisible();
  await expect(page.getByText("Stopping this runtime does not close broker-confirmed open risk.")).toBeVisible();
  await page.getByRole("button", { name: "Execution Feed" }).click();
  await expect(page.getByText("NEEDS MANUAL REVIEW")).toBeVisible();
  await expect(page.getByText("Broker close confirmation timed out; open risk still remains live.")).toBeVisible();
  await expect(page.getByText("Position closed")).toHaveCount(0);
});

test("AUDIT-LIFE-005 strategies keep recovered open risk visible after runtime stop and preserve safe identifier fingerprints", async ({ page, request }) => {
  await setScenario(request, "strategies-recovered-open-risk");

  await page.goto("/strategies");

  await expect(page.getByText("Known open risk remains visible even without an active runtime.")).toBeVisible();
  await expect(page.getByText("Recovered during startup reconciliation from broker-confirmed open position truth.")).toBeVisible();
  await expect(page.getByText("BRK…RCV-14").first()).toBeVisible();
  await expect(page.getByText("fp-rcv-14").first()).toBeVisible();
  await expect(page.getByText("No active runtimes.")).toBeVisible();
});

test("FLOW-EXIT-001 strategies keep partial close truth tied to remaining visible open risk", async ({ page, request }) => {
  await setScenario(request, "strategies-partial-close-open-risk");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Execution Feed" }).click();

  await expect(page.getByLabel(/Partial fill\./)).toBeVisible();
  await expect(page.getByText("Close partially filled; remaining open risk stays live until broker reconciliation completes.")).toBeVisible();
  await expect(page.getByText("Known open risk remains visible even without an active runtime.")).toBeVisible();
  await expect(page.getByText("BRK…PCL-21").first()).toBeVisible();
  await expect(page.getByText("Position closed")).toHaveCount(0);
});

test("FLOW-EXIT-001 strategies keep failed close truth tied to remaining visible open risk", async ({ page, request }) => {
  await setScenario(request, "strategies-close-failed-open-risk");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Execution Feed" }).click();

  await expect(page.getByLabel(/Failed\./)).toBeVisible();
  await expect(page.getByText("Close rejected by broker; position remains open and requires manual review.")).toBeVisible();
  await expect(page.getByText("Known open risk remains visible even without an active runtime.")).toBeVisible();
  await expect(page.getByText("BRK…FCL-22").first()).toBeVisible();
  await expect(page.getByText("Position closed")).toHaveCount(0);
});

test("AUDIT-UI-006 control-plane view keeps governance, deployment, runtime, and open-risk mismatch visible", async ({ page, request }) => {
  await setScenario(request, "control-plane-misaligned-truth");

  await page.goto("/control-plane");

  await expect(
    page.getByLabel("Mismatch. Runtime remains on GBP/USD while deployment intends EUR/USD."),
  ).toBeVisible();
  await expect(page.getByText("Runtime remains on GBP/USD while deployment intends EUR/USD.")).toBeVisible();
  await expect(page.getByText("Runtime: Manual control / Exits-only runtime active")).toBeVisible();
  await expect(page.getByText("Open risk: Open-risk state unavailable")).toBeVisible();
  await expect(page.getByText("No families currently need intervention.")).toHaveCount(0);
});

test("FLOW-MARKET-DATA-001 coverage view keeps polling fallback distinct from healthy streaming", async ({ page, request }) => {
  await setScenario(request, "coverage-polling-fallback");

  await page.goto("/coverage");

  await expect(page.getByLabel("Polling fallback", { exact: true })).toBeVisible();
  await expect(page.getByText("polling_fallback")).toBeVisible();
  await expect(page.getByText("No live tick")).toBeVisible();
});

test("FLOW-MARKET-DATA-001 coverage view keeps unknown tick freshness distinct from healthy streaming truth", async ({ page, request }) => {
  await setScenario(request, "coverage-unknown-freshness");

  await page.goto("/coverage");

  await expect(page.getByText("Stream state unknown")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Unknown", exact: true })).toBeVisible();
  await expect(page.getByText("Streaming", { exact: true })).toHaveCount(0);
});

test("AUDIT-UI-006 markets view keeps unavailable catalogue truth distinct from zero healthy markets", async ({ page, request }) => {
  await setScenario(request, "markets-unavailable-truth");

  await page.goto("/markets");

  await expect(page.getByText("Catalogue unavailable.").first()).toBeVisible();
  await expect(page.getByText("Counts are unavailable, not zero market truth.")).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();
  await expect(page.getByText("available markets")).toHaveCount(0);
});

test("FLOW-MARKET-DATA-001 markets watchlist provenance does not imply trading approval", async ({ page, request }) => {
  await setScenario(request, "markets-watchlist-provenance");

  await page.goto("/markets");

  await expect(page.getByText("Watchlisted, not streaming")).toBeVisible();
  await expect(page.getByText("Evaluation candidate only")).toBeVisible();
  await expect(page.getByText("Not trading approval. Entry still depends on governance, risk, broker, and market-data gates.")).toBeVisible();
  await expect(page.getByText("Trading approved")).toHaveCount(0);
});

test("AUDIT-UI-004 markets shortlist mutation failure preserves backend detail and supports retry without premature success", async ({ page, request }) => {
  await setScenario(request, "markets-shortlist-failure-retry");

  await page.goto("/markets");
  await page.getByRole("button", { name: "Add to shortlist" }).click();

  await expect(page.getByText("Shortlist mutation failed: shortlist write failed because operator audit persistence is unavailable")).toBeVisible();
  await page.getByRole("button", { name: "Add to shortlist" }).click();

  await expect(page.getByText("Shortlist mutation confirmed after backend truth refreshed for", { exact: false })).toBeVisible();
  await expect(page.getByText("Shortlist mutation failed: shortlist write failed because operator audit persistence is unavailable")).toHaveCount(0);
});

test("AUDIT-UI-004 markets shortlist removal failure preserves backend detail and supports retry without premature success", async ({ page, request }) => {
  await setScenario(request, "markets-shortlist-remove-failure-retry");

  await page.goto("/markets");
  await page.getByRole("button", { name: "Remove from shortlist" }).click();

  await expect(page.getByText("Shortlist mutation failed: shortlist removal failed because operator audit persistence is unavailable")).toBeVisible();
  await page.getByRole("button", { name: "Remove from shortlist" }).click();

  await expect(page.getByText("Shortlist mutation confirmed after backend truth refreshed for", { exact: false })).toBeVisible();
  await expect(page.getByText("No shortlisted instruments yet.")).toBeVisible();
  await expect(page.getByText("Shortlist mutation failed: shortlist removal failed because operator audit persistence is unavailable")).toHaveCount(0);
});

test("AUDIT-UI-004 markets strategy-watchlist add refresh failure avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "markets-watchlist-add-refresh-failure");

  await page.goto("/markets");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  await expect(page.getByRole("button", { name: "Adding..." }).first()).toBeVisible();
  await expect(page.getByText("Strategy watchlist mutation succeeded, but backend truth refresh failed: strategy watchlist refresh failed after mutation")).toBeVisible();
  await expect(page.getByText("Strategy watchlist mutation confirmed after backend truth refreshed.")).toHaveCount(0);
});

test("AUDIT-UI-004 markets strategy-watchlist remove confirms refreshed backend truth without implying approval", async ({ page, request }) => {
  await setScenario(request, "markets-watchlist-remove-confirmed");

  await page.goto("/markets");

  await expect(page.getByText("Evaluation candidates. Not trading approval.")).toBeVisible();
  await page.getByRole("button", { name: "Remove", exact: true }).click();

  await expect(page.getByRole("button", { name: "Removing..." })).toBeVisible();
  await expect(page.getByText("Strategy watchlist removal confirmed after backend truth refreshed for", { exact: false })).toBeVisible();
  await expect(page.getByText("No active strategy watchlist instruments.")).toBeVisible();
});

test("AUDIT-UI-004 markets strategy-watchlist removal failure preserves backend detail and supports retry without premature success", async ({ page, request }) => {
  await setScenario(request, "markets-watchlist-remove-failure-retry");

  await page.goto("/markets");
  await page.getByRole("button", { name: "Remove", exact: true }).click();

  await expect(page.getByText("Strategy watchlist mutation failed: strategy watchlist removal failed because operator audit persistence is unavailable")).toBeVisible();
  await page.getByRole("button", { name: "Remove", exact: true }).click();

  await expect(page.getByText("Strategy watchlist removal confirmed after backend truth refreshed for", { exact: false })).toBeVisible();
  await expect(page.getByText("No active strategy watchlist instruments.")).toBeVisible();
  await expect(page.getByText("Strategy watchlist mutation failed: strategy watchlist removal failed because operator audit persistence is unavailable")).toHaveCount(0);
});

test("AUDIT-UI-004 control-plane arm confirms refreshed backend truth before success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-arm-success");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Arm" }).click();

  await expect(page.getByRole("button", { name: "Arming..." })).toBeVisible();
  await expect(page.getByText("Operator control mutation confirmed after backend truth refreshed: governed autonomy armed.")).toBeVisible();
});

test("AUDIT-UI-004 control-plane arm failure preserves backend detail and avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-arm-failure");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Arm" }).click();

  await expect(page.getByRole("button", { name: "Arming..." })).toBeVisible();
  await expect(page.getByText("Operator control mutation failed: operator control mutation audit persistence failed while arming governed autonomy")).toBeVisible();
  await expect(page.getByText("Operator control mutation confirmed after backend truth refreshed: governed autonomy armed.")).toHaveCount(0);
});

test("AUDIT-UI-004 control-plane pause confirms refreshed backend truth before success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-pause-success");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Pause" }).click();

  await expect(page.getByRole("button", { name: "Pausing..." })).toBeVisible();
  await expect(page.getByText("Operator control mutation confirmed after backend truth refreshed: governed autonomy paused.")).toBeVisible();
});

test("AUDIT-UI-004 control-plane mutation refresh failure preserves backend detail and avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-mutation-refresh-failure");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Pause" }).click();

  await expect(page.getByRole("button", { name: "Pausing..." })).toBeVisible();
  await expect(page.getByText("Operator control mutation succeeded, but backend truth refresh failed: control-plane refresh failed after operator control mutation")).toBeVisible();
  await expect(page.getByText("Operator control mutation confirmed after backend truth refreshed: governed autonomy paused.")).toHaveCount(0);
});

test("AUDIT-UI-004 control-plane governance allow confirms refreshed backend truth before success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-governance-allow-success");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Allow Auto Deploy" }).click();

  await expect(page.getByRole("button", { name: "Updating..." }).first()).toBeVisible();
  await expect(page.getByText("Governance mutation confirmed after backend truth refreshed: Breakout can auto deploy.")).toBeVisible();
});

test("AUDIT-UI-004 control-plane governance mutation failure preserves backend detail and avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-governance-mutation-failure");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Disallow" }).click();

  await expect(page.getByRole("button", { name: "Updating..." }).first()).toBeVisible();
  await expect(page.getByText("Governance mutation failed: governance mutation audit persistence failed for Breakout")).toBeVisible();
  await expect(page.getByText("Governance mutation confirmed after backend truth refreshed: Breakout auto deploy disallowed.")).toHaveCount(0);
});

test("AUDIT-UI-004 control-plane governance allow failure preserves backend detail and avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-governance-allow-failure");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Allow Auto Deploy" }).click();

  await expect(page.getByRole("button", { name: "Updating..." }).first()).toBeVisible();
  await expect(page.getByText("Governance mutation failed: governance mutation audit persistence failed while allowing Breakout auto deploy")).toBeVisible();
  await expect(page.getByText("Governance mutation confirmed after backend truth refreshed: Breakout can auto deploy.")).toHaveCount(0);
});

test("AUDIT-UI-004 control-plane governance disallow confirms refreshed backend truth before success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-governance-disallow-success");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Disallow" }).click();

  await expect(page.getByRole("button", { name: "Updating..." }).first()).toBeVisible();
  await expect(page.getByText("Governance mutation confirmed after backend truth refreshed: Breakout auto deploy disallowed.")).toBeVisible();
});

test("FLOW-ENTRY-001 strategies execution feed keeps blocked entry reason and no-order-attempt truth visible", async ({ page, request }) => {
  await setScenario(request, "strategies-entry-blocked-truth");

  await page.goto("/strategies");
  await page.getByRole("button", { name: "Execution Feed" }).click();

  await expect(page.getByText("RISK REJECTED")).toBeVisible();
  await expect(page.getByText("SUBMISSION PENDING")).toBeVisible();
  await expect(page.getByRole("cell", { name: "n/a" }).first()).toBeVisible();
  await expect(page.getByText("stale_market_data blocked a new order attempt.")).toBeVisible();
  await expect(page.getByText("Position opened")).toHaveCount(0);
});

test("FLOW-MARKET-DATA-001 coverage view keeps stale stream distinct from polling fallback and fresh streaming truth", async ({ page, request }) => {
  await setScenario(request, "coverage-stale-stream");

  await page.goto("/coverage");

  await expect(page.getByLabel("Stale market data")).toBeVisible();
  await expect(page.getByText("The latest live tick is stale and should not be treated as fresh stream truth.")).toBeVisible();
  await expect(page.getByText("92.0s").first()).toBeVisible();
  await expect(page.getByText("Polling fallback")).toHaveCount(0);
  await expect(page.getByText("Streaming", { exact: true })).toHaveCount(0);
});

test("FLOW-MARKET-DATA-001 coverage view keeps disconnected stream distinct from stale, fallback, and healthy streaming truth", async ({ page, request }) => {
  await setScenario(request, "coverage-disconnected-stream");

  await page.goto("/coverage");

  await expect(page.getByLabel("Disconnected", { exact: true })).toBeVisible();
  await expect(page.getByText("Live stream is disconnected or unavailable for this instrument.")).toBeVisible();
  await expect(page.getByText("Polling fallback")).toHaveCount(0);
  await expect(page.getByText("Streaming", { exact: true })).toHaveCount(0);
});

test("FLOW-MARKET-DATA-001 coverage view keeps recovered stream provenance visible after degradation", async ({ page, request }) => {
  await setScenario(request, "coverage-stream-recovered");

  await page.goto("/coverage");

  await expect(page.getByLabel("Recovered")).toBeVisible();
  await expect(page.getByText("Recovered", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Live stream recovered after degradation; confirm fresh ticks continue before treating the path as stable.")).toBeVisible();
});

test("AUDIT-LIFE-005 dashboard positions keep unknown broker sync and unavailable broker references visibly degraded", async ({ page, request }) => {
  await setScenario(request, "dashboard-positions-sync-unknown");

  await page.goto("/");
  await page.getByRole("button", { name: "Positions" }).click();

  await expect(page.getByText("Broker reference unavailable")).toBeVisible();
  await expect(page.getByText("Sync unavailable")).toBeVisible();
  await expect(page.getByText("Sync unknown")).toBeVisible();
  await expect(page.getByText("BRK…UNK-302")).toBeVisible();
  await expect(page.getByText("fp-unk-302")).toBeVisible();
  await expect(page.getByText("Broker synced")).toHaveCount(0);
});

test("AUDIT-LIFE-005 dashboard activity keeps simulated local close provenance distinct from broker-confirmed close truth", async ({ page, request }) => {
  await setScenario(request, "dashboard-activity-simulated-close");

  await page.goto("/");
  await page.getByRole("button", { name: "Activity" }).click();

  await expect(page.getByText("Simulated local close")).toBeVisible();
  await expect(page.getByText("Broker confirmed")).toBeVisible();
});
