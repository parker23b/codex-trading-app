import {
  BrokerAuthStatus,
  DashboardSnapshot,
  MarketCategory,
  MarketInstrument,
  MarketOverviewResponse,
  MarketStatus,
  MarketSummary,
  Position,
  StrategyDefinition,
  Trade,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DEV_FALLBACK_ENABLED =
  process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_ENABLE_DEV_FALLBACK !== "false";
const REQUEST_TIMEOUT_MS = 1500;

type BackendMode = "live" | "dev-fallback";

class HttpError extends Error {
  status: number;
  detail?: string;

  constructor(status: number, detail?: string) {
    super(`Request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
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

type MarketTemplate = Omit<MarketInstrument, "status" | "tradable" | "active"> & {
  rule: (now: Date) => Pick<MarketInstrument, "status" | "tradable" | "active" | "sessionNote">;
};

const marketLabels: Record<MarketCategory, string> = {
  forex: "Forex",
  indices: "Indices",
  commodities: "Commodities",
  stocks: "Stocks",
  crypto: "Crypto",
};

function startOfUtcWeek(date: Date) {
  const weekStart = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  weekStart.setUTCDate(weekStart.getUTCDate() - weekStart.getUTCDay());
  return weekStart;
}

function isWithinMinutes(target: Date, now: Date, minutes: number) {
  return Math.abs(target.getTime() - now.getTime()) <= minutes * 60_000;
}

function nextWeek(date: Date, days = 7) {
  return new Date(date.getTime() + days * 24 * 60 * 60 * 1000);
}

function utcDate(date: Date, dayOffset = 0, hour = 0, minute = 0) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + dayOffset, hour, minute, 0, 0));
}

function nextWeekdayDateAt(now: Date, hour: number, minute = 0) {
  let offset = 0;
  while (offset < 8) {
    const candidate = utcDate(now, offset, hour, minute);
    const day = candidate.getUTCDay();
    if (day !== 0 && day !== 6 && candidate > now) {
      return candidate;
    }
    offset += 1;
  }
  return utcDate(now, 7, hour, minute);
}

function buildWeeklyWindowStatus(
  now: Date,
  open: Date,
  close: Date,
  options?: { warningBeforeCloseMinutes?: number; warningAfterOpenMinutes?: number; closedNote?: string; openNote?: string },
): {
  status: MarketStatus;
  tradable: boolean;
  active: boolean;
  sessionNote?: string;
  nextTransitionAt: Date;
  nextTransitionLabel: string;
} {
  const warningBeforeCloseMinutes = options?.warningBeforeCloseMinutes ?? 90;
  const warningAfterOpenMinutes = options?.warningAfterOpenMinutes ?? 20;
  const isOpen = now >= open && now < close;

  if (!isOpen) {
    const nextOpen = now < open ? open : nextWeek(open);
    return {
      status: "CLOSED",
      tradable: false,
      active: false,
      sessionNote: options?.closedNote,
      nextTransitionAt: nextOpen,
      nextTransitionLabel: "Opens",
    };
  }

  const minutesUntilClose = (close.getTime() - now.getTime()) / 60_000;
  const minutesFromOpen = (now.getTime() - open.getTime()) / 60_000;
  const limited = minutesUntilClose <= warningBeforeCloseMinutes || minutesFromOpen <= warningAfterOpenMinutes;

  return {
    status: limited ? "LIMITED" : "OPEN",
    tradable: true,
    active: true,
    sessionNote: limited ? options?.openNote ?? "Approaching a session edge. New entries may be restricted." : undefined,
    nextTransitionAt: close,
    nextTransitionLabel: "Closes",
  };
}

function formatCountdown(targetIso: string, now = new Date()) {
  const deltaMs = Math.max(0, new Date(targetIso).getTime() - now.getTime());
  const totalMinutes = Math.round(deltaMs / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatTransitionHeadline(status: MarketStatus, nextTransitionLabel: string, nextTransitionAt: string, now = new Date()) {
  const countdown = formatCountdown(nextTransitionAt, now);
  if (status === "CLOSED") {
    return `${nextTransitionLabel} in ${countdown}`;
  }
  return `${nextTransitionLabel} in ${countdown}`;
}

function forexStatus(now: Date) {
  const weekStart = startOfUtcWeek(now);
  const open = new Date(weekStart);
  open.setUTCHours(21, 0, 0, 0);
  const close = new Date(weekStart);
  close.setUTCDate(close.getUTCDate() + 5);
  close.setUTCHours(21, 0, 0, 0);
  const adjustedOpen = now.getUTCDay() === 6 ? nextWeek(open) : open;
  return buildWeeklyWindowStatus(now, adjustedOpen, close, {
    warningBeforeCloseMinutes: 120,
    warningAfterOpenMinutes: 30,
    closedNote: "Primary FX session is offline. Strategies should queue until Sunday reopen.",
    openNote: "Liquidity is near a session handoff. Tight spreads are less reliable.",
  });
}

function indicesStatus(now: Date) {
  const isWeekend = now.getUTCDay() === 0 || now.getUTCDay() === 6;
  const todayOpen = utcDate(now, 0, 7, 0);
  const todayClose = utcDate(now, 0, 21, 0);

  if (isWeekend) {
    const nextOpen = nextWeekdayDateAt(now, 7, 0);
    return {
      status: "CLOSED" as const,
      tradable: false,
      active: false,
      sessionNote: "Index futures are in their offline window. Mean-reversion jobs should stay parked.",
      nextTransitionAt: nextOpen,
      nextTransitionLabel: "Opens",
    };
  }

  const open = now < todayOpen ? todayOpen : now < todayClose ? todayOpen : nextWeekdayDateAt(now, 7, 0);
  const close = now < todayOpen ? utcDate(open, 0, 21, 0) : now < todayClose ? todayClose : utcDate(open, 0, 21, 0);
  return buildWeeklyWindowStatus(now, open, close, {
    warningBeforeCloseMinutes: 75,
    warningAfterOpenMinutes: 20,
    closedNote: "Index futures are in their offline window. Mean-reversion jobs should stay parked.",
    openNote: "Index session is live, but edge conditions near the bell favor lighter exposure.",
  });
}

function commoditiesStatus(now: Date) {
  const day = now.getUTCDay();
  const isWeekend = day === 0 || day === 6;
  if (isWeekend) {
    return {
      status: "CLOSED" as const,
      tradable: false,
      active: false,
      sessionNote: "Commodity markets are between sessions or in maintenance.",
      nextTransitionAt: nextWeekdayDateAt(now, 22, 0),
      nextTransitionLabel: "Opens",
    };
  }

  const todayMaintenanceStart = utcDate(now, 0, 21, 0);
  const todayReopen = utcDate(now, 0, 22, 0);
  const prevSessionOpen = utcDate(now, -1, 22, 0);
  const nextSessionClose = utcDate(now, 0, 21, 0);

  if (day === 5 && now >= todayMaintenanceStart) {
    return {
      status: "CLOSED" as const,
      tradable: false,
      active: false,
      sessionNote: "Commodity markets are closed for the weekend after Friday settlement.",
      nextTransitionAt: nextWeekdayDateAt(now, 22, 0),
      nextTransitionLabel: "Opens",
    };
  }

  if (now < nextSessionClose && now >= prevSessionOpen) {
    return buildWeeklyWindowStatus(now, prevSessionOpen, nextSessionClose, {
      warningBeforeCloseMinutes: 60,
      warningAfterOpenMinutes: 30,
      closedNote: "Commodity markets are between sessions or in maintenance.",
      openNote: "Commodity session is live with a narrower operating window around rollover.",
    });
  }

  if (now >= todayMaintenanceStart && now < todayReopen) {
    return {
      status: "LIMITED" as const,
      tradable: false,
      active: true,
      sessionNote: "Daily rollover window. Existing positions can be monitored, but new entries should wait.",
      nextTransitionAt: todayReopen,
      nextTransitionLabel: "Resumes",
    };
  }

  const tonightOpen = utcDate(now, 0, 22, 0);
  const tomorrowClose = utcDate(now, 1, 21, 0);
  return buildWeeklyWindowStatus(now, tonightOpen, tomorrowClose, {
    warningBeforeCloseMinutes: 60,
    warningAfterOpenMinutes: 30,
    closedNote: "Commodity markets are between sessions or in maintenance.",
    openNote: "Commodity session is live with a narrower operating window around rollover.",
  });
}

function stocksStatus(now: Date) {
  const day = now.getUTCDay();
  const isWeekend = day === 0 || day === 6;
  const todayOpen = utcDate(now, 0, 13, 30);
  const todayClose = utcDate(now, 0, 20, 0);

  if (isWeekend) {
    const nextOpen = nextWeekdayDateAt(now, 13, 30);
    return {
      status: "CLOSED" as const,
      tradable: false,
      active: false,
      sessionNote: "Cash equity books are offline. Equity strategies should remain disabled until the next bell.",
      nextTransitionAt: nextOpen,
      nextTransitionLabel: "Opens",
    };
  }

  const open = now < todayOpen ? todayOpen : now < todayClose ? todayOpen : nextWeekdayDateAt(now, 13, 30);
  const close = now < todayOpen ? utcDate(open, 0, 20, 0) : now < todayClose ? todayClose : utcDate(open, 0, 20, 0);
  return buildWeeklyWindowStatus(now, open, close, {
    warningBeforeCloseMinutes: 45,
    warningAfterOpenMinutes: 15,
    closedNote: "Cash equity books are offline. Equity strategies should remain disabled until the next bell.",
    openNote: "Cash market is live, but opening and closing auctions can distort signal quality.",
  });
}

function cryptoStatus(now: Date) {
  const nextFundingCheck = new Date(now);
  nextFundingCheck.setUTCMinutes(0, 0, 0);
  nextFundingCheck.setUTCHours(nextFundingCheck.getUTCHours() + 1);
  const limited = isWithinMinutes(nextFundingCheck, now, 15);
  return {
    status: limited ? ("LIMITED" as const) : ("OPEN" as const),
    tradable: !limited,
    active: true,
    sessionNote: limited ? "Funding and liquidity reset approaching. Auto-entry is paused for the next few minutes." : "24/7 market. Strategies can operate continuously.",
    nextTransitionAt: nextFundingCheck,
    nextTransitionLabel: limited ? "Resumes" : "Funding check",
  };
}

function getCategoryWindow(category: MarketCategory, now: Date) {
  switch (category) {
    case "forex":
      return forexStatus(now);
    case "indices":
      return indicesStatus(now);
    case "commodities":
      return commoditiesStatus(now);
    case "stocks":
      return stocksStatus(now);
    case "crypto":
      return cryptoStatus(now);
  }
}

const mockMarketTemplates: Record<MarketCategory, MarketTemplate[]> = {
  forex: [
    {
      id: "eurusd",
      category: "forex",
      name: "EUR/USD",
      symbol: "EURUSD",
      activityLevel: "HIGH",
      strategyCompatibility: ["Mean reversion", "Breakout guard", "Carry drift"],
      price: 1.0842,
      changePercent: 0.28,
      rule: (now) => ({ ...forexStatus(now), active: true }),
    },
    {
      id: "gbpusd",
      category: "forex",
      name: "GBP/USD",
      symbol: "GBPUSD",
      activityLevel: "HIGH",
      strategyCompatibility: ["Breakout guard", "Session momentum"],
      price: 1.2928,
      changePercent: -0.16,
      rule: (now) => ({ ...forexStatus(now), active: true }),
    },
    {
      id: "usdchf",
      category: "forex",
      name: "USD/CHF",
      symbol: "USDCHF",
      activityLevel: "LOW",
      strategyCompatibility: ["Carry drift"],
      price: 0.8824,
      changePercent: 0.05,
      rule: (now) => ({ ...forexStatus(now), active: now.getUTCHours() >= 6 && now.getUTCHours() <= 18 }),
    },
  ],
  indices: [
    {
      id: "ftse100",
      category: "indices",
      name: "FTSE 100",
      symbol: "UKX",
      activityLevel: "MEDIUM",
      strategyCompatibility: ["Mean reversion", "Breakout guard"],
      price: 8178.4,
      changePercent: 0.41,
      rule: (now) => ({ ...indicesStatus(now), active: true }),
    },
    {
      id: "nasdaq100",
      category: "indices",
      name: "Nasdaq 100",
      symbol: "NDX",
      activityLevel: "HIGH",
      strategyCompatibility: ["Breakout guard", "Trend follow"],
      price: 18864.1,
      changePercent: 0.93,
      rule: (now) => ({ ...indicesStatus(now), active: true }),
    },
    {
      id: "nikkei225",
      category: "indices",
      name: "Nikkei 225",
      symbol: "NI225",
      activityLevel: "LOW",
      strategyCompatibility: ["Overnight drift"],
      price: 39742.6,
      changePercent: -0.22,
      rule: (now) => {
        const base = indicesStatus(now);
        return {
          ...base,
          active: now.getUTCHours() >= 0 && now.getUTCHours() <= 8,
          tradable: base.tradable && now.getUTCHours() >= 0 && now.getUTCHours() <= 8,
          status: base.status === "CLOSED" ? "CLOSED" : now.getUTCHours() <= 8 ? base.status : "LIMITED",
          sessionNote: now.getUTCHours() <= 8 ? base.sessionNote : "Regional session is thin. Signal quality is degraded outside Tokyo hours.",
        };
      },
    },
  ],
  commodities: [
    {
      id: "gold",
      category: "commodities",
      name: "Gold",
      symbol: "XAUUSD",
      activityLevel: "HIGH",
      strategyCompatibility: ["Breakout guard", "Volatility fade"],
      price: 2184.6,
      changePercent: 0.62,
      rule: (now) => ({ ...commoditiesStatus(now), active: true }),
    },
    {
      id: "wti",
      category: "commodities",
      name: "WTI Crude",
      symbol: "CL",
      activityLevel: "MEDIUM",
      strategyCompatibility: ["Trend follow", "Breakout guard"],
      price: 81.42,
      changePercent: -0.44,
      rule: (now) => ({ ...commoditiesStatus(now), active: true }),
    },
    {
      id: "silver",
      category: "commodities",
      name: "Silver",
      symbol: "XAGUSD",
      activityLevel: "LOW",
      strategyCompatibility: ["Mean reversion"],
      price: 24.31,
      changePercent: 0.12,
      rule: (now) => ({ ...commoditiesStatus(now), active: now.getUTCHours() >= 7 && now.getUTCHours() <= 18 }),
    },
  ],
  stocks: [
    {
      id: "aapl",
      category: "stocks",
      name: "Apple",
      symbol: "AAPL",
      activityLevel: "HIGH",
      strategyCompatibility: ["Opening impulse", "Mean reversion"],
      price: 214.82,
      changePercent: 0.74,
      rule: (now) => ({ ...stocksStatus(now), active: true }),
    },
    {
      id: "msft",
      category: "stocks",
      name: "Microsoft",
      symbol: "MSFT",
      activityLevel: "MEDIUM",
      strategyCompatibility: ["Trend follow", "Breakout guard"],
      price: 428.17,
      changePercent: 0.38,
      rule: (now) => ({ ...stocksStatus(now), active: true }),
    },
    {
      id: "tsla",
      category: "stocks",
      name: "Tesla",
      symbol: "TSLA",
      activityLevel: "HIGH",
      strategyCompatibility: ["Volatility breakout"],
      price: 173.94,
      changePercent: -1.12,
      rule: (now) => {
        const base = stocksStatus(now);
        return {
          ...base,
          tradable: base.tradable && now.getUTCHours() >= 14 && now.getUTCHours() <= 19,
          status: base.status === "CLOSED" ? "CLOSED" : now.getUTCHours() >= 14 && now.getUTCHours() <= 19 ? base.status : "LIMITED",
          active: true,
          sessionNote: now.getUTCHours() >= 14 && now.getUTCHours() <= 19 ? base.sessionNote : "Volatility guard is blocking entries outside the core U.S. session.",
        };
      },
    },
  ],
  crypto: [
    {
      id: "btc",
      category: "crypto",
      name: "Bitcoin",
      symbol: "BTCUSD",
      activityLevel: "HIGH",
      strategyCompatibility: ["Trend follow", "Breakout guard", "Funding arb"],
      price: 68242,
      changePercent: 1.84,
      rule: (now) => ({ ...cryptoStatus(now), active: true }),
    },
    {
      id: "eth",
      category: "crypto",
      name: "Ethereum",
      symbol: "ETHUSD",
      activityLevel: "HIGH",
      strategyCompatibility: ["Mean reversion", "Funding arb"],
      price: 3648.2,
      changePercent: 1.12,
      rule: (now) => ({ ...cryptoStatus(now), active: true }),
    },
    {
      id: "sol",
      category: "crypto",
      name: "Solana",
      symbol: "SOLUSD",
      activityLevel: "MEDIUM",
      strategyCompatibility: ["Momentum burst"],
      price: 168.31,
      changePercent: -0.61,
      rule: (now) => {
        const base = cryptoStatus(now);
        return {
          ...base,
          tradable: base.tradable && now.getUTCMinutes() < 50,
          status: base.status === "LIMITED" || now.getUTCMinutes() >= 50 ? "LIMITED" : "OPEN",
          active: true,
          sessionNote: now.getUTCMinutes() >= 50 ? "Exchange throttle window. Auto-routing is held for the last 10 minutes of the hour." : base.sessionNote,
        };
      },
    },
  ],
};

function buildMarketOverview(now = new Date()): MarketOverviewResponse {
  const instruments = (Object.keys(mockMarketTemplates) as MarketCategory[]).reduce<Record<MarketCategory, MarketInstrument[]>>(
    (accumulator, category) => {
      accumulator[category] = mockMarketTemplates[category].map(({ rule, ...template }) => {
        const state = rule(now);
        return {
          ...template,
          ...state,
        };
      });
      return accumulator;
    },
    {
      forex: [],
      indices: [],
      commodities: [],
      stocks: [],
      crypto: [],
    },
  );

  const summaries = (Object.keys(instruments) as MarketCategory[]).map((category) => {
    const rows = instruments[category];
    const activeCount = rows.filter((instrument) => instrument.active).length;
    const tradableCount = rows.filter((instrument) => instrument.tradable).length;
    const categoryState = getCategoryWindow(category, now);
    const nextTransitionAt = categoryState.nextTransitionAt.toISOString();
    const status = tradableCount === 0 ? categoryState.status : rows.some((row) => row.status === "OPEN") ? "OPEN" : rows.some((row) => row.status === "LIMITED") ? "LIMITED" : "CLOSED";

    return {
      category,
      label: marketLabels[category],
      description:
        category === "forex"
          ? "Global currency pairs with session-aware strategy routing."
          : category === "indices"
            ? "Major benchmark contracts where directional and mean-reversion systems run."
            : category === "commodities"
              ? "Metals and energy products with tighter session maintenance windows."
              : category === "stocks"
                ? "Cash equities focused on the primary U.S. session."
                : "Always-on digital assets with hourly risk throttles.",
      status,
      headline: formatTransitionHeadline(status, categoryState.nextTransitionLabel, nextTransitionAt, now),
      detail: categoryState.sessionNote ?? `${tradableCount} of ${rows.length} instruments are ready for strategy deployment.`,
      nextTransitionAt,
      nextTransitionLabel: categoryState.nextTransitionLabel,
      tradableCount,
      activeCount,
      totalCount: rows.length,
    } satisfies MarketSummary;
  });

  return {
    generatedAt: now.toISOString(),
    summaries,
    instruments,
  };
}

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
    if (shouldUseFallback(error)) {
      return {
        state: "unavailable",
        label: "Broker Check Offline",
        detail: "Backend fallback mode is active",
        position_count: 0,
      };
    }

    const detail = error instanceof HttpError ? error.detail : undefined;
    return {
      state: "disconnected",
      label: "IG Auth Failed",
      detail: detail ?? "Broker authentication check failed",
      position_count: 0,
    };
  }
}

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  return request<DashboardSnapshot>("/dashboard");
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

export async function getMarketOverview(): Promise<MarketOverviewResponse> {
  try {
    return await request<MarketOverviewResponse>("/markets/overview");
  } catch (error) {
    if (shouldUseFallback(error)) {
      return buildMarketOverview();
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
