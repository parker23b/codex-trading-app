import type {
  AllocationAlert,
  AllocationCycle,
  AllocationDriftSummary,
  AllocationExposureSummary,
  AllocationIntent,
  DirectionalCurrencyExposureBucket,
  ExposureHotspot,
  RiskTruthConfidence,
} from "./types";

export type RiskTone = "neutral" | "positive" | "warning" | "negative" | "inactive";
export type RiskDataSection = "exposure" | "alerts" | "drift" | "cycles" | "intents" | "selectedCycle";
export type RiskLoadErrors = Partial<Record<RiskDataSection, string | null>>;

const RISK_DATA_SECTION_LABELS: Record<RiskDataSection, string> = {
  exposure: "exposure",
  alerts: "alerts",
  drift: "execution drift",
  cycles: "allocation cycles",
  intents: "risk truth",
  selectedCycle: "selected cycle",
};

export type RiskLoadQuality = {
  degraded: boolean;
  unavailableSections: RiskDataSection[];
  headline: string;
  detail: string;
  sectionUnavailable: (section: RiskDataSection) => boolean;
};

export type RiskSummaryItem = {
  label: string;
  value: string;
  meta?: string;
  tone: RiskTone;
};

export type RiskAllocationSummary = {
  grossRiskPercent: number;
  netRiskPercent: number;
  longRiskPercent: number;
  shortRiskPercent: number;
  openPositionCount: number;
  reservedIntentCount: number;
  topInstruments: Array<{
    instrument: string;
    totalRiskPercent: number;
    utilizationPercent?: number | null;
  }>;
};

export function buildRiskLoadQuality(errors: RiskLoadErrors = {}): RiskLoadQuality {
  const unavailableSections = (Object.entries(errors) as Array<[RiskDataSection, string | null | undefined]>)
    .filter(([, error]) => Boolean(error))
    .map(([section]) => section);

  const sectionLabels = unavailableSections.map((section) => RISK_DATA_SECTION_LABELS[section]);
  const detail = sectionLabels.length
    ? `Backend risk reads failed for ${sectionLabels.join(", ")}. Values from those sections are unavailable, not zero or healthy truth.`
    : "All risk read sections loaded from backend responses.";

  return {
    degraded: unavailableSections.length > 0,
    unavailableSections,
    headline: unavailableSections.length > 0 ? "Risk data unavailable" : "Risk data current",
    detail,
    sectionUnavailable: (section: RiskDataSection) => unavailableSections.includes(section),
  };
}

export type RiskConsoleSummary = {
  openRiskPercent: number;
  reservedRiskPercent: number;
  totalActiveRiskPercent: number;
  remainingPortfolioRiskPercent: number;
  criticalAlertCount: number;
  warningAlertCount: number;
  materialDriftCount: number;
  degradedSizingOrTruth: boolean;
  lastCycleStatus: {
    label: string;
    tone: RiskTone;
    meta: string;
  };
  topHotspot?: ExposureHotspot | null;
  dominantNetCurrency?: DirectionalCurrencyExposureBucket | null;
  truthMix: {
    exact: number;
    provisional: number;
    estimated: number;
    degraded: number;
  };
  metrics: RiskSummaryItem[];
  aimeeContext: {
    status: string;
    headline: string;
    activeRisk: {
      openRiskPercent: number;
      reservedRiskPercent: number;
      totalActiveRiskPercent: number;
      remainingPortfolioRiskPercent: number;
    };
    alerts: {
      critical: number;
      warning: number;
      materialDrift: number;
      degradedSizingOrTruth: boolean;
    };
    hotspots: {
      top?: string | null;
      dominantNetBias?: string | null;
    };
    lastCycle: {
      status: string;
      candidates?: number;
      approved?: number;
      rejected?: number;
      bindingConstraint?: string | null;
    };
  };
};

function statusTone(value: number, warningThreshold: number, criticalThreshold: number): RiskTone {
  if (value >= criticalThreshold) {
    return "negative";
  }
  if (value >= warningThreshold) {
    return "warning";
  }
  return "positive";
}

export function truthConfidenceMeta(value?: RiskTruthConfidence | null): {
  label: string;
  tone: RiskTone;
  detail: string;
} {
  switch (value) {
    case "EXACT_FILL_DERIVED":
      return {
        label: "Exact",
        tone: "positive",
        detail: "Fill-derived risk was recomputed from actual execution data.",
      };
    case "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED":
      return {
        label: "Broker Confirmed",
        tone: "neutral",
        detail: "Risk uses broker-confirmed average fill and size, but exact recomputation is still estimate-based.",
      };
    case "PARTIAL_FILL_PROVISIONAL":
      return {
        label: "Provisional",
        tone: "warning",
        detail: "Risk reflects a partial fill and may change as the order completes or is reconciled.",
      };
    case "SUBMITTED_EXECUTABLE_ESTIMATE":
      return {
        label: "Submitted Estimate",
        tone: "warning",
        detail: "Risk is based on broker-valid submitted size, not final fill truth.",
      };
    case "ALLOCATION_INTENT_ONLY":
      return {
        label: "Allocated Only",
        tone: "inactive",
        detail: "Risk still reflects allocator intent rather than broker-confirmed execution.",
      };
    case "INCOMPLETE_DEGRADED":
      return {
        label: "Degraded",
        tone: "negative",
        detail: "Fill truth is incomplete or inconsistent; post-trade risk remains degraded.",
      };
    default:
      return {
        label: "Unknown",
        tone: "inactive",
        detail: "Risk truth confidence is unavailable.",
      };
  }
}

export function alertSeverityTone(severity: AllocationAlert["severity"]): RiskTone {
  if (severity === "error") {
    return "negative";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}

export function cycleStatus(cycle?: AllocationCycle | null): {
  label: string;
  tone: RiskTone;
  meta: string;
} {
  if (!cycle) {
    return {
      label: "No recent cycle",
      tone: "inactive",
      meta: "Allocation history unavailable.",
    };
  }

  const degraded = cycle.degraded_candidate_count > 0 || Boolean(cycle.details?.degraded);
  const blockedCount =
    cycle.blocked_unsupported_sizing_count +
    cycle.blocked_approximate_live_count +
    cycle.blocked_under_minimum_size_count +
    cycle.blocked_budget_count +
    cycle.blocked_conflict_count;

  if (degraded) {
    return {
      label: "Degraded",
      tone: "negative",
      meta: `${cycle.approved_count}/${cycle.candidate_count} approved · degraded sizing or truth present`,
    };
  }

  if (blockedCount > 0 && cycle.approved_count === 0 && cycle.candidate_count > 0) {
    return {
      label: "Blocked",
      tone: "warning",
      meta: `${cycle.rejected_count}/${cycle.candidate_count} rejected · no capital deployed`,
    };
  }

  if (blockedCount > 0) {
    return {
      label: "Constrained",
      tone: "warning",
      meta: `${cycle.approved_count}/${cycle.candidate_count} approved · ${blockedCount} constrained`,
    };
  }

  return {
    label: "Nominal",
    tone: "positive",
    meta: `${cycle.approved_count}/${cycle.candidate_count} approved`,
  };
}

function getDominantNetCurrency(
  directional: AllocationExposureSummary["currency_directional"],
): DirectionalCurrencyExposureBucket | null {
  if (!directional.length) {
    return null;
  }
  return directional
    .slice()
    .sort((left, right) => Math.abs(right.net_risk_percent) - Math.abs(left.net_risk_percent))[0] ?? null;
}

function classifyTruthMix(intents: AllocationIntent[]) {
  const mix = {
    exact: 0,
    provisional: 0,
    estimated: 0,
    degraded: 0,
  };

  intents
    .filter((intent) => intent.position?.is_open)
    .forEach((intent) => {
      switch (intent.position?.risk_truth_confidence ?? intent.risk_truth_confidence) {
        case "EXACT_FILL_DERIVED":
          mix.exact += 1;
          break;
        case "PARTIAL_FILL_PROVISIONAL":
          mix.provisional += 1;
          break;
        case "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED":
        case "SUBMITTED_EXECUTABLE_ESTIMATE":
        case "ALLOCATION_INTENT_ONLY":
          mix.estimated += 1;
          break;
        case "INCOMPLETE_DEGRADED":
          mix.degraded += 1;
          break;
        default:
          mix.estimated += 1;
          break;
      }
    });

  return mix;
}

function dominantBindingBudget(cycle?: AllocationCycle | null): string | null {
  if (!cycle) {
    return null;
  }
  const entries = Object.entries(cycle.binding_budget_counts ?? {});
  if (!entries.length) {
    return null;
  }
  const [budget] = entries.sort((left, right) => right[1] - left[1])[0];
  return budget;
}

function summaryHeadline(args: {
  criticalAlertCount: number;
  degradedSizingOrTruth: boolean;
  materialDriftCount: number;
  topHotspot?: ExposureHotspot | null;
  totalActiveRiskPercent: number;
}): string {
  if (args.criticalAlertCount > 0) {
    return `${args.criticalAlertCount} critical risk alerts need review`;
  }
  if (args.degradedSizingOrTruth) {
    return "Sizing or fill-truth is degraded";
  }
  if (args.materialDriftCount > 0) {
    return `${args.materialDriftCount} trades show material execution drift`;
  }
  if (args.topHotspot) {
    return `${args.topHotspot.name} is the current concentration hotspot`;
  }
  return `Active risk is running at ${args.totalActiveRiskPercent.toFixed(1)}%`;
}

export function buildRiskConsoleSummary(args: {
  exposure: AllocationExposureSummary;
  alerts: AllocationAlert[];
  drift: AllocationDriftSummary;
  cycles: AllocationCycle[];
  intents: AllocationIntent[];
}): RiskConsoleSummary {
  const { exposure, alerts, drift, cycles, intents } = args;
  const criticalAlertCount = alerts.filter((alert) => alert.severity === "error" && alert.state !== "RESOLVED").length;
  const warningAlertCount = alerts.filter((alert) => alert.severity === "warning" && alert.state !== "RESOLVED").length;
  const degradedSizingOrTruth = alerts.some(
    (alert) =>
      alert.state !== "RESOLVED"
      && ["degraded_allocation_cycles", "missing_broker_sizing_metadata", "incomplete_fill_truth", "approximate_sizing_blocked_live"].includes(alert.alert_type),
  );
  const liveRisk = exposure.totals.live_risk_percent + exposure.totals.provisional_live_risk_percent;
  const reservedRisk = exposure.totals.reserved_risk_percent;
  const totalActiveRiskPercent = liveRisk + reservedRisk;
  const lastCycle = cycles[0] ?? null;
  const topHotspot = exposure.hotspots[0] ?? null;
  const dominantNetCurrency = getDominantNetCurrency(exposure.currency_directional);
  const truthMix = classifyTruthMix(intents);

  const metrics: RiskSummaryItem[] = [
    {
      label: "Open Risk",
      value: `${exposure.totals.live_risk_percent.toFixed(2)}%`,
      meta: exposure.totals.provisional_live_risk_percent > 0
        ? `${exposure.totals.provisional_live_risk_percent.toFixed(2)}% provisional live risk`
        : "Fill-derived live book",
      tone: statusTone(exposure.totals.live_risk_percent, 2.5, 4),
    },
    {
      label: "Reserved Risk",
      value: `${reservedRisk.toFixed(2)}%`,
      meta: `${exposure.totals.reserved_intent_count} intents holding capital`,
      tone: statusTone(reservedRisk, 1.5, 3),
    },
    {
      label: "Active Risk",
      value: `${totalActiveRiskPercent.toFixed(2)}%`,
      meta: `${exposure.totals.remaining_portfolio_risk_percent.toFixed(2)}% headroom remaining`,
      tone: statusTone(totalActiveRiskPercent, 3.5, 5),
    },
    {
      label: "Critical Alerts",
      value: String(criticalAlertCount),
      meta: warningAlertCount > 0 ? `${warningAlertCount} warnings still open` : "No warning backlog",
      tone: criticalAlertCount > 0 ? "negative" : warningAlertCount > 0 ? "warning" : "positive",
    },
    {
      label: "Material Drift",
      value: String(drift.material_drift_count),
      meta: `warning ${drift.drift_warning_percent.toFixed(1)}% · critical ${drift.drift_critical_percent.toFixed(1)}%`,
      tone: drift.material_drift_count > 0 ? "warning" : "positive",
    },
    {
      label: "Risk Truth",
      value:
        truthMix.degraded > 0
          ? `${truthMix.degraded} degraded`
          : truthMix.provisional > 0
            ? `${truthMix.provisional} provisional`
            : truthMix.exact > 0
              ? `${truthMix.exact} exact`
              : "No live book",
      meta:
        truthMix.exact || truthMix.provisional || truthMix.estimated || truthMix.degraded
          ? `${truthMix.exact} exact · ${truthMix.provisional} provisional · ${truthMix.estimated} estimated`
          : "No open positions to classify",
      tone: truthMix.degraded > 0 ? "negative" : truthMix.provisional > 0 || truthMix.estimated > 0 ? "warning" : "positive",
    },
  ];

  return {
    openRiskPercent: exposure.totals.live_risk_percent,
    reservedRiskPercent: reservedRisk,
    totalActiveRiskPercent,
    remainingPortfolioRiskPercent: exposure.totals.remaining_portfolio_risk_percent,
    criticalAlertCount,
    warningAlertCount,
    materialDriftCount: drift.material_drift_count,
    degradedSizingOrTruth,
    lastCycleStatus: cycleStatus(lastCycle),
    topHotspot,
    dominantNetCurrency,
    truthMix,
    metrics,
    aimeeContext: {
      status:
        criticalAlertCount > 0
          ? "critical"
          : degradedSizingOrTruth || drift.material_drift_count > 0
            ? "watch"
            : "nominal",
      headline: summaryHeadline({
        criticalAlertCount,
        degradedSizingOrTruth,
        materialDriftCount: drift.material_drift_count,
        topHotspot,
        totalActiveRiskPercent,
      }),
      activeRisk: {
        openRiskPercent: exposure.totals.live_risk_percent,
        reservedRiskPercent: reservedRisk,
        totalActiveRiskPercent,
        remainingPortfolioRiskPercent: exposure.totals.remaining_portfolio_risk_percent,
      },
      alerts: {
        critical: criticalAlertCount,
        warning: warningAlertCount,
        materialDrift: drift.material_drift_count,
        degradedSizingOrTruth,
      },
      hotspots: {
        top: topHotspot ? `${topHotspot.bucket_type}:${topHotspot.name}` : null,
        dominantNetBias:
          dominantNetCurrency
            ? `${dominantNetCurrency.currency} ${dominantNetCurrency.net_bias} ${dominantNetCurrency.net_risk_percent.toFixed(2)}%`
            : null,
      },
      lastCycle: {
        status: cycleStatus(lastCycle).label,
        candidates: lastCycle?.candidate_count,
        approved: lastCycle?.approved_count,
        rejected: lastCycle?.rejected_count,
        bindingConstraint: dominantBindingBudget(lastCycle),
      },
    },
  };
}

export function buildRiskAllocationSummary(exposure: AllocationExposureSummary): RiskAllocationSummary {
  const longRiskPercent = exposure.currency_directional.reduce(
    (total, bucket) => total + bucket.reserved_long_risk_percent + bucket.live_long_risk_percent,
    0,
  );
  const shortRiskPercent = exposure.currency_directional.reduce(
    (total, bucket) => total + bucket.reserved_short_risk_percent + bucket.live_short_risk_percent,
    0,
  );
  const netRiskPercent = longRiskPercent - shortRiskPercent;
  const grossRiskPercent = exposure.currency_directional.length
    ? exposure.currency_directional.reduce((total, bucket) => total + bucket.gross_risk_percent, 0)
    : longRiskPercent + shortRiskPercent;

  return {
    grossRiskPercent,
    netRiskPercent,
    longRiskPercent,
    shortRiskPercent,
    openPositionCount: exposure.totals.open_position_count,
    reservedIntentCount: exposure.totals.reserved_intent_count,
    topInstruments: exposure.by_instrument
      .slice()
      .sort((left, right) => right.total_risk_percent - left.total_risk_percent)
      .slice(0, 5)
      .map((bucket) => ({
        instrument: bucket.name,
        totalRiskPercent: bucket.total_risk_percent,
        utilizationPercent: bucket.utilization_percent,
      })),
  };
}

export function formatHotspotLabel(hotspot?: ExposureHotspot | null): string {
  if (!hotspot) {
    return "No active hotspot";
  }
  const mode = hotspot.bucket_type === "currency_directional" && hotspot.net_bias
    ? `${hotspot.name} ${hotspot.net_bias.toLowerCase()}`
    : hotspot.name;
  return `${mode} · ${hotspot.utilization_percent.toFixed(0)}% utilized`;
}

export function formatDirectionalBias(bucket?: DirectionalCurrencyExposureBucket | null): string {
  if (!bucket) {
    return "No dominant net bias";
  }
  if (bucket.net_bias === "FLAT") {
    return `${bucket.currency} flat`;
  }
  return `${bucket.currency} ${bucket.net_bias.toLowerCase()} ${Math.abs(bucket.net_risk_percent).toFixed(2)}%`;
}
