export type BrokerExecutionSource =
  | "BROKER_CONFIRMED"
  | "SIMULATED_LOCAL_FILL"
  | "SIMULATED_LOCAL_CLOSE";

export type BrokerSyncStatus =
  | "CONFIRMED"
  | "PENDING"
  | "MISSING_AT_BROKER"
  | "UNKNOWN"
  | "UNAVAILABLE"
  | "SIMULATED_LOCAL_FILL"
  | "SIMULATED_LOCAL_CLOSE";

export type ExecutionStatus =
  | "SUBMISSION_PENDING"
  | "SIGNAL_GENERATED"
  | "RISK_APPROVED"
  | "RISK_REJECTED"
  | "ORDER_SUBMITTED"
  | "ORDER_ACKNOWLEDGED"
  | "FILL_PARTIAL"
  | "FILL_FULL"
  | "POSITION_OPENED"
  | "CLOSE_REQUESTED"
  | "CLOSE_CONFIRMED"
  | "FAILED"
  | "CANCELLED"
  | "NEEDS_MANUAL_REVIEW";

export type TradeIntentState =
  | "PROPOSED"
  | "REJECTED"
  | "APPROVED"
  | "SUBMITTED"
  | "ACKNOWLEDGED"
  | "PARTIALLY_FILLED"
  | "FILLED"
  | "POSITION_OPENED"
  | "CLOSE_REQUESTED"
  | "CLOSED"
  | "FAILED"
  | "CANCELLED"
  | "EXTERNAL_POSITION_ADOPTED"
  | "RECOVERED_POSITION_ATTACHED"
  | "FORCED_RECONCILIATION_CLOSE";

export type SafeIdentifier = {
  display: string;
  fingerprint: string;
};

export type Trade = {
  id: number;
  strategy_name: string;
  broker_reference?: SafeIdentifier | string | null;
  close_broker_reference?: SafeIdentifier | string | null;
  close_execution_source?: BrokerExecutionSource | string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  close_price: number;
  open_time: string;
  close_time: string;
  pnl: number;
  account_type: "DEMO" | "LIVE";
  entry_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | string | null;
  r_multiple?: number | null;
  reason?: string | null;
  outcome?: string | null;
};

export type Execution = {
  id: number;
  trade_intent_id?: number | null;
  strategy_name: string;
  instrument: string;
  phase: "ENTRY" | "CLOSE";
  status: ExecutionStatus | string;
  client_request_id?: SafeIdentifier | string | null;
  broker_reference?: SafeIdentifier | string | null;
  local_position_id?: number | null;
  local_trade_id?: number | null;
  signal_time: string;
  submitted_at?: string | null;
  acknowledged_at?: string | null;
  completed_at?: string | null;
  last_transition_at: string;
  requested_size?: number | null;
  filled_size?: number | null;
  requested_price?: number | null;
  average_fill_price?: number | null;
  intended_risk_amount?: number | null;
  submitted_risk_amount?: number | null;
  fill_derived_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | string | null;
  risk_reconciliation?: Record<string, unknown> | null;
  material_execution_drift: boolean;
  critical_execution_drift: boolean;
  reason?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  requires_manual_review: boolean;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Position = {
  id: number;
  strategy_name: string;
  broker_reference?: SafeIdentifier | string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  close_price?: number | null;
  open_time: string;
  close_time?: string | null;
  pnl?: number | null;
  account_type: "DEMO" | "LIVE";
  is_open: boolean;
  current_price?: number | null;
  unrealized_pnl?: number | null;
  risk_percent?: number | null;
  entry_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | string | null;
  broker_sync_status?: BrokerSyncStatus | string | null;
  close_execution_source?: BrokerExecutionSource | string | null;
  reason?: string | null;
  manual_override?: boolean;
  time_in_trade_seconds?: number;
};

export type StrategyParameter = {
  key: string;
  label: string;
  value: number;
  step?: number;
};

export type StrategyRuntime = {
  strategy_name: string;
  instrument: string;
  runtime_key: string;
  has_open_position: boolean;
  broker_reference?: SafeIdentifier | string | null;
  direction?: "BUY" | "SELL" | null;
  current_price?: number | null;
  unrealized_pnl?: number | null;
  recovery_state?: string | null;
  runtime_mode?: "NORMAL" | "EXITS_ONLY" | "STOPPED" | string | null;
  control_mode?: "MANUAL" | "AUTO" | string | null;
  deployment_id?: number | null;
  recovery_reason?: string | null;
};

export type StrategyPositionSummary = {
  broker_reference?: SafeIdentifier | string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  current_price?: number | null;
  unrealized_pnl?: number | null;
  risk_percent?: number | null;
};

export type StrategyDefinition = {
  name: string;
  description: string;
  instrument: string;
  status: "RUNNING" | "STOPPED";
  current_pnl: number;
  last_price?: number | null;
  price_status?: "STOPPED" | "LIVE" | "POLLED" | "CACHED" | "STALE" | "POSITION" | "REST" | "ERROR";
  price_error?: string | null;
  last_price_updated_at?: string | null;
  trade_count: number;
  win_rate: number;
  account_type: "DEMO" | "LIVE";
  position_size: number;
  risk_per_trade: number;
  supported_asset_classes?: string[];
  available_profiles?: string[];
  governance_approval_state?: string;
  autonomous_operation_allowed?: boolean;
  emergency_stop?: boolean;
  deployment_state?: string;
  deployment_profile?: string | null;
  deployment_parameters?: Record<string, number>;
  deployment_instrument?: string | null;
  deployment_reason?: string | null;
  active_instruments?: string[];
  authorized?: boolean;
  evaluating_instrument_count?: number;
  candidates_generated_today?: number;
  candidates_promoted_today?: number;
  candidates_blocked_today?: number;
  active_runtime_count?: number;
  open_position_count?: number;
  warning_message?: string | null;
  warning_instrument?: string | null;
  warning_status?: string | null;
  active_runtimes?: StrategyRuntime[];
  open_positions?: StrategyPositionSummary[];
  persisted_runtimes?: Array<{
    runtime_id: SafeIdentifier | string;
    instrument: string;
    status: string;
    recovery_state?: string | null;
    recovery_reason?: string | null;
    last_heartbeat_at?: string | null;
    last_price_seen?: number | null;
    last_price_seen_at?: string | null;
    control_mode?: "MANUAL" | "AUTO" | string | null;
    runtime_mode?: "NORMAL" | "EXITS_ONLY" | "STOPPED" | string | null;
    deployment_id?: number | null;
    active_profile_name?: string | null;
    parameters: Record<string, number>;
    auto_resume?: boolean | null;
  }>;
  instrument_options?: { epic: string; label: string; category: string }[];
  parameters: StrategyParameter[];
};

export type StrategyMutationStatus = {
  status: "started" | "stopped";
  strategy?: string | null;
  instrument?: string | null;
};

export type StrategyGovernanceMutationResponse = {
  strategy_name: string;
  approval_state: string;
  autonomous_operation_allowed: boolean;
  emergency_stop: boolean;
  approved_asset_classes: string[];
  approved_instruments: string[];
  approved_profile_names: string[];
  max_concurrent_deployments: number;
  notes?: string | null;
  updated_at: string;
};

export type MarketCatalogueInstrument = {
  id: string;
  instrument: string;
  name: string;
  symbol: string;
  asset_class: string;
  category: string;
  currency?: string | null;
  base_currency?: string | null;
  quote_currency?: string | null;
  forex_major: boolean;
  tradable: boolean;
  shortlisted: boolean;
  in_strategy_watchlist: boolean;
  streaming_now: boolean;
  activity_level: ActivityLevel;
  strategy_compatibility: string[];
  reference_price?: number | null;
  shortlisted_at?: string | null;
  note?: string | null;
};

export type OperatorReason = {
  code: string;
  label: string;
  operator_action: string;
  components?: OperatorReason[];
};

export type MarketCatalogueResponse = {
  generated_at: string;
  instruments: MarketCatalogueInstrument[];
  summary: {
    total_count: number;
    shortlisted_count: number;
    strategy_watchlist_count: number;
    streaming_count: number;
  };
};

export type ShortlistResponse = {
  generated_at: string;
  instruments: MarketCatalogueInstrument[];
  count: number;
};

export type ShortlistMutationResponse = {
  status: "shortlisted" | "removed";
  instrument: MarketCatalogueInstrument | string;
};

export type StrategyWatchlistEntry = CoverageWatchlistEntry;

export type StrategyWatchlistResponse = {
  generated_at: string;
  limit: number;
  active_count: number;
  normal_count?: number;
  streaming_count: number;
  protective_count?: number;
  cap_exceeded_by_protective_coverage?: boolean;
  instruments: StrategyWatchlistEntry[];
};

export type StrategyWatchlistBulkResult = {
  added: Array<{ instrument: string; reason: string; reason_detail?: OperatorReason }>;
  skipped: Array<{ instrument: string; reason: string; reason_detail?: OperatorReason }>;
  limit: number;
};

export type StrategyWatchlistMutationResponse = {
  status: "removed";
  instrument: string;
};

export type FeedMarketStatus = {
  instrument: string;
  is_ok: boolean;
  market_open: boolean;
  tradable: boolean;
  quote_fresh: boolean;
  spread_ok: boolean;
  session_valid: boolean;
  dealing_allowed: boolean;
  last_price_age_ms: number;
  spread?: number | null;
  reason?: string | null;
};

export type FeedState = {
  instrument: string;
  stream_status: "streaming" | "stale" | "desired" | "capped" | "inactive";
  stream_connected: boolean;
  stream_enabled: boolean;
  streaming_now: boolean;
  desired: boolean;
  capped: boolean;
  last_tick_at?: string | null;
  last_tick_age_ms?: number | null;
  spread?: number | null;
  price_source: "STREAM" | "SNAPSHOT" | "STALE" | "UNAVAILABLE";
  stream_reason?: OperatorReason;
  market_status?: FeedMarketStatus | null;
  market_error?: string | null;
  entry_eligibility: string;
  entry_eligibility_reason?: OperatorReason;
  strategies_may_evaluate: boolean;
  active_strategy_runtime_count: number;
  watchlist_entry?: StrategyWatchlistEntry | null;
};

export type FeedStateResponse = {
  generated_at: string;
  instruments: FeedState[];
};

export type LiveChartResponse = {
  instrument: string;
  timeframe: string;
  source: "STREAM" | "REST_CANDLES" | "SNAPSHOT" | "FALLBACK" | "STALE" | "UNAVAILABLE";
  data_state: "READY" | "EMPTY" | "UNSUPPORTED";
  reason_detail?: OperatorReason | null;
  candles: Array<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
    source?: "STREAM" | "REST_CANDLES" | "SNAPSHOT" | "FALLBACK" | "STALE" | "UNAVAILABLE";
  }>;
  markers: Array<Record<string, unknown>>;
  position_overlays: Array<Record<string, unknown>>;
  intent_markers: Array<Record<string, unknown>>;
  execution_markers: Array<Record<string, unknown>>;
  feed_state: FeedState;
};

export type BrokerAuthStatus = {
  state: "connected" | "disconnected" | "unavailable";
  label: string;
  detail: string;
  position_count: number;
};

export type StreamHealthStatus = {
  enabled: boolean;
  connected: boolean;
  dependency_ready: boolean;
  subscribed_instruments: string[];
  last_tick_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
};

export type CoverageWatchlistEntry = {
  instrument: string;
  tier: "TIER1" | "TIER2" | "TIER3";
  status: "ACTIVE" | "COOLDOWN" | "INACTIVE";
  asset_class?: string | null;
  pinned: boolean;
  reason?: string | null;
  reason_detail?: OperatorReason | null;
  protective?: boolean;
  priority_score: number;
  requested_frequency?: string | null;
  promotion_expires_at?: string | null;
  last_streamed_at?: string | null;
  last_refreshed_at?: string | null;
  streamed: boolean;
};

export type CoveragePromotionRequest = {
  id?: number | null;
  instrument: string;
  source: string;
  reason: string;
  score: number;
  status: "PENDING" | "ACCEPTED" | "REJECTED" | "EXPIRED";
  requested_at: string;
  expires_at?: string | null;
  market_status?: string | null;
  tradable?: boolean | null;
  requested_frequency?: string | null;
  updated_at: string;
};

export type ControlPlaneFamily = {
  strategy_name: string;
  description: string;
  supported_asset_classes: string[];
  available_profile_names: string[];
  governance: {
    approval_state: string;
    autonomous_operation_allowed: boolean;
    emergency_stop: boolean;
    approved_asset_classes: string[];
    approved_instruments: string[];
    approved_profile_names: string[];
    supported_asset_classes: string[];
    available_profile_names: string[];
    max_concurrent_deployments?: number | null;
    notes?: string | null;
    updated_at?: string | null;
  };
  deployment: {
    state: string;
    open_risk_management_state?: string | null;
    open_risk_management_reason?: string | null;
    selected_profile?: string | null;
    selected_profile_parameters: Record<string, number>;
    selected_instrument?: string | null;
    selected_asset_class?: string | null;
    suitability_score?: number | null;
    suitability_reason?: string | null;
    profile_selected_at?: string | null;
    profile_change_reason?: string | null;
    last_restart_reason?: string | null;
    blocked_reason?: string | null;
    degraded_reason?: string | null;
    last_evaluated_at?: string | null;
    last_deployed_at?: string | null;
    updated_at?: string | null;
  } | null;
  runtime: {
    is_running: boolean;
    active_runtime_id?: SafeIdentifier | string | null;
    active_instrument?: string | null;
    active_profile_name?: string | null;
    active_parameters: Record<string, number>;
    control_mode?: string | null;
    runtime_mode?: "NORMAL" | "EXITS_ONLY" | "STOPPED" | string | null;
    recovery_state?: string | null;
    updated_at?: string | null;
    persisted_runtimes: Array<{
      runtime_id: SafeIdentifier | string;
      status: string;
      instrument: string;
      control_mode?: string | null;
      runtime_mode?: "NORMAL" | "EXITS_ONLY" | "STOPPED" | string | null;
      active_profile_name?: string | null;
      parameters: Record<string, number>;
      updated_at?: string | null;
    }>;
  };
  alignment: {
    is_aligned: boolean | null;
    status: string;
    reason: string;
    checks: Array<{
      code: string;
      passed: boolean;
      expected?: unknown;
      actual?: unknown;
    }>;
  };
  recent_events: Array<{
    id?: number | null;
    created_at: string;
    event_type: string;
    title: string;
    message?: string | null;
    severity: string;
    payload_json: Record<string, unknown>;
  }>;
};

export type ControlPlaneSummary = {
  autonomous_control_enabled: boolean;
  configured_autonomous_control_enabled: boolean;
  effective_autonomous_control_enabled: boolean;
  autonomy_override_active: boolean;
  autonomy_override_value?: boolean | null;
  autonomy_override_reason?: string | null;
  autonomy_updated_at?: string | null;
  feed_source_state?: "LIVE" | "POLLING_FALLBACK" | "STALE" | "DISCONNECTED";
  feed_health_state?: "HEALTHY" | "DEGRADED" | "FAILED";
  broker_connectivity_state?: "CONNECTED" | "DISCONNECTED";
  entry_eligible?: boolean;
  exit_eligible?: boolean;
  entry_eligibility_state?: string | null;
  exit_eligibility_state?: string | null;
  entry_block_reason?: string | null;
  exit_block_reason?: string | null;
  open_risk_management_state?: string;
  open_risk_management_reason?: string | null;
  counts: Record<string, number>;
  misaligned_count: number;
  families: ControlPlaneFamily[];
};

export type OperatorControlState = {
  configured_autonomous_control_enabled: boolean;
  effective_autonomous_control_enabled: boolean;
  override_active: boolean;
  override_value?: boolean | null;
  override_reason?: string | null;
  updated_at?: string | null;
};

export type TradeAllocatorDecisionSummary = {
  id?: number | null;
  created_at: string;
  event_type: string;
  selected: boolean;
  strategy_name?: string | null;
  instrument?: string | null;
  reason_code?: string | null;
  reason?: string | null;
  score?: number | null;
  direction?: "BUY" | "SELL" | null;
  source_tier?: string | null;
};

export type CoverageSummary = {
  streaming: {
    active_instruments: CoverageWatchlistEntry[];
    execution_readiness: Array<{
      instrument: string;
      is_ok: boolean;
      market_open: boolean;
      tradable: boolean;
      quote_fresh: boolean;
      spread_ok: boolean;
      session_valid: boolean;
      dealing_allowed: boolean;
      last_price_age_ms: number;
      spread?: number | null;
      reason?: string | null;
    }>;
    desired_instruments: string[];
    pinned_instruments: string[];
    capped_instruments: string[];
    asset_class_usage: Record<string, number>;
  };
  tier2: {
    refresh_queue: string[];
    active_candidates: CoverageWatchlistEntry[];
  };
  promotions: {
    pending_count: number;
    accepted_count: number;
    rejected_count: number;
    expired_count: number;
    recent_requests: CoveragePromotionRequest[];
  };
  trade_allocator: {
    selected_count: number;
    rejected_count: number;
    reason_counts: Record<string, number>;
    recent_decisions: TradeAllocatorDecisionSummary[];
  };
};

export type OperationalTelemetry = {
  status: string;
  last_heartbeat: string;
  heartbeat_age_ms?: number | null;
  last_price_update?: string | null;
  last_price_age_ms?: number | null;
  last_reconciliation?: string | null;
  last_reconciliation_age_ms?: number | null;
  last_audit_write_failure?: string | null;
  last_audit_write_failure_age_ms?: number | null;
  stream_connected: boolean;
  stream_last_tick_at?: string | null;
  stream_last_tick_age_ms?: number | null;
  subscribed_instrument_count: number;
  desired_instrument_count: number;
  broker_connected: boolean;
  feed_source_state?: "LIVE" | "POLLING_FALLBACK" | "STALE" | "DISCONNECTED";
  feed_health_state?: "HEALTHY" | "DEGRADED" | "FAILED";
  broker_connectivity_state?: "CONNECTED" | "DISCONNECTED";
  entry_eligible?: boolean;
  exit_eligible?: boolean;
  entry_block_reason?: string | null;
  exit_block_reason?: string | null;
  open_risk_management_state?: string;
  open_risk_management_reason?: string | null;
  audit_write_degraded?: boolean;
  polling_fallback_active?: boolean;
  polling_fallback_active_instrument_count?: number;
  stale_stream_instrument_count?: number;
  stream_degraded?: boolean;
  runtime_degraded?: boolean;
  degradation_reasons?: string[];
  broker_latency_ms?: number | null;
  runtime_count: number;
  active_runtime_count: number;
  stale_runtime_count: number;
  stale_price_runtime_count: number;
  reconciliation_mismatches: number;
  order_failures_last_5m: number;
  rejected_orders_last_5m: number;
  audit_write_failures_last_5m?: number;
  strategies_paused_by_health: number;
};

export type ScreeningStrategyLimit = {
  name: string;
  description: string;
  promotion_threshold: number;
  refresh_tier: string;
};

export type SystemOperatingLimits = {
  autonomous_control_enabled: boolean;
  risk: {
    max_open_positions: number;
    max_positions_per_strategy: number;
    max_open_risk_percent: number;
    daily_loss_limit: number;
    max_position_notional: number;
    max_unhealthy_runtimes: number;
    global_entry_kill_switch: boolean;
  };
  execution: {
    max_price_age_ms: number;
    max_spread_pips: number;
    max_spread_percent_of_price: number;
    entry_burst_limit: number;
    entry_burst_window_seconds: number;
    failed_entry_retry_cooldown_seconds: number;
    duplicate_signal_window_seconds: number;
    cooldown_after_loss_seconds: number;
    cooldown_after_exit_seconds: number;
    allocator_enabled: boolean;
    allocator_max_decisions_per_cycle: number;
    allocator_max_open_positions_per_instrument: number;
    allocator_signal_stale_after_seconds: number;
  };
  coverage: {
    streaming_enabled: boolean;
    max_instruments: number;
    requested_frequency: string;
    max_promotions_per_minute: number;
    max_subscription_churn_per_minute: number;
    promotion_score_threshold: number;
    eviction_score_threshold: number;
    min_tier1_residency_seconds: number;
    demotion_cooldown_seconds: number;
    tier2_refresh_enabled: boolean;
    tier2_refresh_interval_seconds: number;
    tier2_refresh_batch_size: number;
    tier2_refresh_stale_after_seconds: number;
    tier2_promotion_score_threshold: number;
    tier2_promotion_ttl_seconds: number;
    asset_class_slot_budgets: Record<string, number>;
    seed_instruments: string[];
    tier2_seed_instruments: string[];
  };
  screening: ScreeningStrategyLimit[];
};

export type DomainEvent = {
  id: number;
  created_at: string;
  event_type: string;
  category: string;
  severity: string;
  error_type?: string | null;
  source: string;
  correlation_id?: SafeIdentifier | string | null;
  runtime_id?: SafeIdentifier | string | null;
  strategy_name?: string | null;
  instrument?: string | null;
  position_id?: number | null;
  trade_id?: number | null;
  execution_id?: number | null;
  actor_type?: string | null;
  actor_id?: string | null;
  title: string;
  message?: string | null;
  payload_json: Record<string, unknown>;
};

export type DashboardSnapshot = {
  accountValue?: number | null;
  accountValuePercent?: number | null;
  dailyPnl?: number | null;
  dailyPnlPercent?: number | null;
  openRisk: number;
  winRate?: number | null;
  riskReward?: number | null;
  brokerInfo?: {
    accountId: SafeIdentifier | string;
    accountType: "DEMO" | "LIVE";
    balance: number;
    available: number;
    equity: number;
    profitLoss: number;
  } | null;
  runningStrategies?: {
    name: string;
    instrument: string;
    instrumentLabel: string;
    runtimeKey?: string;
    brokerReference?: SafeIdentifier | string | null;
    hasOpenPosition?: boolean;
    lastPrice?: number | null;
  }[];
};

export type MarketCategory = "forex" | "indices" | "commodities" | "stocks" | "crypto";

export type MarketStatus = "OPEN" | "CLOSED" | "LIMITED" | "UNAVAILABLE";

export type ActivityLevel = "LOW" | "MEDIUM" | "HIGH";

export type MarketInstrument = {
  id: string;
  category: MarketCategory;
  name: string;
  symbol: string;
  status: MarketStatus;
  tradable: boolean;
  active: boolean;
  activityLevel: ActivityLevel;
  strategyCompatibility: string[];
  price: number;
  changePercent: number;
  sessionNote?: string;
};

export type MarketSummary = {
  category: MarketCategory;
  label: string;
  description: string;
  status: MarketStatus;
  headline: string;
  detail: string;
  nextTransitionAt: string;
  nextTransitionLabel: string;
  tradableCount: number;
  activeCount: number;
  totalCount: number;
};

export type MarketOverviewResponse = {
  generatedAt: string;
  summaries: MarketSummary[];
  instruments: Record<MarketCategory, MarketInstrument[]>;
};

export type MarketCategoryOverviewResponse = {
  generatedAt: string;
  summary: MarketSummary;
  instruments: MarketInstrument[];
};

export type ReviewObservation = {
  code: string;
  severity: "info" | "warning" | "critical";
  label: string;
  detail: string;
  confidence: number;
  rank: number;
  time_scope: string;
  supporting_metrics: Array<{
    key: string;
    label: string;
    value: number | string | null;
    unit?: string | null;
    baseline_value?: number | string | null;
    delta_value?: number | string | null;
  }>;
  entity_type?: string | null;
  entity_id?: string | null;
};

export type PossibleContributor = {
  code: string;
  label: string;
  detail: string;
  confidence: number;
  time_scope: string;
  related_observation_codes: string[];
  supporting_metrics: Array<{
    key: string;
    label: string;
    value: number | string | null;
    unit?: string | null;
    baseline_value?: number | string | null;
    delta_value?: number | string | null;
  }>;
};

export type ReviewWarning = {
  code: string;
  severity: "info" | "warning" | "critical";
  message: string;
};

export type SupportingMetric = {
  key: string;
  label: string;
  value: number | string | null;
  unit?: string | null;
  baseline_value?: number | string | null;
  delta_value?: number | string | null;
  trend: "up" | "down" | "flat" | "unknown";
  description?: string | null;
};

export type ReviewMetadata = {
  review_id?: number | null;
  review_type:
    | "operator_summary"
    | "daily_review"
    | "strategy_review"
    | "runtime_health_review"
    | "trade_postmortem"
    | "operational_question";
  generated_at: string;
  as_of: string;
  period_start?: string | null;
  period_end?: string | null;
  requested_date?: string | null;
  scope: Record<string, unknown>;
  source_coverage: {
    trades_available: boolean;
    positions_available: boolean;
    executions_available: boolean;
    runtimes_available: boolean;
    reconciliation_available: boolean;
    broker_summary_available: boolean;
    stream_health_available: boolean;
    coverage_notes: string[];
  };
  generation_mode: "deterministic_only" | "deterministic_plus_llm";
};

export type AIReviewSummary = {
  summary: string;
  notable_points: string[];
  operator_checks: string[];
};

export type OperatorSummaryReview = {
  metadata: ReviewMetadata;
  facts: {
    account_value?: number | null;
    account_value_change_percent?: number | null;
    daily_pnl: number;
    daily_pnl_percent?: number | null;
    open_risk_percent: number;
    open_positions_count: number;
    active_runtimes: number;
    main_open_risk?: {
      strategy_name: string;
      instrument: string;
      direction: string;
      risk_percent: number;
      unrealized_pnl?: number | null;
      notional_estimate?: number | null;
      share_of_open_risk_percent?: number | null;
    } | null;
    largest_risk_share_percent: number;
    top_risk_exposures: Array<{
      strategy_name: string;
      instrument: string;
      direction: string;
      risk_percent: number;
      unrealized_pnl?: number | null;
      notional_estimate?: number | null;
      share_of_open_risk_percent?: number | null;
    }>;
    strategy_health: Array<{
      strategy_name: string;
      status: string;
      active_runtime_count: number;
      open_position_count: number;
      trade_count_24h: number;
      pnl_24h: number;
      win_rate_24h?: number | null;
      stale_runtime_count: number;
    }>;
    risk_rejections_24h: number;
    execution_failures_24h: number;
    reconciliation_issues_24h: number;
    stale_runtimes: number;
    stream_connected?: boolean | null;
    stream_last_tick_at?: string | null;
    baseline_open_risk_percent?: number | null;
    baseline_largest_risk_share_percent?: number | null;
    baseline_trade_count_24h?: number | null;
    baseline_win_rate_24h?: number | null;
  };
  derived_observations: ReviewObservation[];
  possible_contributors: PossibleContributor[];
  warnings: ReviewWarning[];
  supporting_metrics: SupportingMetric[];
  ai_summary?: AIReviewSummary | null;
  provenance?: {
    llm_attempted: boolean;
    llm_provider?: string | null;
    llm_model?: string | null;
    prompt_version: string;
    generated_at?: string | null;
    prompt_facts: Record<string, unknown>;
    raw_response?: string | null;
  } | null;
};

export type ReviewHistoryItem = {
  review_id: number;
  review_type:
    | "operator_summary"
    | "daily_review"
    | "strategy_review"
    | "runtime_health_review"
    | "trade_postmortem"
    | "operational_question";
  generated_at: string;
  scope: Record<string, unknown>;
  generation_mode: "deterministic_only" | "deterministic_plus_llm";
  provider?: string | null;
  model?: string | null;
};

export type AimeeControlPlaneSummary = {
  effective_autonomous_control_enabled: boolean;
  configured_autonomous_control_enabled: boolean;
  autonomy_override_active: boolean;
  autonomy_override_value?: boolean | null;
  autonomy_override_reason?: string | null;
  autonomy_updated_at?: string | null;
  feed_source_state: string;
  feed_health_state: string;
  broker_connectivity_state: string;
  entry_eligible?: boolean;
  exit_eligible?: boolean;
  entry_block_reason?: string | null;
  exit_block_reason?: string | null;
  open_risk_management_state?: string | null;
  open_risk_management_reason?: string | null;
  misaligned_count: number;
  counts: Record<string, number>;
  families: Array<{
    strategy_name: string;
    deployment?: {
      state?: string | null;
      open_risk_management_state?: string | null;
      open_risk_management_reason?: string | null;
      blocked_reason?: string | null;
      degraded_reason?: string | null;
      selected_instrument?: string | null;
      selected_profile?: string | null;
      updated_at?: string | null;
    } | null;
    runtime: {
      is_running: boolean;
      active_instrument?: string | null;
      active_profile_name?: string | null;
      control_mode?: string | null;
      persisted_runtime_count: number;
    };
    alignment: {
      is_aligned?: boolean | null;
      reason: string;
    };
    governance: {
      approval_state: string;
      autonomous_operation_allowed: boolean;
      emergency_stop: boolean;
    };
  }>;
};

export type AimeeCoverageSummary = {
  streaming: {
    active_instruments: string[];
    desired_instruments: string[];
    pinned_instruments: string[];
    capped_instruments: string[];
    asset_class_usage: Record<string, number>;
  };
  promotions: {
    pending_count: number;
    accepted_count: number;
    rejected_count: number;
    expired_count: number;
  };
  trade_allocator: {
    selected_count: number;
    rejected_count: number;
    reason_counts: Record<string, number>;
  };
};

export type AimeeStrategySummary = {
  name: string;
  status: "RUNNING" | "STOPPED";
  warning_message?: string | null;
};

export type AimeeSnapshotResponse = {
  review: OperatorSummaryReview;
  history: ReviewHistoryItem[];
  controlPlane: AimeeControlPlaneSummary;
  coverage: AimeeCoverageSummary;
  telemetry: OperationalTelemetry;
  events: DomainEvent[];
  strategies: AimeeStrategySummary[];
  updatedAt: string;
};

export type OperationalQuestionReviewResponse = {
  metadata: ReviewMetadata;
  facts: {
    question: string;
    answer_type: string;
    routed_review_type: ReviewMetadata["review_type"];
    routed_scope: Record<string, unknown>;
    supporting_review: Record<string, unknown>;
  };
  derived_observations: ReviewObservation[];
  possible_contributors: PossibleContributor[];
  warnings: ReviewWarning[];
  supporting_metrics: SupportingMetric[];
  ai_summary?: AIReviewSummary | null;
  provenance?: {
    llm_attempted: boolean;
    llm_provider?: string | null;
    llm_model?: string | null;
    prompt_version: string;
    generated_at?: string | null;
    prompt_facts: Record<string, unknown>;
    raw_response?: string | null;
  } | null;
};

export type RiskTruthConfidence =
  | "EXACT_FILL_DERIVED"
  | "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
  | "PARTIAL_FILL_PROVISIONAL"
  | "SUBMITTED_EXECUTABLE_ESTIMATE"
  | "ALLOCATION_INTENT_ONLY"
  | "INCOMPLETE_DEGRADED"
  | "SIMULATED_LOCAL_FILL"
  | "UNKNOWN";

export type AllocationCycle = {
  cycle_id: string;
  received_at: string;
  completed_at: string;
  candidate_count: number;
  approved_count: number;
  rejected_count: number;
  total_requested_risk_percent: number;
  total_allocated_risk_percent: number;
  remaining_portfolio_risk_percent: number;
  resized_candidate_count: number;
  degraded_candidate_count: number;
  blocked_unsupported_sizing_count: number;
  blocked_approximate_live_count: number;
  blocked_under_minimum_size_count: number;
  blocked_budget_count: number;
  blocked_conflict_count: number;
  binding_budget_counts: Record<string, number>;
  rejection_reason_counts: Record<string, number>;
  details: Record<string, unknown>;
  intents?: AllocationIntent[];
};

export type AllocationIntentExecution = {
  id: number;
  phase: string;
  status: ExecutionStatus | string;
  client_request_id?: SafeIdentifier | string | null;
  broker_reference?: SafeIdentifier | string | null;
  submitted_at?: string | null;
  acknowledged_at?: string | null;
  completed_at?: string | null;
  requested_size?: number | null;
  filled_size?: number | null;
  requested_price?: number | null;
  average_fill_price?: number | null;
  intended_risk_amount?: number | null;
  submitted_risk_amount?: number | null;
  fill_derived_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | null;
  reason?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  requires_manual_review: boolean;
  details: Record<string, unknown>;
};

export type AllocationIntentPosition = {
  id: number;
  broker_reference?: SafeIdentifier | string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  current_price?: number | null;
  unrealized_pnl?: number | null;
  risk_percent?: number | null;
  entry_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | null;
  open_time: string;
  close_time?: string | null;
  is_open: boolean;
};

export type AllocationIntentTrade = {
  id: number;
  broker_reference?: SafeIdentifier | string | null;
  close_broker_reference?: SafeIdentifier | string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  close_price: number;
  pnl: number;
  entry_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | null;
  r_multiple?: number | null;
  open_time: string;
  close_time: string;
  reason?: string | null;
  outcome?: string | null;
};

export type AllocationIntent = {
  id: number;
  allocation_cycle_id?: string | null;
  strategy_name: string;
  family_name?: string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  state: TradeIntentState | string;
  signal_time: string;
  decision_reason_code?: string | null;
  decision_reason?: string | null;
  close_reason_code?: string | null;
  close_reason?: string | null;
  proposed_size?: number | null;
  allocated_size?: number | null;
  proposed_risk_percent?: number | null;
  allocated_risk_percent?: number | null;
  confidence?: number | null;
  estimated_risk_amount?: number | null;
  submitted_risk_amount?: number | null;
  fill_derived_risk_amount?: number | null;
  risk_truth_confidence?: RiskTruthConfidence | null;
  risk_currency?: string | null;
  allocation: Record<string, unknown>;
  allocation_outcome: Record<string, unknown>;
  risk_tracking: Record<string, unknown>;
  risk_reconciliation: Record<string, unknown>;
  latest_execution?: AllocationIntentExecution | null;
  executions: AllocationIntentExecution[];
  position?: AllocationIntentPosition | null;
  trade?: AllocationIntentTrade | null;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AllocationDriftIntentSummary = {
  trade_intent_id: number;
  strategy_name: string;
  family_name?: string | null;
  instrument: string;
  state: TradeIntentState | string;
  max_percent_drift: number;
  drift_metrics: Record<string, unknown>;
  updated_at: string;
};

export type AllocationDriftBucket = {
  name: string;
  count: number;
  average_percent_drift: number;
  max_percent_drift: number;
};

export type AllocationDriftSummary = {
  window_minutes: number;
  drift_warning_percent: number;
  drift_critical_percent: number;
  material_drift_count: number;
  worst_intents: AllocationDriftIntentSummary[];
  by_strategy: AllocationDriftBucket[];
  by_family: AllocationDriftBucket[];
  by_instrument: AllocationDriftBucket[];
};

export type AllocationAlertState = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
export type AllocationAlertSeverity = "info" | "warning" | "error";
export type AllocationAlertEscalationLevel = "none" | "warning" | "critical";

export type AllocationAlert = {
  id: number;
  alert_key: string;
  alert_type: string;
  severity: AllocationAlertSeverity;
  state: AllocationAlertState;
  escalation_level: AllocationAlertEscalationLevel;
  title: string;
  message: string;
  count: number;
  recurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  related_intent_ids: number[];
  related_cycle_ids: string[];
  related_execution_ids: number[];
  details: Record<string, unknown>;
};

export type ExposureBucket = {
  name: string;
  bucket_type: string;
  reserved_risk_percent: number;
  live_risk_percent: number;
  reserved_risk_amount: number;
  live_risk_amount: number;
  budget_limit_percent: number;
  total_risk_percent: number;
  utilization_percent?: number | null;
  remaining_risk_percent: number;
  risk_basis: string[];
};

export type DirectionalCurrencyExposureBucket = {
  currency: string;
  reserved_long_risk_percent: number;
  reserved_short_risk_percent: number;
  live_long_risk_percent: number;
  live_short_risk_percent: number;
  gross_risk_percent: number;
  net_risk_percent: number;
  gross_utilization_percent: number;
  net_bias: "LONG" | "SHORT" | "FLAT";
  risk_basis: string[];
};

export type ExposureHotspot = {
  bucket_type: string;
  name: string;
  total_risk_percent: number;
  budget_limit_percent: number;
  utilization_percent: number;
  risk_basis: string[];
  bucket_mode: string;
  net_bias?: "LONG" | "SHORT" | "FLAT";
  net_risk_percent?: number;
};

export type AllocationExposureSummary = {
  totals: {
    reserved_risk_percent: number;
    live_risk_percent: number;
    provisional_live_risk_percent: number;
    reserved_risk_amount: number;
    live_risk_amount: number;
    provisional_live_risk_amount: number;
    reserved_intent_count: number;
    open_position_count: number;
    remaining_portfolio_risk_percent: number;
  };
  by_strategy: ExposureBucket[];
  by_family: ExposureBucket[];
  by_instrument: ExposureBucket[];
  by_currency: ExposureBucket[];
  currency_directional: DirectionalCurrencyExposureBucket[];
  hotspots: ExposureHotspot[];
  notes: Record<string, string>;
};

export type RiskAllocationChartDataStatus =
  | "READY"
  | "PARTIAL"
  | "DEGRADED"
  | "UNAVAILABLE";

export type RiskAllocationChartSource =
  | "ALLOCATION_EXPOSURE_SUMMARY_PLUS_POSITION_INTENT_TRUTH";

export type RiskAllocationChartTruthCount = {
  confidence: RiskTruthConfidence | string;
  count: number;
};

export type RiskAllocationChartSummary = {
  reserved_risk_percent?: number | null;
  live_risk_percent?: number | null;
  provisional_live_risk_percent?: number | null;
  total_active_risk_percent?: number | null;
  remaining_portfolio_risk_percent?: number | null;
  reserved_intent_count: number;
  open_position_count: number;
  chartable_bucket_count: number;
  unavailable_bucket_count: number;
  has_provisional_risk: boolean;
  has_simulated_risk: boolean;
  has_unknown_risk: boolean;
  has_degraded_risk: boolean;
  risk_truth_confidence_mix: RiskAllocationChartTruthCount[];
  reasons: string[];
};

export type RiskAllocationChartBucket = {
  instrument: string;
  reserved_risk_percent?: number | null;
  live_risk_percent?: number | null;
  provisional_live_risk_percent?: number | null;
  total_risk_percent?: number | null;
  utilization_percent?: number | null;
  budget_limit_percent: number;
  reserved_intent_count: number;
  open_position_count: number;
  data_status: RiskAllocationChartDataStatus | string;
  has_provisional_risk: boolean;
  has_simulated_risk: boolean;
  has_unknown_risk: boolean;
  has_degraded_risk: boolean;
  risk_basis: string[];
  risk_truth_confidence_mix: RiskAllocationChartTruthCount[];
  reasons: string[];
};

export type RiskAllocationChart = {
  generated_at: string;
  data_status: RiskAllocationChartDataStatus | string;
  source: RiskAllocationChartSource | string;
  chart_mode: string;
  summary: RiskAllocationChartSummary;
  bars: RiskAllocationChartBucket[];
  reasons: string[];
  notes: Record<string, string>;
};
