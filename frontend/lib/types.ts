export type Trade = {
  id: number;
  strategy_name: string;
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

export type Position = {
  id: number;
  strategy_name: string;
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

export type StrategyDefinition = {
  name: string;
  description: string;
  instrument: string;
  status: "RUNNING" | "STOPPED";
  current_pnl: number;
  last_price?: number | null;
  trade_count: number;
  win_rate: number;
  account_type: "DEMO" | "LIVE";
  position_size: number;
  risk_per_trade: number;
  instrument_options?: { epic: string; label: string; category: string }[];
  parameters: StrategyParameter[];
};

export type BrokerAuthStatus = {
  state: "connected" | "disconnected" | "unavailable";
  label: string;
  detail: string;
  position_count: number;
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
    lastPrice?: number | null;
  }[];
};
