import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const frontendRoot = path.resolve(import.meta.dirname, "..");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

test("AUDIT-UI-001 nav refresh failures render health as unknown instead of nominal", () => {
  const navSource = readFrontendFile("components/app-nav.tsx");

  assert.match(navSource, /controlPlaneLoadError/);
  assert.match(navSource, /Health unavailable|Health unknown|Unknown/);
  assert.doesNotMatch(navSource, /catch\s*\{\s*\/\/ Keep last known header status if refresh fails\.\s*\}/);
});

test("AUDIT-UI-003 live broker status is labelled as telemetry-derived unless broker-confirmed", () => {
  const liveModelSource = readFrontendFile("lib/live-system-view.ts");

  assert.match(liveModelSource, /Telemetry-derived broker state/);
  assert.doesNotMatch(liveModelSource, /source:\s*"Broker-confirmed"/);
});
