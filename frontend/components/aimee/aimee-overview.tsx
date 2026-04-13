import type { ChangeItem, OverviewCard, Tone, WarningItem } from "@/components/aimee/types";
import { formatDateTime, joinClasses, STATUS_LABEL, toneTextClass } from "@/components/aimee/utils";

type AimeeOverviewProps = {
  isExpanded: boolean;
  onToggle: () => void;
  systemSummary: {
    tone: Tone;
    headline: string;
    detail: string;
    indicators: Array<{ label: string; value: string }>;
  };
  compactMetric: string;
  attentionCount: number;
  updatedAt?: string | null;
  whatMatters: OverviewCard[];
  warningItems: WarningItem[];
  recentChanges: ChangeItem[];
};

export function AimeeOverview({
  isExpanded,
  onToggle,
  systemSummary,
  compactMetric,
  attentionCount,
  updatedAt,
  whatMatters,
  warningItems,
  recentChanges,
}: AimeeOverviewProps) {
  return (
    <>
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
            onClick={onToggle}
            aria-expanded={isExpanded}
            aria-label={isExpanded ? "Collapse AIMEE overview" : "Expand AIMEE overview"}
          >
            <svg viewBox="0 0 20 20" className={joinClasses("h-4 w-4 transition-transform duration-200", isExpanded ? "rotate-180" : "rotate-0")} aria-hidden="true">
              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.09l3.71-3.86a.75.75 0 0 1 1.08 1.04l-4.25 4.42a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" fill="currentColor" />
            </svg>
          </button>
        </div>
      </section>

      {isExpanded ? (
        <section className="flex flex-col gap-3 rounded-[16px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] p-3">
          <section className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">System Overview</div>
                <div className="mt-2 text-[1rem] font-semibold tracking-[-0.02em]">{systemSummary.headline}</div>
                <p className="mt-1 text-[0.84rem] text-[color:var(--text-secondary)]">{systemSummary.detail}</p>
              </div>
              <span className={joinClasses("text-[0.72rem] font-medium uppercase tracking-[0.08em]", toneTextClass(systemSummary.tone))}>{STATUS_LABEL[systemSummary.tone]}</span>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
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
              {updatedAt ? <span className="text-[0.74rem] text-[color:var(--text-tertiary)]">Updated {formatDateTime(updatedAt)}</span> : null}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {whatMatters.map((item) => (
                <article key={item.id} className="rounded-[12px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-[0.88rem] font-semibold tracking-[-0.01em]">{item.title}</h4>
                    <span className={joinClasses("text-[0.66rem] uppercase tracking-[0.08em]", toneTextClass(item.tone))}>{item.tone}</span>
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

          <section>
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
          </section>
        </section>
      ) : null}
    </>
  );
}
