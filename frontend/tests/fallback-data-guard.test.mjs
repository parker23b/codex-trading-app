import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const frontendRoot = path.resolve(import.meta.dirname, "..");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

function extractConstObject(source, name) {
  const start = source.indexOf(`export const ${name}`);
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

test("AUDIT-UI-007 backend-unavailable control fallbacks are explicit and fail closed", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const controlFallback = extractConstObject(apiSource, "EMPTY_CONTROL_PLANE_SUMMARY");
  const limitsFallback = extractConstObject(apiSource, "EMPTY_SYSTEM_OPERATING_LIMITS");

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
