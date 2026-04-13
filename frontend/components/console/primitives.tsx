import type { CSSProperties, ReactNode } from "react";

export type ConsoleTone = "neutral" | "positive" | "warning" | "negative" | "inactive";
export type PanelPriority = "critical" | "primary" | "secondary" | "passive";

type PanelProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  priority?: PanelPriority;
  tone?: ConsoleTone;
  compact?: boolean;
};

type BoardLayoutProps = {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  className?: string;
};

type StatusItem = {
  label: string;
  value: ReactNode;
  tone?: ConsoleTone;
  meta?: ReactNode;
  emphasis?: "strong" | "normal";
};

type StatusStripProps = {
  items: StatusItem[];
};

type SplitPanelProps = {
  left: ReactNode;
  center?: ReactNode;
  right?: ReactNode;
  className?: string;
};

type InspectorDrawerProps = {
  title: string;
  subtitle?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

type ExceptionListItem = {
  id: string;
  title: string;
  detail?: string;
  tone?: ConsoleTone;
  meta?: string;
};

type ExceptionListProps = {
  title: string;
  subtitle?: string;
  items: ExceptionListItem[];
  emptyLabel: string;
  priority?: PanelPriority;
};

type CompactTableColumn<T> = {
  key: string;
  header: string;
  className?: string;
  render: (row: T, index: number) => ReactNode;
};

type CompactTableProps<T> = {
  columns: CompactTableColumn<T>[];
  rows: T[];
  emptyLabel: string;
  dense?: boolean;
  getRowTone?: (row: T, index: number) => ConsoleTone | undefined;
  getRowActive?: (row: T, index: number) => boolean;
};

type StickyToolbarProps = {
  children: ReactNode;
  className?: string;
};

type StatusPillProps = {
  label: ReactNode;
  tone?: ConsoleTone;
  quiet?: boolean;
  title?: string;
};

type DataIndicatorProps = {
  state: "loading" | "error" | "unavailable";
  message?: string | null;
};

function joinClasses(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function toneBorderColor(tone: ConsoleTone) {
  const colors: Record<ConsoleTone, string> = {
    neutral: "var(--glass-stroke)",
    positive: "color-mix(in srgb, var(--positive) 34%, var(--border))",
    warning: "color-mix(in srgb, var(--warning) 38%, var(--border))",
    negative: "color-mix(in srgb, var(--negative) 40%, var(--border))",
    inactive: "color-mix(in srgb, var(--inactive) 34%, var(--border))",
  };

  return colors[tone];
}

function statusItemStyle(tone: ConsoleTone | undefined, emphasis: "strong" | "normal" | undefined): CSSProperties | undefined {
  if (!tone || tone === "neutral") {
    return emphasis === "strong" ? { boxShadow: "var(--shadow-panel)" } : undefined;
  }

  return {
    borderColor: toneBorderColor(tone),
    boxShadow:
      tone === "negative"
        ? "var(--shadow-raised)"
        : emphasis === "strong"
          ? "var(--shadow-panel)"
          : undefined,
  };
}

function toneDotClass(tone: ConsoleTone) {
  const toneStyles: Record<ConsoleTone, string> = {
    neutral: "border-[color:var(--border-strong)] bg-[color:var(--bg-muted)]",
    positive: "bg-[color:var(--positive)] shadow-[0_0_0_4px_var(--positive-soft)]",
    warning: "bg-[color:var(--warning)] shadow-[0_0_0_4px_var(--warning-soft)]",
    negative: "bg-[color:var(--negative)] shadow-[0_0_0_4px_var(--negative-soft)]",
    inactive: "bg-[color:var(--inactive)] shadow-[0_0_0_4px_var(--inactive-soft)]",
  };

  return joinClasses("inline-flex h-[9px] w-[9px] rounded-full border", toneStyles[tone]);
}

function panelPriorityClass(priority: PanelPriority) {
  const priorities: Record<PanelPriority, string> = {
    critical: "bg-[image:var(--glass-surface)] shadow-[var(--shadow-raised)]",
    primary: "bg-[image:var(--glass-surface)] shadow-[var(--shadow-panel)]",
    secondary: "bg-[image:var(--glass-surface-soft)] shadow-[var(--shadow-soft)]",
    passive: "bg-[image:var(--glass-surface-passive)] shadow-[var(--shadow-soft)]",
  };

  return priorities[priority];
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  priority = "secondary",
  tone = "neutral",
  compact = false,
}: PanelProps) {
  return (
    <section
      className={joinClasses(
        "rounded-[18px] border border-[color:var(--glass-stroke)]",
        panelPriorityClass(priority),
        compact ? "overflow-hidden" : "",
        className,
      )}
      style={tone === "neutral" ? undefined : { borderColor: toneBorderColor(tone) }}
    >
      <header className={joinClasses("flex items-start justify-between gap-3", compact ? "px-4 pt-3 pb-0" : "px-[18px] pt-4 pb-0")}>
        <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
          <div className="flex items-center gap-2">
            <span className={toneDotClass(tone)} aria-hidden="true" />
            <div className="text-[1rem] font-semibold tracking-[-0.01em]">{title}</div>
          </div>
          {subtitle ? <p className="text-[0.82rem] text-[color:var(--text-secondary)]">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      <div className={joinClasses("flex flex-col gap-3", compact ? "p-4" : "p-[18px]")}>{children}</div>
    </section>
  );
}

export function StatusStrip({ items }: StatusStripProps) {
  return (
    <section className="grid flex-none grid-cols-6 gap-[10px] max-[1200px]:grid-cols-3 max-[720px]:grid-cols-2" aria-label="System status strip">
      {items.map((item) => (
        <div
          key={item.label}
          className={joinClasses(
            "min-h-[84px] overflow-hidden rounded-[14px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface)] px-3 py-[11px] shadow-[var(--shadow-soft)]",
          )}
          style={statusItemStyle(item.tone, item.emphasis)}
        >
          <div className="flex items-center gap-2">
            <span className={toneDotClass(item.tone ?? "neutral")} aria-hidden="true" />
            <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">{item.label}</span>
          </div>
          <strong className="mt-1 block overflow-hidden text-ellipsis whitespace-nowrap text-[1rem] font-semibold tracking-[-0.01em]">{item.value}</strong>
          {item.meta ? <span className="mt-1 line-clamp-2 block text-[0.76rem] text-[color:var(--text-secondary)]">{item.meta}</span> : null}
        </div>
      ))}
    </section>
  );
}

export function BoardLayout({ left, center, right, className }: BoardLayoutProps) {
  return (
    <section className={joinClasses("grid grid-cols-3 gap-3 max-[1200px]:grid-cols-1", className)}>
      <div className="flex min-h-0 flex-col gap-3">{left}</div>
      <div className="flex min-h-0 flex-col gap-3">{center}</div>
      <div className="flex min-h-0 flex-col gap-3">{right}</div>
    </section>
  );
}

export function SplitPanel({ left, center, right, className }: SplitPanelProps) {
  const mode = center && right ? "triple" : right ? "dual" : "single";
  return (
    <section
      className={joinClasses(
        "grid gap-3",
        mode === "triple" ? "grid-cols-3 max-[1200px]:grid-cols-1" : mode === "dual" ? "grid-cols-2 max-[1200px]:grid-cols-1" : "grid-cols-1",
        className,
      )}
    >
      <div className="flex min-h-0 flex-col gap-3">{left}</div>
      {center ? <div className="flex min-h-0 flex-col gap-3">{center}</div> : null}
      {right ? <div className="flex min-h-0 flex-col gap-3">{right}</div> : null}
    </section>
  );
}

export function StickyToolbar({ children, className }: StickyToolbarProps) {
  return (
    <div
      className={joinClasses(
        "sticky top-2 z-10 mb-1 flex flex-wrap items-center justify-between gap-2 rounded-[16px] border border-[color:var(--border)] bg-[color:color-mix(in_srgb,var(--bg-shell)_92%,transparent)] px-3 py-2 shadow-[var(--shadow-soft)] backdrop-blur-[16px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function StatusPill({ label, tone = "neutral", quiet = false, title }: StatusPillProps) {
  return (
    <span className="group relative inline-flex max-w-full">
      <span
        className={joinClasses(
          "inline-flex max-w-full items-center gap-2 rounded-full border px-[10px] py-1 text-[0.72rem] font-medium leading-none whitespace-nowrap",
          tone === "positive" && "bg-[color:var(--positive-soft)] text-[color:var(--positive)]",
          tone === "warning" && "bg-[color:var(--warning-soft)] text-[color:var(--warning)]",
          tone === "negative" && "bg-[color:var(--negative-soft)] text-[color:var(--negative)]",
          tone === "inactive" && "bg-[color:var(--inactive-soft)] text-[color:var(--inactive)]",
          tone === "neutral" && "border-[color:var(--border)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)]",
          quiet && "bg-transparent",
        )}
        style={tone === "neutral" ? undefined : { borderColor: toneBorderColor(tone) }}
        aria-label={typeof label === "string" ? `${label}${title ? `. ${title}` : ""}` : title}
        tabIndex={title ? 0 : undefined}
      >
        <span className={toneDotClass(tone)} aria-hidden="true" />
        {label}
      </span>
      {title ? (
        <span className="pointer-events-none absolute top-[calc(100%+8px)] left-1/2 z-30 w-max max-w-[220px] -translate-x-1/2 rounded-[10px] border border-[color:var(--border)] bg-[color:var(--bg-surface-strong)] px-3 py-2 text-center text-[0.74rem] leading-[1.35] text-[color:var(--text-primary)] opacity-0 shadow-[var(--shadow-panel)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
          {title}
        </span>
      ) : null}
    </span>
  );
}

export function DataIndicator({ state, message }: DataIndicatorProps) {
  const label = state === "loading" ? "Loading" : state === "error" ? "Error" : "Unavailable";
  return (
    <span
      className={joinClasses(
        "ml-[0.35rem] inline-flex h-4 w-4 min-w-4 items-center justify-center rounded-full border align-middle text-[color:var(--text-secondary)]",
        state === "error" && "border-[color:color-mix(in_srgb,var(--negative)_48%,var(--border))] bg-[color:var(--negative-soft)] text-[color:var(--negative)]",
        state === "unavailable" && "border-[color:color-mix(in_srgb,var(--inactive)_48%,var(--border))] bg-[color:var(--inactive-soft)] text-[color:var(--inactive)]",
        state === "loading" && "border-[color:color-mix(in_srgb,var(--accent)_42%,var(--border))] bg-[color:var(--accent-soft)]",
      )}
      title={message ?? label}
      aria-label={message ?? label}
    >
      {state === "loading" ? (
        <span
          className="h-[0.55rem] w-[0.55rem] animate-spin rounded-full border-2 border-[color:color-mix(in_srgb,var(--accent)_28%,transparent)] border-t-[color:var(--accent)]"
          aria-hidden="true"
        />
      ) : state === "error" ? "!" : "-"}
    </span>
  );
}

export function ExceptionList({
  title,
  subtitle,
  items,
  emptyLabel,
  priority = "critical",
}: ExceptionListProps) {
  return (
    <Panel title={title} subtitle={subtitle} priority={priority} tone={items.length ? items[0]?.tone ?? "warning" : "positive"}>
      <div className="flex flex-col gap-3">
        {items.length ? (
          items.map((item) => (
            <article
              key={item.id}
              className={joinClasses(
                "flex items-start justify-between gap-3 rounded-[14px] border border-[color:var(--border)] bg-[color:var(--bg-surface-muted)] px-3 py-3",
                item.tone === "positive" && "border-[color:color-mix(in_srgb,var(--positive)_34%,var(--border))]",
                item.tone === "warning" && "border-[color:color-mix(in_srgb,var(--warning)_34%,var(--border))]",
                item.tone === "negative" && "border-[color:color-mix(in_srgb,var(--negative)_34%,var(--border))]",
              )}
            >
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className={toneDotClass(item.tone ?? "neutral")} aria-hidden="true" />
                  <strong>{item.title}</strong>
                </div>
                {item.detail ? <p className="text-[0.85rem] text-[color:var(--text-secondary)]">{item.detail}</p> : null}
              </div>
              {item.meta ? <div className="text-right text-[0.75rem] text-[color:var(--text-tertiary)]">{item.meta}</div> : null}
            </article>
          ))
        ) : (
          <div className="console-empty console-empty--positive">{emptyLabel}</div>
        )}
      </div>
    </Panel>
  );
}

export function CompactTable<T>({
  columns,
  rows,
  emptyLabel,
  dense,
  getRowTone,
  getRowActive,
}: CompactTableProps<T>) {
  if (!rows.length) {
    return <div className="console-empty">{emptyLabel}</div>;
  }

  return (
    <div className="compact-table-shell">
      <table className={`compact-table${dense ? " compact-table--dense" : ""}`}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.className}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const tone = getRowTone?.(row, index);
            const active = getRowActive?.(row, index);
            return (
              <tr
                key={index}
                className={[
                  tone ? `compact-table__row--${tone}` : "",
                  active ? "compact-table__row--active" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {columns.map((column) => (
                  <td key={column.key} className={column.className}>
                    {column.render(row, index)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function InspectorDrawer({ title, subtitle, open, onClose, children }: InspectorDrawerProps) {
  return (
    <div
      className={joinClasses(
        "pointer-events-none fixed inset-0 z-40",
        open ? "visible" : "invisible",
      )}
      aria-hidden={!open}
    >
      <div
        className={joinClasses(
          "absolute inset-0 bg-[rgba(6,18,28,0.16)] opacity-0 backdrop-blur-[4px] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),inset_0_0_120px_rgba(6,18,28,0.1)] transition-opacity duration-200",
          open && "pointer-events-auto opacity-100",
        )}
        onClick={onClose}
      />
      <aside
        className={joinClasses(
          "pointer-events-auto absolute right-0 w-full max-w-[620px] overflow-x-hidden border-l border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_96%,transparent)] shadow-[var(--shadow-raised)] backdrop-blur-[16px] transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
        style={{ top: 0, height: "100vh" }}
        aria-label={title}
      >
        <header className="flex items-start justify-between gap-3 border-b border-[color:var(--border)] px-5 py-4">
          <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
            <div className="flex items-center gap-2">
              <span className={toneDotClass("neutral")} aria-hidden="true" />
              <div className="text-[1rem] font-semibold tracking-[-0.01em]">{title}</div>
            </div>
            {subtitle ? <p className="text-[0.82rem] text-[color:var(--text-secondary)]">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
            onClick={onClose}
            aria-label={`Close ${title}`}
          >
            <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
              <path d="M5.22 5.22a.75.75 0 0 1 1.06 0L10 8.94l3.72-3.72a.75.75 0 1 1 1.06 1.06L11.06 10l3.72 3.72a.75.75 0 0 1-1.06 1.06L10 11.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06L8.94 10 5.22 6.28a.75.75 0 0 1 0-1.06Z" fill="currentColor" />
            </svg>
          </button>
        </header>
        <div className="flex h-[calc(100%-73px)] flex-col gap-3 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}
