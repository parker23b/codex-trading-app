import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const repoRoot = path.resolve(import.meta.dirname, "..");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(repoRoot, relativePath), "utf8");
}

test("AUDIT-003 passive frontend alert reads do not request refresh=true", () => {
  const passiveFiles = [
    "app/page.tsx",
    "app/live/page.tsx",
    "app/risk/page.tsx",
    "components/dashboard/dashboard-live.tsx",
    "components/live/live-system-view.tsx",
  ];

  for (const file of passiveFiles) {
    assert.doesNotMatch(
      readFrontendFile(file),
      /getAllocationAlerts\(\{[^)]*refresh:\s*true/s,
      `${file} must not refresh allocation alerts from a passive surface`,
    );
  }

  const riskLive = readFrontendFile("components/risk/risk-allocation-live.tsx");
  const refreshTrueCalls = [
    ...riskLive.matchAll(/getAllocationAlerts\(\{[^)]*refresh:\s*true/gs),
  ];
  assert.equal(
    refreshTrueCalls.length,
    1,
    "risk live view should reserve refresh=true for the explicit alert mutation follow-up",
  );
  assert.match(
    riskLive.slice(Math.max(0, refreshTrueCalls[0].index - 80), refreshTrueCalls[0].index),
    /mutateAlert|const nextAlerts = await/s,
  );
});
