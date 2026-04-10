export type Trade = {
  id: number;
  strategy_name: string;
  broker_reference?: string | null;
  close_broker_reference?: string | null;
  instrument: string;
  direction: "BUY" | "SELL";
  size: number;
  open_price: number;
  close_price: number;
  open_time: string;
  close_time: string;
  pnl: number;
  account_type: "DEMO" | "LIVE";
  r_multiple?: number | null;
  reason?: string | null;
};

export type Execution = {
  id: number;
  strategy_name: string;
  instrument: string;
  phase: "ENTRY" | "CLOSE";
  status:
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
  broker_reference?: string | null;
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
  broker_reference?: string | null;
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
  reason?: string | null;
  manual_override?: boolean;
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
  broker_reference?: string | null;
  direction?: "BUY" | "SELL" | null;
  current_price?: number | null;
  unrealized_pnl?: number | null;
};

export type StrategyPositionSummary = {
  broker_reference?: string | null;
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
  active_instruments?: string[];
  active_runtime_count?: number;
  open_position_count?: number;
  warning_message?: string | null;
  warning_instrument?: string | null;
  warning_status?: string | null;
  active_runtimes?: StrategyRuntime[];
  open_positions?: StrategyPositionSummary[];
  instrument_options?: { epic: string; label: string; category: string }[];
  parameters: StrategyParameter[];
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
    updated_at?: string | null;
  };
  deployment: {
    state: string;
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
    active_runtime_id?: string | null;
    active_instrument?: string | null;
    active_profile_name?: string | null;
    active_parameters: Record<string, number>;
    control_mode?: string | null;
    recovery_state?: string | null;
    updated_at?: string | null;
    persisted_runtimes: Array<{
      runtime_id: string;
      status: string;
      instrument: string;
      control_mode?: string | null;
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
  stream_connected: boolean;
  stream_last_tick_at?: string | null;
  stream_last_tick_age_ms?: number | null;
  subscribed_instrument_count: number;
  desired_instrument_count: number;
  broker_connected: boolean;
  broker_latency_ms?: number | null;
  runtime_count: number;
  active_runtime_count: number;
  stale_runtime_count: number;
  stale_price_runtime_count: number;
  reconciliation_mismatches: number;
  order_failures_last_5m: number;
  rejected_orders_last_5m: number;
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
  category: "strategy" | "risk" | "execution" | "reconciliation" | "operator" | "health";
  severity: "info" | "warning" | "error";
  error_type?: string | null;
  source: string;
  correlation_id?: string | null;
  runtime_id?: string | null;
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
  accountValue: number;
  accountValuePercent: number;
  dailyPnl: number;
  dailyPnlPercent: number;
  openRisk: number;
  winRate: number;
  riskReward: number;
  runningStrategies?: {
    name: string;
    instrument: string;
    instrumentLabel: string;
    runtimeKey?: string;
    brokerReference?: string | null;
    hasOpenPosition?: boolean;
    lastPrice?: number | null;
  }[];
};

export type MarketCategory = "forex" | "indices" | "commodities" | "stocks" | "crypto";

export type MarketStatus = "OPEN" | "CLOSED" | "LIMITED";

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
