import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

test("AIMEE-009 backend-owned AIMEE snapshot contract matches frontend API types", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "aimee.py"),
    "utf8",
  );
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(backendSource, /class AimeeSnapshotResponse\(BaseModel\):/);
  assert.match(
    frontendSource,
    /export type AimeeSnapshotResponse = \{\s*review: OperatorSummaryReview;\s*history: ReviewHistoryItem\[\];\s*controlPlane: AimeeControlPlaneSummary;\s*coverage: AimeeCoverageSummary;\s*telemetry: OperationalTelemetry;\s*events: DomainEvent\[\];\s*strategies: AimeeStrategySummary\[\];\s*updatedAt: string;\s*\};/s,
  );
});

test("ARCH-009 AIMEE control-plane frontend type keeps backend-owned fields explicit", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(frontendSource, /autonomy_override_value\?: boolean \| null;/);
  assert.match(frontendSource, /autonomy_updated_at\?: string \| null;/);
  assert.match(frontendSource, /feed_source_state: string;/);
  assert.match(frontendSource, /feed_health_state: string;/);
  assert.match(frontendSource, /broker_connectivity_state: string;/);
  assert.match(frontendSource, /open_risk_management_state\?: string \| null;/);
});

test("ARCH-012 AIMEE event parity does not collapse backend domain-event categories into an incomplete frontend union", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(frontendSource, /category: string;/);
  assert.match(frontendSource, /severity: string;/);
  assert.doesNotMatch(
    frontendSource,
    /category: "strategy" \| "risk" \| "execution" \| "reconciliation" \| "operator" \| "health";/,
  );
});
