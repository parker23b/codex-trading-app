import { AimeeCloseButton } from "@/components/aimee/aimee-close-button";
import type { RouteContext } from "@/components/aimee/types";
import { routeLabel } from "@/components/aimee/utils";

type AimeeDrawerHeaderProps = {
  context: RouteContext;
  onClose: () => void;
};

export function AimeeDrawerHeader({
  context,
  onClose,
}: AimeeDrawerHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[color:var(--border)] px-5 py-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="relative mt-1 flex h-11 w-11 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--glass-stroke))] bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--accent)_22%,transparent),transparent_60%),linear-gradient(180deg,color-mix(in_srgb,var(--bg-surface-strong)_90%,transparent),color-mix(in_srgb,var(--bg-surface)_86%,transparent))] shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_0_26px_color-mix(in_srgb,var(--accent)_20%,transparent)]">
          <span className="absolute h-7 w-7 animate-pulse rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--accent)_60%,transparent),transparent_72%)]" />
          <span className="relative h-3 w-3 rounded-full bg-[color:var(--accent)] shadow-[0_0_0_6px_color-mix(in_srgb,var(--accent)_12%,transparent)]" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[1.04rem] font-semibold tracking-[-0.02em]">
              A.I.M.E.E
            </h2>
            <span className="rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] px-2 py-1 text-[0.66rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
              {routeLabel(context)}
            </span>
          </div>
          <p className="mt-1 text-[0.8rem] text-[color:var(--text-secondary)]">
            Autonomous Intelligence for Market Explanation &amp; Evaluation
          </p>
        </div>
      </div>
      <AimeeCloseButton label="Close A.I.M.E.E" onClick={onClose} />
    </div>
  );
}
