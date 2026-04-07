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
