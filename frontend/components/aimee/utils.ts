import { formatCurrency, formatPercent, formatRelativeDuration, formatSignedCurrency } from "@/lib/format";
import type { OperationalQuestionReviewResponse } from "@/lib/types";

import type { AimeeSnapshot, ChangeItem, OverviewCard, RouteContext, Tone, WarningItem } from "@/components/aimee/types";

export const SUGGESTED_QUESTIONS: Record<RouteContext, string[]> = {
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

export const STATUS_LABEL: Record<Tone, string> = {
  positive: "Healthy",
  warning: "Degraded",
  negative: "Attention Needed",
  neutral: "Monitoring",
};

export function joinClasses(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function formatDateTime(value?: string | null) {
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

export function formatCount(label: string, count: number) {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

export function formatMetricValue(value?: number | null, kind: "currency" | "percent" | "count" = "count") {
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

export function toneFromWarningSeverity(severity?: string): Tone {
  if (severity === "critical" || severity === "error") {
    return "negative";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}

export function routeContextFromPath(pathname: string): RouteContext {
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

export function routeLabel(context: RouteContext) {
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

export function computeSystemTone(snapshot: AimeeSnapshot): Tone {
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

export function buildSystemSummary(snapshot: AimeeSnapshot, context: RouteContext) {
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

  return {
    tone,
    headline,
    detail,
    indicators: [
      { label: "Status", value: STATUS_LABEL[tone] },
      { label: "Warnings", value: String(snapshot.review?.warnings.length ?? 0) },
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
    ],
  };
}

export function buildWhatMatters(snapshot: AimeeSnapshot, context: RouteContext): OverviewCard[] {
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
          review.facts.main_open_risk != null
            ? `${review.facts.main_open_risk.strategy_name} on ${review.facts.main_open_risk.instrument} holds ${formatPercent(review.facts.main_open_risk.share_of_open_risk_percent ?? review.facts.largest_risk_share_percent)} of open risk.`
            : "Open risk is distributed with no single dominant exposure identified.",
        meta: `${formatPercent(review.facts.open_risk_percent)} open risk`,
        tone: review.facts.largest_risk_share_percent >= 50 ? "warning" : "neutral",
      },
      {
        id: "operate-pnl",
        title: "PnL session",
        detail: `Daily PnL is ${formatSignedCurrency(review.facts.daily_pnl)}${review.facts.daily_pnl_percent != null ? ` (${formatPercent(review.facts.daily_pnl_percent)})` : ""}.`,
        meta: review.facts.account_value != null ? `Account value ${formatCurrency(review.facts.account_value)}` : undefined,
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
        detail: blockedFamilies.length ? blockedFamilies.slice(0, 2).map((family) => family.strategy_name).join(", ") : "No families are blocked.",
        meta: String(blockedFamilies.length),
        tone: blockedFamilies.length ? "negative" : "neutral",
      },
      {
        id: "cp-degraded",
        title: "Degraded deployment",
        detail: degradedFamilies.length ? degradedFamilies.slice(0, 2).map((family) => family.strategy_name).join(", ") : "No degraded families detected.",
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
        detail: coverage.streaming.capped_instruments.length ? `${coverage.streaming.capped_instruments.slice(0, 3).join(", ")} are at cap.` : "No instruments are currently capped.",
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
        detail: warningStrategies.length ? warningStrategies.slice(0, 2).map((strategy) => strategy.name).join(", ") : "No strategy-level warnings are currently surfaced.",
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

export function buildWarningItems(snapshot: AimeeSnapshot): WarningItem[] {
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

export function buildRecentChanges(snapshot: AimeeSnapshot): ChangeItem[] {
  const historyItems = snapshot.history.slice(0, 2).map((item) => ({
    id: `history-${item.review_id}`,
    title: "Operator summary refreshed",
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

export function reviewResponseSummary(response: OperationalQuestionReviewResponse) {
  if (response.ai_summary?.summary) {
    return response.ai_summary.summary;
  }
  if (response.derived_observations[0]?.detail) {
    return response.derived_observations[0].detail;
  }
  return "No grounded answer is available yet.";
}

export function toneClasses(tone: Tone) {
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

export function toneTextClass(tone: Tone) {
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
