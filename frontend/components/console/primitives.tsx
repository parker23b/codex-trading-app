import type { ReactNode } from "react";

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
};

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
      className={[
        "console-panel",
        `console-panel--${priority}`,
        `console-panel--tone-${tone}`,
        compact ? "console-panel--compact" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="console-panel__header">
        <div className="console-panel__heading">
          <div className="console-panel__title-row">
            <span className={`state-dot state-dot--${tone}`} aria-hidden="true" />
            <div className="console-panel__title">{title}</div>
          </div>
          {subtitle ? <p className="console-panel__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="console-panel__actions">{actions}</div> : null}
      </header>
      <div className="console-panel__body">{children}</div>
    </section>
  );
}

export function StatusStrip({ items }: StatusStripProps) {
  return (
    <section className="status-strip" aria-label="System status strip">
      {items.map((item) => (
        <div
          key={item.label}
          className={[
            "status-strip__item",
            `status-strip__item--${item.tone ?? "neutral"}`,
            item.emphasis === "strong" ? "status-strip__item--strong" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <div className="status-strip__label-row">
            <span className={`state-dot state-dot--${item.tone ?? "neutral"}`} aria-hidden="true" />
            <span className="status-strip__label">{item.label}</span>
          </div>
          <strong className="status-strip__value">{item.value}</strong>
          {item.meta ? <span className="status-strip__meta">{item.meta}</span> : null}
        </div>
      ))}
    </section>
  );
}

export function BoardLayout({ left, center, right, className }: BoardLayoutProps) {
  return (
    <section className={["board-layout", className].filter(Boolean).join(" ")}>
      <div className="board-layout__column">{left}</div>
      <div className="board-layout__column">{center}</div>
      <div className="board-layout__column">{right}</div>
    </section>
  );
}

export function SplitPanel({ left, center, right, className }: SplitPanelProps) {
  const mode = center && right ? "triple" : right ? "dual" : "single";
  return (
    <section className={["split-panel", `split-panel--${mode}`, className].filter(Boolean).join(" ")}>
      <div className="split-panel__pane">{left}</div>
      {center ? <div className="split-panel__pane">{center}</div> : null}
      {right ? <div className="split-panel__pane">{right}</div> : null}
    </section>
  );
}

export function StickyToolbar({ children, className }: StickyToolbarProps) {
  return <div className={["sticky-toolbar", className].filter(Boolean).join(" ")}>{children}</div>;
}

export function StatusPill({ label, tone = "neutral", quiet = false }: StatusPillProps) {
  return (
    <span className={`console-pill console-pill--${tone}${quiet ? " console-pill--quiet" : ""}`}>
      <span className={`state-dot state-dot--${tone}`} aria-hidden="true" />
      {label}
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
      <div className="exception-list">
        {items.length ? (
          items.map((item) => (
            <article key={item.id} className={`exception-list__item exception-list__item--${item.tone ?? "neutral"}`}>
              <div className="exception-list__main">
                <div className="exception-list__title-row">
                  <span className={`state-dot state-dot--${item.tone ?? "neutral"}`} aria-hidden="true" />
                  <strong>{item.title}</strong>
                </div>
                {item.detail ? <p>{item.detail}</p> : null}
              </div>
              {item.meta ? <div className="exception-list__meta">{item.meta}</div> : null}
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
    <div className={`inspector-drawer${open ? " inspector-drawer--open" : ""}`} aria-hidden={!open}>
      <div className="inspector-drawer__scrim" onClick={onClose} />
      <aside className="inspector-drawer__panel" aria-label={title}>
        <header className="inspector-drawer__header">
          <div className="console-panel__heading">
            <div className="console-panel__title-row">
              <span className="state-dot state-dot--neutral" aria-hidden="true" />
              <div className="console-panel__title">{title}</div>
            </div>
            {subtitle ? <p className="console-panel__subtitle">{subtitle}</p> : null}
          </div>
          <button type="button" className="console-button console-button--ghost" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="inspector-drawer__body">{children}</div>
      </aside>
    </div>
  );
}
