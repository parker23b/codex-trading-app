import {
  AllocationAlert,
  AllocationCycle,
  AllocationDriftSummary,
  AllocationExposureSummary,
  AllocationIntent,
  AimeeSnapshotResponse,
  BrokerAuthStatus,
  CoverageSummary,
  ControlPlaneSummary,
  DashboardSnapshot,
  DomainEvent,
  Execution,
  FeedState,
  FeedStateResponse,
  LiveChartResponse,
  MarketCatalogueResponse,
  MarketCategory,
  MarketCategoryOverviewResponse,
  OperatorControlState,
  OperatorSummaryReview,
  OperationalTelemetry,
  OperationalQuestionReviewResponse,
  Position,
  ReviewHistoryItem,
  SystemOperatingLimits,
  StrategyDefinition,
  StrategyWatchlistBulkResult,
  StrategyWatchlistResponse,
  StreamHealthStatus,
  Trade,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 1500;
const MARKET_REQUEST_TIMEOUT_MS = 12000;

export const EMPTY_BROKER_AUTH_STATUS: BrokerAuthStatus = {
  state: "unavailable",
  label: "Broker Unavailable",
  detail: "Broker status could not be loaded.",
  position_count: 0,
};

export const EMPTY_STREAM_HEALTH_STATUS: StreamHealthStatus = {
  enabled: false,
  connected: false,
  dependency_ready: false,
  subscribed_instruments: [],
  last_tick_at: null,
  last_status: "Unavailable",
  last_error: "Stream health could not be loaded.",
};

export const EMPTY_COVERAGE_SUMMARY: CoverageSummary = {
  streaming: {
    active_instruments: [],
    execution_readiness: [],
    desired_instruments: [],
    pinned_instruments: [],
    capped_instruments: [],
    asset_class_usage: {},
  },
  tier2: {
    refresh_queue: [],
    active_candidates: [],
  },
  promotions: {
    pending_count: 0,
    accepted_count: 0,
    rejected_count: 0,
    expired_count: 0,
    recent_requests: [],
  },
  trade_allocator: {
    selected_count: 0,
    rejected_count: 0,
    reason_counts: {},
    recent_decisions: [],
  },
};

export const EMPTY_CONTROL_PLANE_SUMMARY: ControlPlaneSummary = {
  autonomous_control_enabled: true,
  configured_autonomous_control_enabled: true,
  effective_autonomous_control_enabled: true,
  autonomy_override_active: false,
  autonomy_override_value: null,
  autonomy_override_reason: null,
  autonomy_updated_at: null,
  feed_source_state: "DISCONNECTED",
  feed_health_state: "FAILED",
  broker_connectivity_state: "DISCONNECTED",
  entry_eligible: false,
  exit_eligible: false,
  entry_block_reason: "data_disconnected",
  exit_block_reason: "data_disconnected",
  open_risk_management_state: "NO_OPEN_RISK",
  open_risk_management_reason: null,
  counts: {},
  misaligned_count: 0,
  families: [],
};

export const EMPTY_OPERATIONAL_TELEMETRY: OperationalTelemetry = {
  status: "unknown",
  last_heartbeat: new Date(0).toISOString(),
  heartbeat_age_ms: null,
  last_price_update: null,
  last_price_age_ms: null,
  last_reconciliation: null,
  last_reconciliation_age_ms: null,
  stream_connected: false,
  stream_last_tick_at: null,
  stream_last_tick_age_ms: null,
  subscribed_instrument_count: 0,
  desired_instrument_count: 0,
  broker_connected: false,
  feed_source_state: "DISCONNECTED",
  feed_health_state: "FAILED",
  broker_connectivity_state: "DISCONNECTED",
  entry_eligible: false,
  exit_eligible: false,
  entry_block_reason: "data_disconnected",
  exit_block_reason: "data_disconnected",
  open_risk_management_state: "NO_OPEN_RISK",
  open_risk_management_reason: null,
  broker_latency_ms: null,
  runtime_count: 0,
  active_runtime_count: 0,
  stale_runtime_count: 0,
  stale_price_runtime_count: 0,
  reconciliation_mismatches: 0,
  order_failures_last_5m: 0,
  rejected_orders_last_5m: 0,
  strategies_paused_by_health: 0,
};

export const EMPTY_SYSTEM_OPERATING_LIMITS: SystemOperatingLimits = {
  autonomous_control_enabled: true,
  risk: {
    max_open_positions: 0,
    max_positions_per_strategy: 0,
    max_open_risk_percent: 0,
    daily_loss_limit: 0,
    max_position_notional: 0,
    max_unhealthy_runtimes: 0,
    global_entry_kill_switch: false,
  },
  execution: {
    max_price_age_ms: 0,
    max_spread_pips: 0,
    max_spread_percent_of_price: 0,
    entry_burst_limit: 0,
    entry_burst_window_seconds: 0,
    failed_entry_retry_cooldown_seconds: 0,
    duplicate_signal_window_seconds: 0,
    cooldown_after_loss_seconds: 0,
    cooldown_after_exit_seconds: 0,
    allocator_enabled: false,
    allocator_max_decisions_per_cycle: 0,
    allocator_max_open_positions_per_instrument: 0,
    allocator_signal_stale_after_seconds: 0,
  },
  coverage: {
    streaming_enabled: false,
    max_instruments: 0,
    requested_frequency: "n/a",
    max_promotions_per_minute: 0,
    max_subscription_churn_per_minute: 0,
    promotion_score_threshold: 0,
    eviction_score_threshold: 0,
    min_tier1_residency_seconds: 0,
    demotion_cooldown_seconds: 0,
    tier2_refresh_enabled: false,
    tier2_refresh_interval_seconds: 0,
    tier2_refresh_batch_size: 0,
    tier2_refresh_stale_after_seconds: 0,
    tier2_promotion_score_threshold: 0,
    tier2_promotion_ttl_seconds: 0,
    asset_class_slot_budgets: {},
    seed_instruments: [],
    tier2_seed_instruments: [],
  },
  screening: [],
};

export const EMPTY_DASHBOARD_SNAPSHOT: DashboardSnapshot = {
  dailyPnl: null,
  dailyPnlPercent: null,
  openRisk: 0,
  winRate: null,
  riskReward: null,
  brokerInfo: null,
  runningStrategies: [],
};

export const EMPTY_ALLOCATION_DRIFT_SUMMARY: AllocationDriftSummary = {
  window_minutes: 0,
  drift_warning_percent: 0,
  drift_critical_percent: 0,
  material_drift_count: 0,
  worst_intents: [],
  by_strategy: [],
  by_family: [],
  by_instrument: [],
};

export const EMPTY_ALLOCATION_EXPOSURE_SUMMARY: AllocationExposureSummary = {
  totals: {
    reserved_risk_percent: 0,
    live_risk_percent: 0,
    provisional_live_risk_percent: 0,
    reserved_risk_amount: 0,
    live_risk_amount: 0,
    provisional_live_risk_amount: 0,
    reserved_intent_count: 0,
    open_position_count: 0,
    remaining_portfolio_risk_percent: 0,
  },
  by_strategy: [],
  by_family: [],
  by_instrument: [],
  by_currency: [],
  currency_directional: [],
  hotspots: [],
  notes: {},
};

export const EMPTY_MARKET_CATALOGUE: MarketCatalogueResponse = {
  generated_at: new Date(0).toISOString(),
  instruments: [],
  summary: {
    total_count: 0,
    shortlisted_count: 0,
    strategy_watchlist_count: 0,
    streaming_count: 0,
  },
};

export const EMPTY_STRATEGY_WATCHLIST: StrategyWatchlistResponse = {
  generated_at: new Date(0).toISOString(),
  limit: 0,
  active_count: 0,
  streaming_count: 0,
  protective_count: 0,
  cap_exceeded_by_protective_coverage: false,
  instruments: [],
};

export const EMPTY_FEED_STATE_RESPONSE: FeedStateResponse = {
  generated_at: new Date(0).toISOString(),
  instruments: [],
};

type BackendMode = "live";

export type LoadResult<T> = {
  data: T;
  error: string | null;
};

class HttpError extends Error {
  status: number;
  detail?: string;

  constructor(status: number, detail?: string) {
    super(detail ?? `Request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function fetchWithTimeout(input: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  return fetch(input, {
    ...init,
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}${path}`,
    {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    },
    init?.timeoutMs,
  );

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = undefined;
    }
    throw new HttpError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export async function getBackendMode(): Promise<BackendMode> {
  return "live";
}

export async function getTrades(): Promise<Trade[]> {
  return request<Trade[]>("/trades");
}

export async function getExecutions(limit = 100): Promise<Execution[]> {
  return request<Execution[]>(`/executions?limit=${limit}`);
}

export async function getOpenPositions(): Promise<Position[]> {
  return request<Position[]>("/trades/positions");
}

export async function getBrokerAuthStatus(): Promise<BrokerAuthStatus> {
  try {
    const telemetry = await getOperationalTelemetry();
    return {
      state: telemetry.broker_connected ? "connected" : "disconnected",
      label: telemetry.broker_connected ? "IG Connected" : "IG Disconnected",
      detail: telemetry.broker_connected
        ? telemetry.broker_latency_ms != null
          ? `Connectivity derived from system telemetry · ${telemetry.broker_latency_ms.toFixed(0)}ms`
          : "Connectivity derived from system telemetry"
        : telemetry.broker_connectivity_state === "DISCONNECTED"
          ? "Broker connectivity is currently unavailable according to system telemetry."
          : "Broker state could not be confirmed.",
      position_count: 0,
    };
  } catch (error) {
    const detail = error instanceof HttpError ? error.detail : error instanceof Error ? error.message : undefined;
    return {
      state: "unavailable",
      label: "IG Unavailable",
      detail: detail ?? "Broker authentication check failed",
      position_count: 0,
    };
  }
}

export async function getStreamHealth(): Promise<StreamHealthStatus> {
  return request<StreamHealthStatus>("/health/stream");
}

export async function getCoverageSummary(): Promise<CoverageSummary> {
  return request<CoverageSummary>("/coverage/summary");
}

export async function getControlPlaneSummary(): Promise<ControlPlaneSummary> {
  return request<ControlPlaneSummary>("/control-plane/summary");
}

export async function getControlPlaneFamily(strategyName: string): Promise<ControlPlaneSummary["families"][number]> {
  return request<ControlPlaneSummary["families"][number]>(`/control-plane/strategies/${strategyName}`);
}

export async function getOperatorControlState(): Promise<OperatorControlState> {
  return request<OperatorControlState>("/control-plane/operator-state");
}

export async function updateOperatorControlState(
  payload: { autonomous_control_enabled?: boolean | null; reason?: string | null },
): Promise<OperatorControlState> {
  return request<OperatorControlState>("/control-plane/operator-state", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function updateStrategyGovernance(
  strategyName: string,
  payload: {
    approval_state?: string | null;
    autonomous_operation_allowed?: boolean | null;
    emergency_stop?: boolean | null;
    approved_asset_classes?: string[] | null;
    approved_instruments?: string[] | null;
    approved_profile_names?: string[] | null;
    max_concurrent_deployments?: number | null;
    notes?: string | null;
  },
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/control-plane/governance/${strategyName}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getOperationalTelemetry(): Promise<OperationalTelemetry> {
  return request<OperationalTelemetry>("/system/telemetry");
}

export async function getSystemOperatingLimits(): Promise<SystemOperatingLimits> {
  return request<SystemOperatingLimits>("/system/limits");
}

export async function getAllocationCycles(limit = 25): Promise<AllocationCycle[]> {
  return request<AllocationCycle[]>(`/allocation/cycles?limit=${limit}`);
}

export async function getAllocationCycle(cycleId: string): Promise<AllocationCycle> {
  return request<AllocationCycle>(`/allocation/cycles/${cycleId}`);
}

export async function getAllocationIntents(params?: {
  limit?: number;
  cycleId?: string;
  strategyName?: string;
  instrument?: string;
  state?: string[];
}): Promise<AllocationIntent[]> {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.cycleId) {
    query.set("cycle_id", params.cycleId);
  }
  if (params?.strategyName) {
    query.set("strategy_name", params.strategyName);
  }
  if (params?.instrument) {
    query.set("instrument", params.instrument);
  }
  params?.state?.forEach((value) => query.append("state", value));
  const suffix = query.toString();
  return request<AllocationIntent[]>(`/allocation/intents${suffix ? `?${suffix}` : ""}`);
}

export async function getAllocationIntent(tradeIntentId: number): Promise<AllocationIntent> {
  return request<AllocationIntent>(`/allocation/intents/${tradeIntentId}`);
}

export async function getAllocationDriftSummary(params?: {
  limit?: number;
  windowMinutes?: number;
}): Promise<AllocationDriftSummary> {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.windowMinutes) {
    query.set("window_minutes", String(params.windowMinutes));
  }
  const suffix = query.toString();
  return request<AllocationDriftSummary>(`/allocation/drift${suffix ? `?${suffix}` : ""}`);
}

export async function getAllocationAlerts(params?: {
  limit?: number;
  windowMinutes?: number;
  includeResolved?: boolean;
  refresh?: boolean;
}): Promise<AllocationAlert[]> {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.windowMinutes) {
    query.set("window_minutes", String(params.windowMinutes));
  }
  if (typeof params?.includeResolved === "boolean") {
    query.set("include_resolved", String(params.includeResolved));
  }
  if (typeof params?.refresh === "boolean") {
    query.set("refresh", String(params.refresh));
  }
  const suffix = query.toString();
  return request<AllocationAlert[]>(`/allocation/alerts${suffix ? `?${suffix}` : ""}`);
}

export async function getUnresolvedCriticalAllocationAlerts(limit = 25): Promise<AllocationAlert[]> {
  return request<AllocationAlert[]>(`/allocation/alerts/unresolved-critical?limit=${limit}`);
}

export async function acknowledgeAllocationAlert(alertId: number, actorId = "operator"): Promise<{ id: number; state: string; acknowledged_at?: string | null }> {
  return request<{ id: number; state: string; acknowledged_at?: string | null }>(`/allocation/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ actor_id: actorId }),
  });
}

export async function resolveAllocationAlert(alertId: number, actorId = "operator"): Promise<{ id: number; state: string; resolved_at?: string | null }> {
  return request<{ id: number; state: string; resolved_at?: string | null }>(`/allocation/alerts/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ actor_id: actorId }),
  });
}

export async function getAllocationExposureSummary(): Promise<AllocationExposureSummary> {
  return request<AllocationExposureSummary>("/allocation/exposure");
}

export async function withFallback<T>(loader: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader();
  } catch {
    return fallback;
  }
}

export async function loadWithMeta<T>(loader: () => Promise<T>, fallback: T): Promise<LoadResult<T>> {
  try {
    return {
      data: await loader(),
      error: null,
    };
  } catch (error) {
    const message = error instanceof HttpError ? error.detail ?? error.message : error instanceof Error ? error.message : "Request failed";
    return {
      data: fallback,
      error: message,
    };
  }
}

export async function getDomainEvents(params?: {
  limit?: number;
  eventType?: string;
  errorType?: string;
  category?: string;
  severity?: string;
  strategyName?: string;
  instrument?: string;
  correlationId?: string;
  since?: string;
  until?: string;
}): Promise<DomainEvent[]> {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.eventType) {
    query.set("event_type", params.eventType);
  }
  if (params?.errorType) {
    query.set("error_type", params.errorType);
  }
  if (params?.category) {
    query.set("category", params.category);
  }
  if (params?.severity) {
    query.set("severity", params.severity);
  }
  if (params?.strategyName) {
    query.set("strategy_name", params.strategyName);
  }
  if (params?.instrument) {
    query.set("instrument", params.instrument);
  }
  if (params?.correlationId) {
    query.set("correlation_id", params.correlationId);
  }
  if (params?.since) {
    query.set("since", params.since);
  }
  if (params?.until) {
    query.set("until", params.until);
  }
  const suffix = query.toString();
  return request<DomainEvent[]>(`/events${suffix ? `?${suffix}` : ""}`);
}

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  return request<DashboardSnapshot>("/dashboard");
}

export async function getStrategies(): Promise<StrategyDefinition[]> {
  return request<StrategyDefinition[]>("/strategies");
}

export async function getMarketOverview(category: MarketCategory = "forex"): Promise<MarketCategoryOverviewResponse> {
  return request<MarketCategoryOverviewResponse>(`/markets/overview?category=${category}`, {
    timeoutMs: MARKET_REQUEST_TIMEOUT_MS,
  });
}

export async function getMarketCatalogue(): Promise<MarketCatalogueResponse> {
  return request<MarketCatalogueResponse>("/markets/catalogue", {
    timeoutMs: MARKET_REQUEST_TIMEOUT_MS,
  });
}

export async function addShortlistInstrument(instrumentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/watchlist/shortlist/${encodeURIComponent(instrumentId)}`, {
    method: "POST",
  });
}

export async function removeShortlistInstrument(instrumentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/watchlist/shortlist/${encodeURIComponent(instrumentId)}`, {
    method: "DELETE",
  });
}

export async function addStrategyWatchlistInstruments(instrumentIds: string[]): Promise<StrategyWatchlistBulkResult> {
  return request<StrategyWatchlistBulkResult>("/strategy-watchlist/bulk", {
    method: "POST",
    body: JSON.stringify({ instrument_ids: instrumentIds }),
  });
}

export async function getStrategyWatchlist(): Promise<StrategyWatchlistResponse> {
  return request<StrategyWatchlistResponse>("/strategy-watchlist");
}

export async function removeStrategyWatchlistInstrument(instrumentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/strategy-watchlist/${encodeURIComponent(instrumentId)}`, {
    method: "DELETE",
  });
}

export async function getFeedState(): Promise<FeedStateResponse> {
  return request<FeedStateResponse>("/market-data/feed-state");
}

export async function getInstrumentFeedState(instrumentId: string): Promise<FeedState> {
  return request<FeedState>(`/market-data/feed-state/${encodeURIComponent(instrumentId)}`);
}

export async function getLiveInstrumentChart(instrumentId: string, timeframe = "1m"): Promise<LiveChartResponse> {
  return request<LiveChartResponse>(`/live/instruments/${encodeURIComponent(instrumentId)}/chart?timeframe=${encodeURIComponent(timeframe)}`, {
    timeoutMs: MARKET_REQUEST_TIMEOUT_MS,
  });
}

export async function startStrategy(strategyName: string, instrument: string): Promise<{ status: string }> {
  return request<{ status: string }>("/strategy/start", {
    method: "POST",
    body: JSON.stringify({
      strategy_name: strategyName,
      instrument,
    }),
  });
}

export async function stopStrategy(params: { instrument?: string; strategyName?: string }): Promise<{ status: string }> {
  return request<{ status: string }>("/strategy/stop", {
    method: "POST",
    body: JSON.stringify({
      instrument: params.instrument,
      strategy_name: params.strategyName,
    }),
  });
}

export async function getOperatorSummaryReview(): Promise<OperatorSummaryReview> {
  return request<OperatorSummaryReview>("/reviews/operator-summary", {
    timeoutMs: 3000,
  });
}

export async function getReviewHistory(reviewType?: string, limit = 8): Promise<ReviewHistoryItem[]> {
  const query = new URLSearchParams();
  if (reviewType) {
    query.set("review_type", reviewType);
  }
  query.set("limit", String(limit));
  return request<ReviewHistoryItem[]>(`/reviews/history?${query.toString()}`, {
    timeoutMs: 3000,
  });
}

export async function askOperationalQuestion(payload: {
  question: string;
  strategyName?: string | null;
}): Promise<OperationalQuestionReviewResponse> {
  return request<OperationalQuestionReviewResponse>("/reviews/questions", {
    method: "POST",
    body: JSON.stringify({
      question: payload.question,
      strategy_name: payload.strategyName ?? null,
    }),
    timeoutMs: 5000,
  });
}

export async function getAimeeSnapshot(): Promise<AimeeSnapshotResponse> {
  return request<AimeeSnapshotResponse>("/aimee/snapshot", {
    timeoutMs: 5000,
  });
}

export async function resetTestHistory(): Promise<{
  status: string;
  summary: Record<string, number>;
}> {
  return request<{ status: string; summary: Record<string, number> }>("/testing/reset-history", {
    method: "POST",
  });
}
