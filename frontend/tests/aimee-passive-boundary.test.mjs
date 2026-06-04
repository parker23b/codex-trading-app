import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

const frontendRoot = path.resolve(import.meta.dirname, "..");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

function extractFunction(source, name) {
  const start = source.indexOf(`export async function ${name}`);
  assert.notEqual(start, -1, `${name} should be exported`);

  const nextExport = source.indexOf("\nexport ", start + 1);
  return source.slice(start, nextExport === -1 ? source.length : nextExport);
}

test("AIMEE-008 passive AIMEE loader calls only the passive snapshot API", () => {
  const dataSource = readFrontendFile("components/aimee/data.ts");
  const shellSource = readFrontendFile("components/aimee/aimee-shell.tsx");
  const apiSource = readFrontendFile("lib/api.ts");
  const getSnapshot = extractFunction(apiSource, "getAimeeSnapshot");

  assert.match(dataSource, /import \{ getAimeeSnapshot \} from "@\/lib\/api";/);
  assert.doesNotMatch(dataSource, /askOperationalQuestion|getOperatorSummaryReview|getReviewHistory|reviews\/|persist:\s*true/);
  assert.match(shellSource, /loadSnapshot/);
  assert.match(shellSource, /askOperationalQuestion/);
  assert.match(getSnapshot, /request<AimeeSnapshotResponse>\("\/aimee\/snapshot"/);
  assert.doesNotMatch(getSnapshot, /method:\s*"POST"|reviews\/|persist/);
});

test("AIMEE-011 passive frontend AIMEE paths never opt into mutation-like review GET persistence", () => {
  const passiveSources = [
    "components/aimee/data.ts",
    "components/aimee/aimee-shell.tsx",
    "components/aimee/aimee-overview.tsx",
    "components/aimee/aimee-conversation.tsx",
  ];

  for (const file of passiveSources) {
    const source = readFrontendFile(file);
    assert.doesNotMatch(source, /persist\s*:\s*true/, `${file} must not request persisted review GETs`);
    assert.doesNotMatch(source, /\/reviews\/(?:operator-summary|daily|strategies|runtime-health|trades)/, `${file} must not call mutation-like review GET routes directly`);
  }
});

test("TEST-016 AIMEE advisory question API is an explicit POST mutation with backend detail preservation", () => {
  const apiSource = readFrontendFile("lib/api.ts");
  const askQuestion = extractFunction(apiSource, "askOperationalQuestion");
  const requestHelper = apiSource.slice(
    apiSource.indexOf("async function request"),
    apiSource.indexOf("export async function getTrades"),
  );

  assert.match(askQuestion, /request<OperationalQuestionReviewResponse>\("\/reviews\/questions"/);
  assert.match(askQuestion, /method:\s*"POST"/);
  assert.match(askQuestion, /question:\s*payload\.question/);
  assert.doesNotMatch(askQuestion, /persist\s*:\s*true|\/aimee\/snapshot/);

  assert.match(requestHelper, /payload\.detail/);
  assert.match(requestHelper, /throw new HttpError\(response\.status,\s*detail\)/);
});
