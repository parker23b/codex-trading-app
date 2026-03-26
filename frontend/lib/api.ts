import {
  BrokerAuthStatus,
  DashboardSnapshot,
  MarketCategory,
  MarketCategoryOverviewResponse,
  Position,
  StrategyDefinition,
  StreamHealthStatus,
  Trade,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 1500;
const MARKET_REQUEST_TIMEOUT_MS = 12000;

type BackendMode = "live";

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

export async function getOpenPositions(): Promise<Position[]> {
  return request<Position[]>("/trades/positions");
}

export async function getBrokerAuthStatus(): Promise<BrokerAuthStatus> {
  try {
    const positions = await request<
      Array<{ instrument: string; direction: "BUY" | "SELL"; size: number; open_price: number; opened_at: string }>
    >("/broker/positions");
    return {
      state: "connected",
      label: "IG Connected",
      detail: positions.length ? `${positions.length} broker position${positions.length === 1 ? "" : "s"} synced` : "Authenticated with no open broker positions",
      position_count: positions.length,
    };
  } catch (error) {
    const detail = error instanceof HttpError ? error.detail : undefined;
    return {
      state: "disconnected",
      label: "IG Auth Failed",
      detail: detail ?? "Broker authentication check failed",
      position_count: 0,
    };
  }
}

export async function getStreamHealth(): Promise<StreamHealthStatus> {
  return request<StreamHealthStatus>("/health/stream");
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

export async function startStrategy(strategyName: string, instrument: string): Promise<{ status: string }> {
  return request<{ status: string }>("/strategy/start", {
    method: "POST",
    body: JSON.stringify({
      strategy_name: strategyName,
      instrument,
    }),
  });
}

export async function stopStrategy(instrument: string): Promise<{ status: string }> {
  return request<{ status: string }>("/strategy/stop", {
    method: "POST",
    body: JSON.stringify({ instrument }),
  });
}
