"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";

import {
  askOperationalQuestion,
  getControlPlaneSummary,
  getCoverageSummary,
  getDashboardSnapshot,
  getDomainEvents,
  getOperationalTelemetry,
  getOperatorSummaryReview,
  getReviewHistory,
  getStrategies,
} from "@/lib/api";
import { formatCurrency, formatPercent, formatRelativeDuration, formatSignedCurrency } from "@/lib/format";
import type {
  ControlPlaneSummary,
  CoverageSummary,
  DashboardSnapshot,
  DomainEvent,
  OperationalQuestionReviewResponse,
  OperationalTelemetry,
  OperatorSummaryReview,
  ReviewHistoryItem,
  StrategyDefinition,
} from "@/lib/types";

type Tone = "positive" | "warning" | "negative" | "neutral";
type RouteContext = "operate" | "control-plane" | "coverage" | "events" | "strategies" | "general";

type AimeeSnapshot = {
  review: OperatorSummaryReview | null;
  history: ReviewHistoryItem[];
  controlPlane: ControlPlaneSummary | null;
  coverage: CoverageSummary | null;
  dashboard: DashboardSnapshot | null;
  telemetry: OperationalTelemetry | null;
  events: DomainEvent[];
  strategies: StrategyDefinition[];
  updatedAt: string | null;
};

type OverviewCard = {
  id: string;
  title: string;
  detail: string;
  meta?: string;
  tone: Tone;
};

type WarningItem = {
  id: string;
  title: string;
  detail: string;
  tone: Tone;
};

type ChangeItem = {
  id: string;
  title: string;
  detail: string;
  at?: string | null;
};

type ChatMessage =
  | {
      id: string;
      role: "user";
      createdAt: string;
      question: string;
    }
  | {
      id: string;
      role: "assistant";
      createdAt: string;
      question: string;
      status: "loading" | "ready" | "error";
      response?: OperationalQuestionReviewResponse | null;
      error?: string | null;
    };

const SUGGESTED_QUESTIONS: Record<RouteContext, string[]> = {
  operate: [
    "What needs my attention right now?",
    "Explain current risk exposure",
    "What changed in the last hour?",
    "Why is PnL moving today?",
  ],
  "control-plane": [
    "Which families are blocked or degraded?",
    "Why is this family blocked?",
    "What governance mismatches matter most?",
    "Where is autonomy constrained right now?",
  ],
  coverage: [
    "Explain current Tier 1 and Tier 2 allocation",
    "Which promotion decisions deserve review?",
    "Where are coverage limits binding?",
    "What changed in the watchlist recently?",
  ],
  events: [
    "Which anomalies matter most right now?",
    "Summarize the latest warning and error events",
    "What changed in the last hour?",
    "Which events suggest operational risk?",
  ],
  strategies: [
    "Which strategies need attention?",
    "Explain runtime health across strategies",
    "Where are strategies degraded or stale?",
    "What changed in deployment state recently?",
  ],
  general: [
    "What needs my attention?",
    "Summarize current system state",
    "What changed in the last hour?",
    "Explain current risk exposure",
  ],
};

const STATUS_LABEL: Record<Tone, string> = {
  positive: "Healthy",
  warning: "Degraded",
  negative: "Attention Needed",
  neutral: "Monitoring",
};

function joinClasses(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "n/a";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatCount(label: string, count: number) {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

function formatMetricValue(value?: number | null, kind: "currency" | "percent" | "count" = "count") {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (kind === "currency") {
    return formatCurrency(value);
  }
  if (kind === "percent") {
    return formatPercent(value);
  }
  return String(value);
}

function toneFromWarningSeverity(severity?: string): Tone {
  if (severity === "critical" || severity === "error") {
    return "negative";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}

function routeContextFromPath(pathname: string): RouteContext {
  if (pathname === "/") {
    return "operate";
  }
  if (pathname.startsWith("/control-plane")) {
    return "control-plane";
  }
  if (pathname.startsWith("/coverage")) {
    return "coverage";
  }
  if (pathname.startsWith("/events")) {
    return "events";
  }
  if (pathname.startsWith("/strategies")) {
    return "strategies";
  }
  return "general";
}

function routeLabel(context: RouteContext) {
  switch (context) {
    case "operate":
      return "Operate";
    case "control-plane":
      return "Control Plane";
    case "coverage":
      return "Coverage";
    case "events":
      return "Events";
    case "strategies":
      return "Strategies";
    default:
      return "System";
  }
}

function computeSystemTone(snapshot: AimeeSnapshot): Tone {
  const criticalWarnings = snapshot.review?.warnings.filter((warning) => warning.severity === "critical").length ?? 0;
  const warningCount = snapshot.review?.warnings.length ?? 0;
  const telemetry = snapshot.telemetry;
  const controlPlane = snapshot.controlPlane;

  if (
    criticalWarnings > 0 ||
    (telemetry !== null &&
      (!telemetry.stream_connected ||
        !telemetry.broker_connected ||
        telemetry.reconciliation_mismatches > 0 ||
        telemetry.order_failures_last_5m > 0))
  ) {
    return "negative";
  }

  if (
    warningCount > 0 ||
    (controlPlane !== null && controlPlane.misaligned_count > 0) ||
    (telemetry !== null &&
      (telemetry.stale_runtime_count > 0 || telemetry.stale_price_runtime_count > 0 || telemetry.rejected_orders_last_5m > 0))
  ) {
    return "warning";
  }

  return snapshot.review ? "positive" : "neutral";
}

function buildSystemSummary(snapshot: AimeeSnapshot, context: RouteContext) {
  const tone = computeSystemTone(snapshot);
  const leadObservation = snapshot.review?.derived_observations[0] ?? null;
  const review = snapshot.review;
  const telemetry = snapshot.telemetry;
  const controlPlane = snapshot.controlPlane;

  let headline = "Awaiting a fresh operating picture.";
  if (leadObservation) {
    headline = leadObservation.label;
  } else if (review) {
    headline = tone === "positive" ? "System operating within expected bounds." : "Signals are mixed; review key exceptions.";
  }

  let detail = `Context: ${routeLabel(context)}.`;
  if (context === "operate" && review) {
    detail = `Open risk ${formatPercent(review.facts.open_risk_percent)} across ${formatCount("position", review.facts.open_positions_count)}.`;
  } else if (context === "control-plane" && controlPlane) {
    detail = `${formatCount("misalignment", controlPlane.misaligned_count)} across ${formatCount("family", controlPlane.families.length)}.`;
  } else if (context === "coverage" && snapshot.coverage) {
    detail = `${formatCount("tier 1 instrument", snapshot.coverage.streaming.active_instruments.length)} active with ${formatCount("pending promotion", snapshot.coverage.promotions.pending_count)}.`;
  } else if (context === "events" && snapshot.events[0]) {
    detail = `Latest event: ${snapshot.events[0].title}.`;
  } else if (context === "strategies" && snapshot.strategies.length) {
    const runningCount = snapshot.strategies.filter((strategy) => strategy.status === "RUNNING").length;
    detail = `${formatCount("running strategy", runningCount)} across ${formatCount("strategy", snapshot.strategies.length)} configured.`;
  } else if (telemetry) {
    detail = `Heartbeat ${telemetry.heartbeat_age_ms != null ? `${Math.round(telemetry.heartbeat_age_ms / 1000)}s old` : "age unavailable"}.`;
  }

  const indicators = [
    {
      label: "Status",
      value: STATUS_LABEL[tone],
    },
    {
      label: "Warnings",
      value: String(snapshot.review?.warnings.length ?? 0),
    },
    {
      label: context === "operate" ? "Open Risk" : context === "control-plane" ? "Mismatches" : "Freshness",
      value:
        context === "operate"
          ? review
            ? formatPercent(review.facts.open_risk_percent)
            : "n/a"
          : context === "control-plane"
            ? String(controlPlane?.misaligned_count ?? 0)
            : telemetry?.stream_last_tick_at
              ? formatRelativeDuration(telemetry.stream_last_tick_at)
              : "n/a",
    },
  ];

  return {
    tone,
    headline,
    detail,
    indicators,
  };
}

function buildWhatMatters(snapshot: AimeeSnapshot, context: RouteContext): OverviewCard[] {
  const review = snapshot.review;
  const telemetry = snapshot.telemetry;
  const controlPlane = snapshot.controlPlane;
  const coverage = snapshot.coverage;

  if (context === "operate" && review) {
    return [
      {
        id: "operate-risk",
        title: "Risk concentration",
        detail:
          review.facts.main_open_risk !== null && review.facts.main_open_risk !== undefined
            ? `${review.facts.main_open_risk.strategy_name} on ${review.facts.main_open_risk.instrument} holds ${formatPercent(review.facts.main_open_risk.share_of_open_risk_percent ?? review.facts.largest_risk_share_percent)} of open risk.`
            : "Open risk is distributed with no single dominant exposure identified.",
        meta: `${formatPercent(review.facts.open_risk_percent)} open risk`,
        tone: review.facts.largest_risk_share_percent >= 50 ? "warning" : "neutral",
      },
      {
        id: "operate-pnl",
        title: "PnL session",
        detail: `Daily PnL is ${formatSignedCurrency(review.facts.daily_pnl)}${review.facts.daily_pnl_percent !== null && review.facts.daily_pnl_percent !== undefined ? ` (${formatPercent(review.facts.daily_pnl_percent)})` : ""}.`,
        meta: review.facts.account_value !== null && review.facts.account_value !== undefined ? `Account value ${formatCurrency(review.facts.account_value)}` : undefined,
        tone: review.facts.daily_pnl < 0 ? "warning" : "positive",
      },
      {
        id: "operate-exec",
        title: "Execution health",
        detail: `${formatCount("failure", review.facts.execution_failures_24h)} and ${formatCount("risk rejection", review.facts.risk_rejections_24h)} over the last 24h.`,
        meta: telemetry ? `${formatCount("reconciliation issue", telemetry.reconciliation_mismatches)} live` : undefined,
        tone: review.facts.execution_failures_24h > 0 ? "warning" : "neutral",
      },
      {
        id: "operate-stream",
        title: "Market data freshness",
        detail: telemetry?.stream_last_tick_at ? `Last live tick ${formatRelativeDuration(telemetry.stream_last_tick_at)} ago.` : "Stream freshness is unavailable.",
        meta: telemetry?.stream_connected ? "Streaming connected" : "Streaming disconnected",
        tone: telemetry?.stream_connected ? "positive" : "negative",
      },
    ];
  }

  if (context === "control-plane" && controlPlane) {
    const blockedFamilies = controlPlane.families.filter((family) => family.deployment?.state === "BLOCKED");
    const degradedFamilies = controlPlane.families.filter((family) => family.deployment?.state === "DEGRADED");
    return [
      {
        id: "cp-mismatch",
        title: "Governance alignment",
        detail: `${formatCount("family", controlPlane.misaligned_count)} currently misaligned with intended deployment or runtime state.`,
        meta: controlPlane.effective_autonomous_control_enabled ? "Autonomy effective" : "Autonomy constrained",
        tone: controlPlane.misaligned_count > 0 ? "warning" : "positive",
      },
      {
        id: "cp-blocked",
        title: "Blocked families",
        detail: blockedFamilies.length
          ? blockedFamilies.slice(0, 2).map((family) => family.strategy_name).join(", ")
          : "No families are blocked.",
        meta: String(blockedFamilies.length),
        tone: blockedFamilies.length ? "negative" : "neutral",
      },
      {
        id: "cp-degraded",
        title: "Degraded deployment",
        detail: degradedFamilies.length
          ? degradedFamilies.slice(0, 2).map((family) => family.strategy_name).join(", ")
          : "No degraded families detected.",
        meta: String(degradedFamilies.length),
        tone: degradedFamilies.length ? "warning" : "positive",
      },
      {
        id: "cp-runtime",
        title: "Runtime intent",
        detail: `${formatCount("family", controlPlane.families.filter((family) => family.runtime.is_running).length)} currently running.`,
        meta: `${formatCount("family", controlPlane.families.length)} tracked`,
        tone: "neutral",
      },
    ];
  }

  if (context === "coverage" && coverage) {
    return [
      {
        id: "cov-tier1",
        title: "Tier 1 allocation",
        detail: `${formatCount("active instrument", coverage.streaming.active_instruments.length)} in Tier 1.`,
        meta: `${formatCount("desired instrument", coverage.streaming.desired_instruments.length)} targeted`,
        tone: "neutral",
      },
      {
        id: "cov-promo",
        title: "Promotion pressure",
        detail: `${formatCount("pending promotion", coverage.promotions.pending_count)} pending; ${formatCount("accepted promotion", coverage.promotions.accepted_count)} accepted recently.`,
        meta: `${formatCount("expired promotion", coverage.promotions.expired_count)} expired`,
        tone: coverage.promotions.pending_count > 0 ? "warning" : "positive",
      },
      {
        id: "cov-cap",
        title: "Capacity limits",
        detail: coverage.streaming.capped_instruments.length
          ? `${coverage.streaming.capped_instruments.slice(0, 3).join(", ")} are at cap.`
          : "No instruments are currently capped.",
        meta: `${Object.keys(coverage.streaming.asset_class_usage).length} asset classes active`,
        tone: coverage.streaming.capped_instruments.length ? "warning" : "neutral",
      },
      {
        id: "cov-allocator",
        title: "Allocator selectivity",
        detail: `${formatCount("selection", coverage.trade_allocator.selected_count)} vs ${formatCount("rejection", coverage.trade_allocator.rejected_count)} in recent allocator decisions.`,
        meta: Object.entries(coverage.trade_allocator.reason_counts)[0]?.[0]?.replaceAll("_", " ") ?? "No dominant reject reason",
        tone: coverage.trade_allocator.rejected_count > coverage.trade_allocator.selected_count ? "warning" : "neutral",
      },
    ];
  }

  if (context === "events") {
    const recentWarnings = snapshot.events.filter((event) => event.severity !== "info");
    return [
      {
        id: "events-latest",
        title: "Latest anomaly",
        detail: snapshot.events[0] ? snapshot.events[0].title : "No recent anomaly events.",
        meta: snapshot.events[0]?.created_at ? formatDateTime(snapshot.events[0].created_at) : undefined,
        tone: toneFromWarningSeverity(snapshot.events[0]?.severity),
      },
      {
        id: "events-volume",
        title: "Signal density",
        detail: `${formatCount("warning or error event", recentWarnings.length)} in the latest event window.`,
        meta: `${formatCount("event", snapshot.events.length)} loaded`,
        tone: recentWarnings.length > 0 ? "warning" : "positive",
      },
      {
        id: "events-recon",
        title: "Operational fault lines",
        detail: `${formatCount("reconciliation issue", snapshot.telemetry?.reconciliation_mismatches ?? 0)} and ${formatCount("order failure", snapshot.telemetry?.order_failures_last_5m ?? 0)} live.`,
        meta: snapshot.telemetry?.stream_connected ? "Stream connected" : "Stream disconnected",
        tone: (snapshot.telemetry?.reconciliation_mismatches ?? 0) > 0 || (snapshot.telemetry?.order_failures_last_5m ?? 0) > 0 ? "negative" : "neutral",
      },
      {
        id: "events-route",
        title: "Current route focus",
        detail: "AIMEE is prioritizing anomaly interpretation, event clustering, and recent state transitions.",
        tone: "neutral",
      },
    ];
  }

  if (context === "strategies") {
    const runningCount = snapshot.strategies.filter((strategy) => strategy.status === "RUNNING").length;
    const warningStrategies = snapshot.strategies.filter((strategy) => strategy.warning_message);
    return [
      {
        id: "str-running",
        title: "Runtime coverage",
        detail: `${formatCount("running strategy", runningCount)}; ${formatCount("stale runtime", snapshot.telemetry?.stale_runtime_count ?? 0)} flagged.`,
        meta: `${formatCount("configured strategy", snapshot.strategies.length)} total`,
        tone: runningCount > 0 ? "neutral" : "warning",
      },
      {
        id: "str-warning",
        title: "Strategy warnings",
        detail: warningStrategies.length
          ? warningStrategies.slice(0, 2).map((strategy) => strategy.name).join(", ")
          : "No strategy-level warnings are currently surfaced.",
        meta: String(warningStrategies.length),
        tone: warningStrategies.length ? "warning" : "positive",
      },
      {
        id: "str-health",
        title: "Health pauses",
        detail: `${formatCount("strategy paused by health", snapshot.telemetry?.strategies_paused_by_health ?? 0)} right now.`,
        meta: `${formatCount("order rejection", snapshot.telemetry?.rejected_orders_last_5m ?? 0)} in the last 5m`,
        tone: (snapshot.telemetry?.strategies_paused_by_health ?? 0) > 0 ? "warning" : "neutral",
      },
      {
        id: "str-review",
        title: "Reviewer lead",
        detail: snapshot.review?.derived_observations[0]?.label ?? "No lead reviewer observation is currently available.",
        tone: toneFromWarningSeverity(snapshot.review?.derived_observations[0]?.severity),
      },
    ];
  }

  return [
    {
      id: "general-status",
      title: "System status",
      detail: buildSystemSummary(snapshot, context).headline,
      meta: snapshot.updatedAt ? `Updated ${formatDateTime(snapshot.updatedAt)}` : undefined,
      tone: computeSystemTone(snapshot),
    },
    {
      id: "general-review",
      title: "Reviewer signal",
      detail: snapshot.review?.derived_observations[0]?.detail ?? "No current reviewer explanation available.",
      tone: toneFromWarningSeverity(snapshot.review?.derived_observations[0]?.severity),
    },
  ];
}

function buildWarningItems(snapshot: AimeeSnapshot): WarningItem[] {
  const items: WarningItem[] = [];

  snapshot.review?.warnings.forEach((warning) => {
    items.push({
      id: `review-${warning.code}`,
      title: warning.message,
      detail: "Reviewer warning",
      tone: toneFromWarningSeverity(warning.severity),
    });
  });

  snapshot.controlPlane?.families
    .filter((family) => family.deployment?.state === "BLOCKED" || family.deployment?.state === "DEGRADED")
    .slice(0, 3)
    .forEach((family) => {
      items.push({
        id: `family-${family.strategy_name}`,
        title: `${family.strategy_name} ${family.deployment?.state?.toLowerCase() ?? "changed"}`,
        detail: family.deployment?.blocked_reason ?? family.deployment?.degraded_reason ?? family.alignment.reason,
        tone: family.deployment?.state === "BLOCKED" ? "negative" : "warning",
      });
    });

  if (snapshot.telemetry) {
    if (!snapshot.telemetry.stream_connected) {
      items.push({
        id: "stream-disconnected",
        title: "Market-data stream disconnected",
        detail: "Live ticks are unavailable or stale.",
        tone: "negative",
      });
    }
    if (snapshot.telemetry.reconciliation_mismatches > 0) {
      items.push({
        id: "reconciliation",
        title: "Reconciliation mismatches detected",
        detail: formatCount("mismatch", snapshot.telemetry.reconciliation_mismatches),
        tone: "warning",
      });
    }
  }

  return items.slice(0, 5);
}

function buildRecentChanges(snapshot: AimeeSnapshot): ChangeItem[] {
  const historyItems = snapshot.history.slice(0, 2).map((item) => ({
    id: `history-${item.review_id}`,
    title: `Operator summary refreshed`,
    detail: `Mode ${item.generation_mode === "deterministic_plus_llm" ? "AI-assisted" : "deterministic"} for review #${item.review_id}.`,
    at: item.generated_at,
  }));

  const eventItems = snapshot.events.slice(0, 3).map((event) => ({
    id: `event-${event.id}`,
    title: event.title,
    detail: event.message ?? `${event.category} event`,
    at: event.created_at,
  }));

  return [...eventItems, ...historyItems]
    .sort((left, right) => new Date(right.at ?? 0).getTime() - new Date(left.at ?? 0).getTime())
    .slice(0, 4);
}

function reviewResponseSummary(response: OperationalQuestionReviewResponse) {
  if (response.ai_summary?.summary) {
    return response.ai_summary.summary;
  }
  if (response.derived_observations[0]?.detail) {
    return response.derived_observations[0].detail;
  }
  return "No grounded answer is available yet.";
}

async function loadSnapshot(): Promise<AimeeSnapshot> {
  const [review, history, controlPlane, coverage, dashboard, telemetry, events, strategies] = await Promise.allSettled([
    getOperatorSummaryReview(),
    getReviewHistory("operator_summary", 6),
    getControlPlaneSummary(),
    getCoverageSummary(),
    getDashboardSnapshot(),
    getOperationalTelemetry(),
    getDomainEvents({ limit: 8 }),
    getStrategies(),
  ]);

  return {
    review: review.status === "fulfilled" ? review.value : null,
    history: history.status === "fulfilled" ? history.value : [],
    controlPlane: controlPlane.status === "fulfilled" ? controlPlane.value : null,
    coverage: coverage.status === "fulfilled" ? coverage.value : null,
    dashboard: dashboard.status === "fulfilled" ? dashboard.value : null,
    telemetry: telemetry.status === "fulfilled" ? telemetry.value : null,
    events: events.status === "fulfilled" ? events.value : [],
    strategies: strategies.status === "fulfilled" ? strategies.value : [],
    updatedAt: new Date().toISOString(),
  };
}

function buildSnapshotSignature(snapshot: AimeeSnapshot) {
  return JSON.stringify({
    leadObservation: snapshot.review?.derived_observations[0]?.code ?? null,
    warnings: snapshot.review?.warnings.map((warning) => `${warning.code}:${warning.severity}`) ?? [],
    misalignedCount: snapshot.controlPlane?.misaligned_count ?? 0,
    blockedFamilies:
      snapshot.controlPlane?.families
        .filter((family) => family.deployment?.state === "BLOCKED" || family.deployment?.state === "DEGRADED")
        .map((family) => `${family.strategy_name}:${family.deployment?.state}`)
        .sort() ?? [],
    streamConnected: snapshot.telemetry?.stream_connected ?? null,
    reconciliationMismatches: snapshot.telemetry?.reconciliation_mismatches ?? 0,
    latestEvent: snapshot.events[0]?.id ?? null,
  });
}

function toneClasses(tone: Tone) {
  if (tone === "positive") {
    return "border-[color:color-mix(in_srgb,var(--positive)_35%,var(--border))] bg-[color:var(--positive-soft)] text-[color:var(--positive)]";
  }
  if (tone === "warning") {
    return "border-[color:color-mix(in_srgb,var(--warning)_38%,var(--border))] bg-[color:var(--warning-soft)] text-[color:var(--warning)]";
  }
  if (tone === "negative") {
    return "border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))] bg-[color:var(--negative-soft)] text-[color:var(--negative)]";
  }
  return "border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)]";
}

function toneTextClass(tone: Tone) {
  if (tone === "positive") {
    return "text-[color:var(--positive)]";
  }
  if (tone === "warning") {
    return "text-[color:var(--warning)]";
  }
  if (tone === "negative") {
    return "text-[color:var(--negative)]";
  }
  return "text-[color:var(--text-secondary)]";
}

export function AimeeShell() {
  const pathname = usePathname();
  const context = routeContextFromPath(pathname);
  const [isOpen, setIsOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<AimeeSnapshot>({
    review: null,
    history: [],
    controlPlane: null,
    coverage: null,
    dashboard: null,
    telemetry: null,
    events: [],
    strategies: [],
    updatedAt: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isOverviewExpanded, setIsOverviewExpanded] = useState(true);
  const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false);
  const [hasAttentionPulse, setHasAttentionPulse] = useState(false);
  const lastSignatureRef = useRef<string | null>(null);
  const panelScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async (initial = false) => {
      if (initial) {
        setIsLoading(true);
      }

      try {
        const nextSnapshot = await loadSnapshot();
        if (cancelled) {
          return;
        }

        setSnapshot(nextSnapshot);
        setLoadingError(null);

        const nextSignature = buildSnapshotSignature(nextSnapshot);
        if (lastSignatureRef.current && lastSignatureRef.current !== nextSignature && !isOpen) {
          setHasAttentionPulse(true);
        }
        lastSignatureRef.current = nextSignature;
      } catch (error) {
        if (!cancelled) {
          setLoadingError(error instanceof Error ? error.message : "Failed to load AIMEE context.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void refresh(true);
    const intervalId = window.setInterval(() => {
      void refresh(false);
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setHasAttentionPulse(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const { body, documentElement } = document;
    const previousBodyOverflow = body.style.overflow;
    const previousHtmlOverflow = documentElement.style.overflow;

    body.style.overflow = "hidden";
    documentElement.style.overflow = "hidden";

    return () => {
      body.style.overflow = previousBodyOverflow;
      documentElement.style.overflow = previousHtmlOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    const container = panelScrollRef.current;
    if (!container || hasAutoCollapsed || !isOverviewExpanded) {
      return;
    }

    if (container.scrollHeight > container.clientHeight + 24 && messages.length >= 2) {
      setIsOverviewExpanded(false);
      setHasAutoCollapsed(true);
    }
  }, [hasAutoCollapsed, isOverviewExpanded, messages]);

  useEffect(() => {
    const container = panelScrollRef.current;
    if (!container) {
      return;
    }

    container.scrollTo({
      top: container.scrollHeight,
      behavior: messages.length > 2 ? "smooth" : "auto",
    });
  }, [messages]);

  const systemSummary = useMemo(() => buildSystemSummary(snapshot, context), [context, snapshot]);
  const whatMatters = useMemo(() => buildWhatMatters(snapshot, context), [context, snapshot]);
  const warningItems = useMemo(() => buildWarningItems(snapshot), [snapshot]);
  const recentChanges = useMemo(() => buildRecentChanges(snapshot), [snapshot]);
  const suggestedQuestions = SUGGESTED_QUESTIONS[context];

  const submitQuestion = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    const timestamp = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: `${timestamp}-user`,
      role: "user",
      createdAt: timestamp,
      question: trimmed,
    };
    const assistantMessage: ChatMessage = {
      id: `${timestamp}-assistant`,
      role: "assistant",
      createdAt: timestamp,
      question: trimmed,
      status: "loading",
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setInputValue("");
    setIsOpen(true);

    try {
      const response = await askOperationalQuestion({ question: trimmed });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                status: "ready",
                response,
              }
            : message,
        ),
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                status: "error",
                error: error instanceof Error ? error.message : "AIMEE could not answer that question.",
              }
            : message,
        ),
      );
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitQuestion(inputValue);
  };

  const attentionCount = warningItems.length;
  const compactMetric =
    context === "operate"
      ? snapshot.review
        ? `${formatPercent(snapshot.review.facts.open_risk_percent)} risk`
        : "Risk n/a"
      : context === "control-plane"
        ? `${snapshot.controlPlane?.misaligned_count ?? 0} mismatches`
        : `${attentionCount} warnings`;

  return (
    <>
      <div
        className={joinClasses(
          "pointer-events-none fixed inset-0 z-40",
          isOpen ? "opacity-100" : "opacity-0",
        )}
        aria-hidden={!isOpen}
      >
        <button
          type="button"
          className={joinClasses(
            "absolute inset-0 bg-[rgba(6,18,28,0.18)] backdrop-blur-[6px] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),inset_0_0_140px_rgba(6,18,28,0.12)] transition-opacity duration-200 max-[920px]:bg-[rgba(6,18,28,0.32)] max-[920px]:backdrop-blur-[8px]",
            isOpen ? "pointer-events-auto opacity-100" : "opacity-0",
          )}
          onClick={() => setIsOpen(false)}
          tabIndex={isOpen ? 0 : -1}
          aria-label="Close AIMEE panel"
        />
        <aside
          className={joinClasses(
            "pointer-events-auto absolute right-0 top-0 flex h-full w-full max-w-[560px] flex-col border-l border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_95%,transparent)] shadow-[var(--shadow-raised)] backdrop-blur-[20px] transition-transform duration-200 ease-out max-[920px]:top-auto max-[920px]:h-[86vh] max-[920px]:rounded-t-[28px] max-[920px]:border-l-0 max-[920px]:border-t",
            isOpen ? "translate-x-0 max-[920px]:translate-y-0" : "translate-x-full max-[920px]:translate-y-full",
          )}
          aria-label="AIMEE operator assistant"
          onWheel={(event) => event.stopPropagation()}
          onTouchMove={(event) => event.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-4 border-b border-[color:var(--border)] px-5 py-4">
            <div className="flex min-w-0 items-start gap-3">
              <div className="relative mt-1 flex h-11 w-11 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--glass-stroke))] bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--accent)_22%,transparent),transparent_60%),linear-gradient(180deg,color-mix(in_srgb,var(--bg-surface-strong)_90%,transparent),color-mix(in_srgb,var(--bg-surface)_86%,transparent))] shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_0_26px_color-mix(in_srgb,var(--accent)_20%,transparent)]">
                <span className="absolute h-7 w-7 animate-pulse rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--accent)_60%,transparent),transparent_72%)]" />
                <span className="relative h-3 w-3 rounded-full bg-[color:var(--accent)] shadow-[0_0_0_6px_color-mix(in_srgb,var(--accent)_12%,transparent)]" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[1.04rem] font-semibold tracking-[-0.02em]">AIMEE</h2>
                  <span className="rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] px-2 py-1 text-[0.66rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
                    Read-only system intelligence
                  </span>
                </div>
                <p className="mt-1 text-[0.8rem] text-[color:var(--text-secondary)]">
                  Autonomous Intelligence for Market Explanation &amp; Evaluation
                </p>
                <p className="mt-2 text-[0.76rem] text-[color:var(--text-tertiary)]">Focused on {routeLabel(context)} context.</p>
              </div>
            </div>
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              onClick={() => setIsOpen(false)}
              aria-label="Close AIMEE"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
                <path d="M5.22 5.22a.75.75 0 0 1 1.06 0L10 8.94l3.72-3.72a.75.75 0 1 1 1.06 1.06L11.06 10l3.72 3.72a.75.75 0 0 1-1.06 1.06L10 11.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06L8.94 10 5.22 6.28a.75.75 0 0 1 0-1.06Z" fill="currentColor" />
              </svg>
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-5 pb-5">
            <div ref={panelScrollRef} className="min-h-0 flex-1 overflow-y-auto pr-1">
              <div className="flex min-h-full flex-col gap-4 pt-4">
                <section className="sticky top-0 z-10 -mx-5 border-b border-transparent bg-[color:color-mix(in_srgb,var(--bg-shell)_94%,transparent)] px-5 pb-3 backdrop-blur-[8px]">
                  <div className="flex items-center justify-between gap-3 rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface-muted)] px-3 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={joinClasses("h-2.5 w-2.5 rounded-full", systemSummary.tone === "positive" ? "bg-[color:var(--positive)]" : systemSummary.tone === "warning" ? "bg-[color:var(--warning)]" : systemSummary.tone === "negative" ? "bg-[color:var(--negative)]" : "bg-[color:var(--accent)]")} />
                        <span className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">{STATUS_LABEL[systemSummary.tone]}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <strong className="text-[0.95rem] tracking-[-0.02em]">{systemSummary.headline}</strong>
                        <span className="text-[0.78rem] text-[color:var(--text-secondary)]">{compactMetric}</span>
                        <span className="text-[0.78rem] text-[color:var(--text-secondary)]">{attentionCount} active warnings</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)] transition-transform hover:text-[color:var(--text-primary)]"
                      onClick={() => setIsOverviewExpanded((value) => !value)}
                      aria-expanded={isOverviewExpanded}
                      aria-label={isOverviewExpanded ? "Collapse AIMEE overview" : "Expand AIMEE overview"}
                    >
                      <svg viewBox="0 0 20 20" className={joinClasses("h-4 w-4 transition-transform duration-200", isOverviewExpanded ? "rotate-180" : "rotate-0")} aria-hidden="true">
                        <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.09l3.71-3.86a.75.75 0 0 1 1.08 1.04l-4.25 4.42a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" fill="currentColor" />
                      </svg>
                    </button>
                  </div>
                </section>

                {isOverviewExpanded ? (
                  <div className="flex flex-col gap-2">
                    <section className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] p-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">System Overview</div>
                          <div className="mt-2 text-[1rem] font-semibold tracking-[-0.02em]">{systemSummary.headline}</div>
                          <p className="mt-1 text-[0.84rem] text-[color:var(--text-secondary)]">{systemSummary.detail}</p>
                        </div>
                        <span className={joinClasses("text-[0.72rem] font-medium uppercase tracking-[0.08em]", toneTextClass(systemSummary.tone))}>
                          {STATUS_LABEL[systemSummary.tone]}
                        </span>
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        {systemSummary.indicators.map((indicator) => (
                          <div key={indicator.label} className="rounded-[10px] border border-[color:var(--border)] bg-[color:transparent] px-3 py-2">
                            <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">{indicator.label}</div>
                            <div className="mt-1 text-[0.92rem] font-semibold">{indicator.value}</div>
                          </div>
                        ))}
                      </div>
                    </section>

                    <section>
                      <div className="mb-2 flex items-center justify-between">
                        <h3 className="text-[0.78rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">What Matters Now</h3>
                        {snapshot.updatedAt ? <span className="text-[0.74rem] text-[color:var(--text-tertiary)]">Updated {formatDateTime(snapshot.updatedAt)}</span> : null}
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {whatMatters.map((item) => (
                          <article key={item.id} className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] p-3">
                            <div className="flex items-center justify-between gap-2">
                              <h4 className="text-[0.88rem] font-semibold tracking-[-0.01em]">{item.title}</h4>
                              <span className={joinClasses("text-[0.66rem] uppercase tracking-[0.08em]", toneTextClass(item.tone))}>
                                {item.tone}
                              </span>
                            </div>
                            <p className="mt-2 text-[0.8rem] text-[color:var(--text-secondary)]">{item.detail}</p>
                            {item.meta ? <div className="mt-2 text-[0.74rem] text-[color:var(--text-tertiary)]">{item.meta}</div> : null}
                          </article>
                        ))}
                      </div>
                    </section>

                    <section>
                      <h3 className="mb-2 text-[0.78rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Active Warnings / Risks</h3>
                      <div className="grid gap-2">
                        {warningItems.length ? (
                          warningItems.map((warning) => (
                            <article
                              key={warning.id}
                              className={joinClasses(
                                "rounded-[12px] border bg-[color:var(--bg-surface)] p-3",
                                warning.tone === "positive" && "border-[color:color-mix(in_srgb,var(--positive)_35%,var(--border))]",
                                warning.tone === "warning" && "border-[color:color-mix(in_srgb,var(--warning)_38%,var(--border))]",
                                warning.tone === "negative" && "border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))]",
                                warning.tone === "neutral" && "border-[color:var(--border)]",
                              )}
                            >
                              <div className="text-[0.84rem] font-semibold">{warning.title}</div>
                              <div className={joinClasses("mt-1 text-[0.76rem]", toneTextClass(warning.tone))}>{warning.detail}</div>
                            </article>
                          ))
                        ) : (
                          <div className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] px-3 py-3 text-[0.8rem] text-[color:var(--text-secondary)]">
                            No high-signal warnings are currently active.
                          </div>
                        )}
                      </div>
                    </section>

                    <section className="grid gap-3 sm:grid-cols-[1.2fr_0.8fr]">
                      <div>
                        <h3 className="mb-2 text-[0.78rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Recent Changes</h3>
                        <div className="grid gap-2">
                          {recentChanges.length ? (
                            recentChanges.map((change) => (
                              <article key={change.id} className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] px-3 py-3">
                                <div className="flex items-center justify-between gap-3">
                                  <div className="text-[0.82rem] font-semibold">{change.title}</div>
                                  {change.at ? <div className="text-[0.72rem] text-[color:var(--text-tertiary)]">{formatDateTime(change.at)}</div> : null}
                                </div>
                                <p className="mt-1 text-[0.76rem] text-[color:var(--text-secondary)]">{change.detail}</p>
                              </article>
                            ))
                          ) : (
                            <div className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] px-3 py-3 text-[0.8rem] text-[color:var(--text-secondary)]">
                              No recent changes available.
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <h3 className="mb-2 text-[0.78rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Suggested Questions</h3>
                        <div className="flex flex-wrap gap-2">
                          {suggestedQuestions.map((question) => (
                            <button
                              key={question}
                              type="button"
                              className="rounded-[10px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] px-3 py-2 text-left text-[0.76rem] text-[color:var(--text-secondary)] transition-colors duration-150 hover:bg-[color:var(--bg-muted)] hover:text-[color:var(--text-primary)]"
                              onClick={() => void submitQuestion(question)}
                            >
                              {question}
                            </button>
                          ))}
                        </div>
                      </div>
                    </section>
                  </div>
                ) : null}

                <section className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-[0.82rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Reasoning Layer</h3>
                      <p className="mt-1 text-[0.78rem] text-[color:var(--text-secondary)]">Ask for explanation, grounding, and operator guidance. AIMEE remains read-only.</p>
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 pb-1">
                    {isLoading ? (
                      <div className="rounded-[18px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] px-4 py-3 text-[0.84rem] text-[color:var(--text-secondary)] shadow-[var(--shadow-soft)]">
                        AIMEE is refreshing system context.
                      </div>
                    ) : null}
                    {loadingError ? (
                      <div className="rounded-[18px] border border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))] bg-[color:var(--negative-soft)] px-4 py-3 text-[0.84rem] text-[color:var(--negative)] shadow-[var(--shadow-soft)]">
                        {loadingError}
                      </div>
                    ) : null}

                  {messages.length === 0 ? (
                    <div className="rounded-[20px] border border-dashed border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-4 py-4 text-[0.84rem] text-[color:var(--text-secondary)]">
                      Use the suggested questions above or ask AIMEE to explain current state, warnings, exposure, or recent changes.
                    </div>
                  ) : (
                    messages.map((message) =>
                      message.role === "user" ? (
                        <article key={message.id} className="ml-auto max-w-[88%] rounded-[18px] border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--border))] bg-[color:var(--accent-soft)] px-4 py-3 text-[0.84rem] shadow-[var(--shadow-soft)]">
                          <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Operator</div>
                          <div className="mt-1 font-medium text-[color:var(--text-primary)]">{message.question}</div>
                        </article>
                      ) : (
                        <article key={message.id} className="max-w-[96%] rounded-[20px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface)] px-4 py-4 shadow-[var(--shadow-panel)]">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">AIMEE</div>
                            <div className="text-[0.72rem] text-[color:var(--text-tertiary)]">
                              {message.status === "loading" ? "Thinking" : formatDateTime(message.createdAt)}
                            </div>
                          </div>
                          {message.status === "loading" ? (
                            <div className="mt-2 text-[0.84rem] text-[color:var(--text-secondary)]">Interpreting current system state for that question.</div>
                          ) : message.status === "error" ? (
                            <div className="mt-2 rounded-[14px] border border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))] bg-[color:var(--negative-soft)] px-3 py-3 text-[0.82rem] text-[color:var(--negative)]">
                              {message.error ?? "AIMEE could not answer that question."}
                            </div>
                          ) : message.response ? (
                            <div className="mt-3 grid gap-3">
                              <div>
                                <div className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Answer</div>
                                <p className="mt-1 text-[0.86rem] text-[color:var(--text-primary)]">{reviewResponseSummary(message.response)}</p>
                              </div>

                              {message.response.derived_observations.length ? (
                                <div className="grid gap-2">
                                  {message.response.derived_observations.slice(0, 3).map((observation) => (
                                    <div key={observation.code} className="rounded-[14px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-3">
                                      <div className="flex items-center justify-between gap-2">
                                        <div className="text-[0.82rem] font-semibold">{observation.label}</div>
                                        <span className={joinClasses("rounded-full border px-2 py-[5px] text-[0.64rem] uppercase tracking-[0.08em]", toneClasses(toneFromWarningSeverity(observation.severity)))}>
                                          {observation.severity}
                                        </span>
                                      </div>
                                      <p className="mt-1 text-[0.76rem] text-[color:var(--text-secondary)]">{observation.detail}</p>
                                    </div>
                                  ))}
                                </div>
                              ) : null}

                              {message.response.supporting_metrics.length ? (
                                <div className="grid grid-cols-2 gap-2">
                                  {message.response.supporting_metrics.slice(0, 4).map((metric) => (
                                    <div key={metric.key} className="rounded-[14px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-2">
                                      <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">{metric.label}</div>
                                      <div className="mt-1 text-[0.84rem] font-semibold">
                                        {typeof metric.value === "number"
                                          ? metric.unit === "pct"
                                            ? formatMetricValue(metric.value, "percent")
                                            : formatMetricValue(metric.value, "count")
                                          : String(metric.value ?? "n/a")}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : null}

                              {message.response.warnings.length ? (
                                <div className="flex flex-wrap gap-2">
                                  {message.response.warnings.map((warning) => (
                                    <span key={warning.code} className={joinClasses("rounded-full border px-3 py-[7px] text-[0.7rem]", toneClasses(toneFromWarningSeverity(warning.severity)))}>
                                      {warning.message}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </article>
                      ),
                    )
                  )}
                  </div>
                </section>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="mt-3 flex-none rounded-[20px] border border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_96%,transparent)] p-3 shadow-[var(--shadow-panel)] backdrop-blur-[16px]">
              <div className="flex items-end gap-2">
                <label className="flex-1">
                  <span className="sr-only">Ask AIMEE a system question</span>
                  <textarea
                    value={inputValue}
                    onChange={(event) => setInputValue(event.target.value)}
                    rows={2}
                    placeholder="Ask AIMEE to explain the current system state..."
                    className="min-h-[72px] w-full resize-none rounded-[16px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-3 text-[0.84rem] text-[color:var(--text-primary)] outline-none transition-colors placeholder:text-[color:var(--text-tertiary)] focus:border-[color:color-mix(in_srgb,var(--accent)_36%,var(--glass-stroke))]"
                  />
                </label>
                <button
                  type="submit"
                  className="inline-flex h-11 shrink-0 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_32%,var(--border))] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--accent-soft)_70%,white_18%),color-mix(in_srgb,var(--accent-soft)_94%,transparent))] px-4 text-[0.82rem] font-semibold text-[color:var(--text-primary)] shadow-[var(--shadow-soft)] transition-transform duration-150 hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!inputValue.trim()}
                >
                  Ask
                </button>
              </div>
            </form>
          </div>
        </aside>
      </div>

      <button
        type="button"
        className="fixed right-4 bottom-4 z-30 flex items-center gap-3 rounded-full border border-[color:var(--glass-stroke)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--bg-surface-strong)_94%,transparent),color-mix(in_srgb,var(--bg-surface)_92%,transparent))] px-4 py-3 text-[color:var(--text-primary)] shadow-[var(--shadow-panel)] backdrop-blur-[18px] transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-[var(--shadow-raised)] max-[920px]:right-3 max-[920px]:bottom-3 max-[920px]:px-3"
        onClick={() => setIsOpen(true)}
        aria-label="Open AIMEE assistant"
      >
        <span className="relative flex h-9 w-9 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--glass-stroke))] bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--accent)_20%,transparent),transparent_62%),linear-gradient(180deg,#16304a,#0c131a)] shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]">
          <span className="absolute h-5 w-5 animate-pulse rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--accent)_70%,transparent),transparent_72%)]" />
          <span className="relative h-2.5 w-2.5 rounded-full bg-[color:var(--accent)]" />
          {hasAttentionPulse || attentionCount > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center">
              <span className="absolute h-3.5 w-3.5 animate-ping rounded-full bg-[color:var(--warning)] opacity-60" />
              <span className={joinClasses("relative h-2.5 w-2.5 rounded-full border border-[color:var(--bg-surface-strong)]", attentionCount > 0 ? "bg-[color:var(--warning)]" : "bg-[color:var(--accent)]")} />
            </span>
          ) : null}
        </span>
        <span className="flex min-w-0 flex-col items-start">
          <span className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">AIMEE</span>
          <span className="max-w-[160px] overflow-hidden text-ellipsis whitespace-nowrap text-[0.88rem] font-semibold tracking-[-0.01em]">
            {STATUS_LABEL[systemSummary.tone]}
          </span>
        </span>
      </button>
    </>
  );
}
