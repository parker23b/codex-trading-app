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

test("AUDIT-UI-006 dashboard shows stale feed truth and keeps simulated closes distinct from broker-confirmed closes", async ({ page, request }) => {
  await setScenario(request, "dashboard-stale-truth");

  await page.goto("/");

  await expect(page.getByLabel("System status strip")).toContainText("Stale");
  await expect(page.getByText("stale_market_data")).toBeVisible();
  await page.getByRole("button", { name: "Trades" }).click();
  await expect(page.getByText("Simulated local close")).toBeVisible();
  await expect(page.getByText("Broker confirmed")).toBeVisible();
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

test("AUDIT-UI-006 risk alert mutation failure preserves backend detail and does not show clean success", async ({ page, request }) => {
  await setScenario(request, "risk-alert-mutation-failure");

  await page.goto("/risk");
  await page.getByRole("button", { name: "Acknowledge" }).click();

  await expect(page.getByText("Mutation failed: backend domain-event persistence failed for alert 5")).toBeVisible();
  await expect(page.getByText("Mutation confirmed after backend alert truth refreshed.")).toHaveCount(0);
});

test("FLOW-EXIT-001 strategies view keeps broker-confirmed open-risk stop truth visible", async ({ page, request }) => {
  await setScenario(request, "strategies-open-risk");

  await page.goto("/strategies");

  await expect(page.getByText("BUY position")).toBeVisible();
  await expect(page.locator("span.muted").filter({ hasText: "BROKER-OPEN-1" }).first()).toBeVisible();
  await expect(page.getByText("Stopping this runtime does not close broker-confirmed open risk.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop Runtime" })).toBeVisible();
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

  await expect(page.getByText("BUY position")).toBeVisible();
  await expect(page.getByText("BROKER-OPEN-2")).toBeVisible();
  await expect(page.getByText("Stopping this runtime does not close broker-confirmed open risk.")).toBeVisible();
  await page.getByRole("button", { name: "Execution Feed" }).click();
  await expect(page.getByText("NEEDS MANUAL REVIEW")).toBeVisible();
  await expect(page.getByText("Broker close confirmation timed out; open risk still remains live.")).toBeVisible();
  await expect(page.getByText("Position closed")).toHaveCount(0);
});

test("AUDIT-UI-006 control-plane view keeps governance, deployment, runtime, and open-risk mismatch visible", async ({ page, request }) => {
  await setScenario(request, "control-plane-misaligned-truth");

  await page.goto("/control-plane");

  await expect(
    page.getByLabel("MISALIGNED. Runtime remains on GBP/USD while deployment intends EUR/USD."),
  ).toBeVisible();
  await expect(page.getByText("Runtime remains on GBP/USD while deployment intends EUR/USD.")).toBeVisible();
  await expect(page.getByText("Runtime: MANUAL / EXITS_ONLY active")).toBeVisible();
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

test("AUDIT-UI-004 control-plane mutation refresh failure preserves backend detail and avoids clean success copy", async ({ page, request }) => {
  await setScenario(request, "control-plane-mutation-refresh-failure");

  await page.goto("/control-plane");
  await page.getByRole("button", { name: "Pause" }).click();

  await expect(page.getByRole("button", { name: "Pausing..." })).toBeVisible();
  await expect(page.getByText("control-plane refresh failed after operator control mutation")).toBeVisible();
  await expect(page.getByText("Autonomy paused.")).toHaveCount(0);
});
