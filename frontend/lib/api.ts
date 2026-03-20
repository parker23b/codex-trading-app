import { Position, StrategyDefinition, Trade } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DEV_FALLBACK_ENABLED =
  process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_ENABLE_DEV_FALLBACK !== "false";
const REQUEST_TIMEOUT_MS = 1500;

type BackendMode = "live" | "dev-fallback";

class HttpError extends Error {
  status: number;

  constructor(status: number) {
    super(`Request failed with status ${status}`);
    this.status = status;
  }
}

const mockTrades: Trade[] = [
  {
    id: 1,
    strategy_name: "mean_reversion",
    instrument: "IX.D.FTSE.DAILY.IP",
    direction: "BUY",
    size: 2,
    open_price: 8124.4,
    close_price: 8141.2,
    open_time: "2026-03-20T08:30:00Z",
    close_time: "2026-03-20T10:05:00Z",
    pnl: 33.6,
    account_type: "DEMO",
    r_multiple: 1.4,
    reason: "Price snapped back through the rolling mean after opening below threshold.",
  },
  {
    id: 2,
    strategy_name: "mean_reversion",
    instrument: "IX.D.DAX.DAILY.IP",
    direction: "SELL",
    size: 1,
    open_price: 18495.5,
    close_price: 18440.3,
    open_time: "2026-03-19T13:00:00Z",
    close_time: "2026-03-19T14:12:00Z",
    pnl: 55.2,
    account_type: "DEMO",
    r_multiple: 2.1,
    reason: "Short entry faded an overextended move into resistance.",
  },
  {
    id: 3,
    strategy_name: "breakout_guard",
    instrument: "IX.D.NASDAQ.DAILY.IP",
    direction: "BUY",
    size: 1.5,
    open_price: 18944.3,
    close_price: 18880.4,
    open_time: "2026-03-18T09:45:00Z",
    close_time: "2026-03-18T13:05:00Z",
    pnl: -95.85,
    account_type: "DEMO",
    r_multiple: -1.0,
    reason: "Momentum breakout failed after volatility compression unwind.",
  },
  {
    id: 4,
    strategy_name: "mean_reversion",
    instrument: "IX.D.SP500.DAILY.IP",
    direction: "SELL",
    size: 1,
    open_price: 5210.7,
    close_price: 5197.2,
    open_time: "2026-03-17T12:20:00Z",
    close_time: "2026-03-17T15:35:00Z",
    pnl: 13.5,
    account_type: "DEMO",
    r_multiple: 0.8,
    reason: "Mean reversion signal after intraday extension beyond volatility band.",
  },
];

const mockPositions: Position[] = [
  {
    id: 1,
    strategy_name: "mean_reversion",
    instrument: "IX.D.FTSE.DAILY.IP",
    direction: "SELL",
    size: 1,
    open_price: 8162.8,
    open_time: "2026-03-20T11:20:00Z",
    close_time: null,
    close_price: null,
    pnl: null,
    account_type: "DEMO",
    is_open: true,
    current_price: 8148.6,
    unrealized_pnl: 14.2,
    risk_percent: 1.2,
    reason: "Price moved more than 1% above the 20-period mean.",
    manual_override: false,
  },
  {
    id: 2,
    strategy_name: "breakout_guard",
    instrument: "IX.D.NASDAQ.DAILY.IP",
    direction: "BUY",
    size: 0.8,
    open_price: 18762.4,
    open_time: "2026-03-20T10:10:00Z",
    close_time: null,
    close_price: null,
    pnl: null,
    account_type: "DEMO",
    is_open: true,
    current_price: 18748.9,
    unrealized_pnl: -10.8,
    risk_percent: 0.9,
    reason: "Breakout confirmation after range expansion and volume pickup.",
    manual_override: true,
  },
  {
    id: 3,
    strategy_name: "carry_drift",
    instrument: "IX.D.DAX.DAILY.IP",
    direction: "SELL",
    size: 0.6,
    open_price: 18520.1,
    open_time: "2026-03-20T09:05:00Z",
    close_time: null,
    close_price: null,
    pnl: null,
    account_type: "DEMO",
    is_open: true,
    current_price: 18490.2,
    unrealized_pnl: 17.94,
    risk_percent: 1.8,
    reason: "Short bias activated after overnight gap exhausted against trend filter.",
    manual_override: false,
  },
];

const mockStrategies: StrategyDefinition[] = [
  {
    name: "mean_reversion",
    description: "Buys when price moves below the rolling mean and sells when price stretches above it.",
    instrument: "IX.D.FTSE.DAILY.IP",
    status: "RUNNING",
    current_pnl: 14.2,
    trade_count: 18,
    win_rate: 61,
    account_type: "DEMO",
    position_size: 1,
    risk_per_trade: 0.8,
    parameters: [
      { key: "window", label: "Window", value: 20, step: 1 },
      { key: "entry_threshold", label: "Entry Threshold", value: 1.2, step: 0.1 },
      { key: "exit_threshold", label: "Exit Threshold", value: 0.3, step: 0.1 },
    ],
  },
  {
    name: "breakout_guard",
    description: "Trades directional breaks only when volatility and trend filters align.",
    instrument: "IX.D.NASDAQ.DAILY.IP",
    status: "RUNNING",
    current_pnl: -10.8,
    trade_count: 12,
    win_rate: 50,
    account_type: "DEMO",
    position_size: 0.8,
    risk_per_trade: 1.1,
    parameters: [
      { key: "breakout_window", label: "Breakout Window", value: 15, step: 1 },
      { key: "atr_filter", label: "ATR Filter", value: 1.4, step: 0.1 },
      { key: "stop_multiple", label: "Stop Multiple", value: 1.8, step: 0.1 },
    ],
  },
  {
    name: "carry_drift",
    description: "Follows session trend drift with a tighter mean-reentry stop discipline.",
    instrument: "IX.D.DAX.DAILY.IP",
    status: "STOPPED",
    current_pnl: 0,
    trade_count: 24,
    win_rate: 58,
    account_type: "DEMO",
    position_size: 0.6,
    risk_per_trade: 0.7,
    parameters: [
      { key: "trend_window", label: "Trend Window", value: 34, step: 1 },
      { key: "reentry_buffer", label: "Reentry Buffer", value: 0.6, step: 0.1 },
      { key: "take_profit", label: "Take Profit", value: 2.3, step: 0.1 },
    ],
  },
];

async function fetchWithTimeout(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    ...init,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
}

function shouldUseFallback(error: unknown): boolean {
  return DEV_FALLBACK_ENABLED && error instanceof Error && !(error instanceof HttpError);
}

async function isBackendReachable(): Promise<boolean> {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new HttpError(response.status);
  }

  return response.json() as Promise<T>;
}

export async function getBackendMode(): Promise<BackendMode> {
  if (!DEV_FALLBACK_ENABLED) {
    return "live";
  }

  const reachable = await isBackendReachable();
  return reachable ? "live" : "dev-fallback";
}

export async function getTrades(): Promise<Trade[]> {
  try {
    return await request<Trade[]>("/trades");
  } catch (error) {
    if (shouldUseFallback(error)) {
      return mockTrades;
    }
    throw error;
  }
}

export async function getOpenPositions(): Promise<Position[]> {
  try {
    return await request<Position[]>("/trades/positions");
  } catch (error) {
    if (shouldUseFallback(error)) {
      return mockPositions;
    }
    throw error;
  }
}

export async function getStrategies(): Promise<StrategyDefinition[]> {
  try {
    return await request<StrategyDefinition[]>("/strategies");
  } catch (error) {
    if (shouldUseFallback(error)) {
      return mockStrategies;
    }
    throw error;
  }
}

export async function startStrategy(strategyName: string, instrument: string): Promise<{ status: string }> {
  try {
    return await request<{ status: string }>("/strategy/start", {
      method: "POST",
      body: JSON.stringify({
        strategy_name: strategyName,
        instrument,
      }),
    });
  } catch (error) {
    if (shouldUseFallback(error)) {
      return { status: `simulated-start:${strategyName}:${instrument}` };
    }
    throw error;
  }
}

export async function stopStrategy(instrument: string): Promise<{ status: string }> {
  try {
    return await request<{ status: string }>("/strategy/stop", {
      method: "POST",
      body: JSON.stringify({ instrument }),
    });
  } catch (error) {
    if (shouldUseFallback(error)) {
      return { status: `simulated-stop:${instrument}` };
    }
    throw error;
  }
}
