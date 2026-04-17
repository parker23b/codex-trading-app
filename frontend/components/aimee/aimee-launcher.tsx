import type { Tone } from "@/components/aimee/types";
import { STATUS_LABEL, joinClasses } from "@/components/aimee/utils";

type AimeeLauncherProps = {
  tone: Tone;
  attentionCount: number;
  hasAttentionPulse: boolean;
  onOpen: () => void;
};

export function AimeeLauncher({
  tone,
  attentionCount,
  hasAttentionPulse,
  onOpen,
}: AimeeLauncherProps) {
  return (
    <button
      type="button"
      className="fixed right-4 bottom-4 z-30 flex items-center gap-3 rounded-full border border-[color:var(--glass-stroke)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--bg-surface-strong)_94%,transparent),color-mix(in_srgb,var(--bg-surface)_92%,transparent))] px-4 py-3 text-[color:var(--text-primary)] shadow-[var(--shadow-panel)] backdrop-blur-[18px] transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-[var(--shadow-raised)] max-[920px]:right-3 max-[920px]:bottom-3 max-[920px]:px-3"
      onClick={onOpen}
      aria-label="Open AIMEE assistant">
      <span className="relative flex h-9 w-9 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--glass-stroke))] bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--accent)_20%,transparent),transparent_62%),linear-gradient(180deg,#16304a,#0c131a)] shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]">
        <span className="absolute h-5 w-5 animate-pulse rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--accent)_70%,transparent),transparent_72%)]" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-[color:var(--accent)]" />
        {hasAttentionPulse || attentionCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center">
            <span className="absolute h-3.5 w-3.5 animate-ping rounded-full bg-[color:var(--warning)] opacity-60" />
            <span
              className={joinClasses(
                "relative h-2.5 w-2.5 rounded-full border border-[color:var(--bg-surface-strong)]",
                attentionCount > 0
                  ? "bg-[color:var(--warning)]"
                  : "bg-[color:var(--accent)]",
              )}
            />
          </span>
        ) : null}
      </span>
      <span className="flex min-w-0 flex-col items-start">
        <span className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
          A.I.M.E.E
        </span>
        <span className="max-w-[160px] overflow-hidden text-ellipsis whitespace-nowrap text-[0.88rem] font-semibold tracking-[-0.01em]">
          {STATUS_LABEL[tone]}
        </span>
      </span>
    </button>
  );
}
