import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const frontendRoot = path.resolve(import.meta.dirname, "..");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

function listFrontendFiles(relativePath) {
  const root = path.join(frontendRoot, relativePath);
  const entries = readdirSync(root, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const entryPath = path.join(relativePath, entry.name);
    if (entry.isDirectory()) {
      return listFrontendFiles(entryPath);
    }
    return entryPath;
  });
}

function extractConstObject(source, name) {
  let start = source.indexOf(`export const ${name}`);
  if (start === -1) {
    start = source.indexOf(`const ${name}`);
  }
  assert.notEqual(start, -1, `${name} export should exist`);
  const bodyStart = source.indexOf("{", start);
  assert.notEqual(bodyStart, -1, `${name} object should start`);

  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    const character = source[index];
    if (character === "{") {
      depth += 1;
    } else if (character === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(bodyStart, index + 1);
      }
    }
  }
  assert.fail(`${name} object should end`);
}

function findLoadWithMetaFallbackCalls(source) {
  const violations = [];
  let start = source.indexOf("loadWithMeta(");
  while (start !== -1) {
    const argsStart = source.indexOf("(", start);
    let depth = 0;
    let topLevelCommaCount = 0;
    for (let index = argsStart; index < source.length; index += 1) {
      const character = source[index];
      if (character === "(" || character === "{" || character === "[") {
        depth += 1;
      } else if (character === ")" || character === "}" || character === "]") {
        depth -= 1;
        if (depth === 0) {
          if (topLevelCommaCount > 0) {
            violations.push(source.slice(start, index + 1));
          }
          break;
        }
      } else if (character === "," && depth === 1) {
        topLevelCommaCount += 1;
      }
    }
    start = source.indexOf("loadWithMeta(", start + 1);
  }
  return violations;
}

test("AUDIT-UI-007 backend-unavailable control fallbacks are explicit and fail closed", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const controlFallback = extractConstObject(apiSource, "UNAVAILABLE_CONTROL_PLANE_SUMMARY");
  const limitsFallback = extractConstObject(apiSource, "UNAVAILABLE_SYSTEM_OPERATING_LIMITS");

  assert.match(controlFallback, /autonomous_control_enabled:\s*false/);
  assert.match(controlFallback, /configured_autonomous_control_enabled:\s*false/);
  assert.match(controlFallback, /effective_autonomous_control_enabled:\s*false/);
  assert.match(controlFallback, /entry_eligible:\s*false/);
  assert.match(controlFallback, /exit_eligible:\s*false/);
  assert.match(controlFallback, /entry_block_reason:\s*"backend_unavailable"/);
  assert.match(controlFallback, /exit_block_reason:\s*"backend_unavailable"/);
  assert.match(controlFallback, /open_risk_management_state:\s*"UNAVAILABLE"/);
  assert.match(controlFallback, /open_risk_management_reason:\s*"Control-plane state could not be loaded\."/);
  assert.doesNotMatch(controlFallback, /open_risk_management_state:\s*"NO_OPEN_RISK"/);

  assert.match(limitsFallback, /autonomous_control_enabled:\s*false/);
});

test("AUDIT-UI-007 backend-unavailable telemetry fallback does not assert no open risk", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const telemetryFallback = extractConstObject(apiSource, "UNAVAILABLE_OPERATIONAL_TELEMETRY");

  assert.match(telemetryFallback, /status:\s*"unknown"/);
  assert.match(telemetryFallback, /entry_eligible:\s*false/);
  assert.match(telemetryFallback, /exit_eligible:\s*false/);
  assert.match(telemetryFallback, /entry_block_reason:\s*"backend_unavailable"/);
  assert.match(telemetryFallback, /exit_block_reason:\s*"backend_unavailable"/);
  assert.match(telemetryFallback, /open_risk_management_state:\s*"UNAVAILABLE"/);
  assert.match(telemetryFallback, /open_risk_management_reason:\s*"Operational telemetry could not be loaded\."/);
  assert.doesNotMatch(telemetryFallback, /open_risk_management_state:\s*"NO_OPEN_RISK"/);
});

test("AUDIT-UI-007 nav uses backend-owned broker environment truth instead of a hardcoded unknown account env card", () => {
  const navSource = readFrontendFile("components/app-nav.tsx");

  assert.match(navSource, /Broker Env/);
  assert.match(navSource, /getBrokerEnvironmentStatus/);
  assert.match(navSource, /CONFIGURATION INVALID/);
  assert.match(navSource, /ENVIRONMENT UNKNOWN/);
  assert.doesNotMatch(navSource, /Account Env/);
  assert.doesNotMatch(navSource, /Account environment is unavailable/);
});

test("AUDIT-UI-007 frontend does not keep a hardcoded live mode fallback or infer broker environment from URL strings", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const productionSources = listFrontendFiles("app")
    .concat(listFrontendFiles("components"))
    .concat(listFrontendFiles("lib"))
    .filter((filePath) => /\.(tsx?|mjs)$/.test(filePath) && !filePath.startsWith("tests/"));

  assert.match(apiSource, /export async function getBrokerEnvironmentStatus/);
  assert.doesNotMatch(apiSource, /type BackendMode/);
  assert.doesNotMatch(apiSource, /return "live";/);

  const forbiddenUrlInference = productionSources.flatMap((filePath) => {
    const source = readFrontendFile(filePath);
    return Array.from(
      source.matchAll(/demo-api\.ig\.com|api\.ig\.com\/gateway\/deal|environment.*url/gi),
      (match) => `${filePath}: ${match[0]}`,
    );
  });
  assert.deepEqual(forbiddenUrlInference, []);
});

test("AUDIT-UI-007 API client does not expose silent fallback helper", () => {
  const apiSource = readFrontendFile("lib/api.ts");

  assert.doesNotMatch(apiSource, /export async function withFallback/);
  assert.match(apiSource, /export async function loadWithMeta/);
});

test("AUDIT-UI-007 loadWithMeta does not accept caller-provided backend-shaped fallback data", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const productionSources = listFrontendFiles("app")
    .concat(listFrontendFiles("components"))
    .concat(listFrontendFiles("lib"))
    .filter((filePath) => /\.(tsx?|mjs)$/.test(filePath) && !filePath.startsWith("tests/"));

  assert.match(apiSource, /export type LoadResult<T> = \{\s*data: T \| null;/);
  assert.match(apiSource, /export async function loadWithMeta<T>\(loader: \(\) => Promise<T>\): Promise<LoadResult<T>>/);
  assert.doesNotMatch(apiSource, /loadWithMeta<T>\(loader: \(\) => Promise<T>, fallback: T\)/);
  assert.doesNotMatch(apiSource, /export const EMPTY_/);

  const violations = productionSources.flatMap((filePath) =>
    findLoadWithMetaFallbackCalls(readFrontendFile(filePath)).map((call) => `${filePath}: ${call}`),
  );
  assert.deepEqual(violations, []);

  const emptyFallbackNames = productionSources.flatMap((filePath) => {
    const source = readFrontendFile(filePath);
    return Array.from(source.matchAll(/\bEMPTY_[A-Z0-9_]+\b/g), (match) => `${filePath}: ${match[0]}`);
  });
  assert.deepEqual(emptyFallbackNames, []);
});

test("AUDIT-UI-007 production modules do not import mock demo fake or fixture backend data", () => {
  const productionSources = listFrontendFiles("app")
    .concat(listFrontendFiles("components"))
    .concat(listFrontendFiles("lib"))
    .filter((filePath) => /\.(tsx?|mjs)$/.test(filePath) && !filePath.startsWith("tests/"));
  const forbiddenImportPattern = /^\s*import\s+(?:[^"']+\s+from\s+)?["'][^"']*(?:mock|demo|fake|fixture|fixtures)[^"']*["'];?/gim;

  const violations = productionSources.flatMap((filePath) => {
    const source = readFrontendFile(filePath);
    return Array.from(source.matchAll(forbiddenImportPattern), (match) => `${filePath}: ${match[0].trim()}`);
  });

  assert.deepEqual(violations, []);
});

test("AUDIT-UI-007 dashboard summaries do not default missing open risk to no risk", () => {
  const autonomySource = readFrontendFile("components/dashboard/autonomy-overview.tsx");
  const stripSource = readFrontendFile("components/dashboard/control-plane-strip.tsx");

  assert.match(autonomySource, /open_risk_management_state \?\? "UNAVAILABLE"/);
  assert.match(stripSource, /open_risk_management_state \?\? "UNAVAILABLE"/);
  assert.doesNotMatch(autonomySource, /open_risk_management_state \?\? "NO_OPEN_RISK"/);
  assert.doesNotMatch(stripSource, /open_risk_management_state \?\? "NO_OPEN_RISK"/);
});

test("AUDIT-UI-007 backend-unavailable market overview fallback is explicit, not limited market truth", () => {
  const marketsPageSource = readFrontendFile("app/markets/page.tsx");
  const marketFallback = extractConstObject(marketsPageSource, "UNAVAILABLE_FOREX_OVERVIEW");

  assert.match(marketFallback, /status:\s*"UNAVAILABLE"/);
  assert.match(marketFallback, /headline:\s*"Backend unavailable"/);
  assert.match(marketFallback, /detail:\s*"Market overview could not be loaded\. Counts are unavailable, not zero market truth\."/);
  assert.match(marketFallback, /nextTransitionAt:\s*new Date\(0\)\.toISOString\(\)/);
  assert.match(marketFallback, /nextTransitionLabel:\s*"Unavailable"/);
  assert.doesNotMatch(marketFallback, /status:\s*"LIMITED"/);
  assert.doesNotMatch(marketFallback, /Load on demand|Refreshes|avoid overusing IG REST endpoints|Date\.now\(\)/);
});

test("AUDIT-UI-007 live-view derived confidence cannot be high with unavailable sources", () => {
  const liveModelSource = readFrontendFile("lib/live-system-view.ts");

  assert.match(liveModelSource, /missingSourceCount === 0[\s\S]*confidence = "HIGH"/);
  assert.match(liveModelSource, /missingSourceCount \? `\$\{missingSourceCount\} source/);
  assert.doesNotMatch(liveModelSource, /missingSourceCount <= 1[\s\S]*confidence = "HIGH"/);
});
