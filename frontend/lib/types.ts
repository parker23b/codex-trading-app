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
