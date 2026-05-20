import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

test("API-003 markets route family uses backend-owned response models", () => {
  const backendSource = readFileSync(
    path.join(repoRoot, "backend", "app", "api", "contracts", "markets.py"),
    "utf8",
  );

  for (const className of [
    "MarketCategoryOverviewResponse",
    "MarketCatalogueResponse",
    "ShortlistResponse",
    "ShortlistMutationResponse",
    "StrategyWatchlistBulkResponse",
    "StrategyWatchlistResponse",
    "StrategyWatchlistMutationResponse",
    "FeedStateResponse",
    "FeedStateInstrumentResponse",
    "LiveChartResponse",
  ]) {
    assert.match(backendSource, new RegExp(`class ${className}\\(BaseModel\\):`));
  }
});

test("ARCH-009 markets frontend types keep stream and price provenance explicit", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type FeedState = \{[\s\S]*stream_status: "streaming" \| "stale" \| "desired" \| "capped" \| "inactive";/s,
  );
  assert.match(
    frontendSource,
    /export type FeedState = \{[\s\S]*price_source: "STREAM" \| "SNAPSHOT" \| "STALE" \| "UNAVAILABLE";/s,
  );
  assert.match(
    frontendSource,
    /export type FeedMarketStatus = \{[\s\S]*last_price_age_ms: number;[\s\S]*reason\?: string \| null;/s,
  );
});

test("API-004 frontend API client uses typed watchlist mutation responses", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "api.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export async function addShortlistInstrument\(instrumentId: string\): Promise<ShortlistMutationResponse>/,
  );
  assert.match(
    frontendSource,
    /export async function removeShortlistInstrument\(instrumentId: string\): Promise<ShortlistMutationResponse>/,
  );
  assert.match(
    frontendSource,
    /export async function removeStrategyWatchlistInstrument\(instrumentId: string\): Promise<StrategyWatchlistMutationResponse>/,
  );
});

test("UI-001 and UI-011 market feed types keep freshness and watchlist provenance fields visible", () => {
  const frontendSource = readFileSync(
    path.join(frontendRoot, "lib", "types.ts"),
    "utf8",
  );

  assert.match(
    frontendSource,
    /export type FeedState = \{[\s\S]*last_tick_at\?: string \| null;[\s\S]*last_tick_age_ms\?: number \| null;[\s\S]*market_error\?: string \| null;[\s\S]*watchlist_entry\?: StrategyWatchlistEntry \| null;/s,
  );
});
