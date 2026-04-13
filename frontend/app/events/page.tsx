import Link from "next/link";

import { CompactTable, Panel, StatusPill, StickyToolbar } from "@/components/console/primitives";
import { ResetHistoryButton } from "@/components/testing/reset-history-button";
import { getDomainEvents } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const EVENT_TYPE_OPTIONS = [
  "strategy.runtime_started",
  "strategy.runtime_stopped",
  "strategy.entry_candidate",
  "strategy.exit_candidate",
  "risk.entry_approved",
  "risk.entry_rejected",
  "execution.order_submitted",
  "execution.order_acknowledged",
  "execution.order_rejected",
  "execution.retry_suppressed",
  "execution.fill_received",
  "execution.position_opened",
  "execution.close_requested",
  "execution.position_closed",
  "reconciliation.mismatch_detected",
  "reconciliation.position_corrected",
  "reconciliation.unmatched_remote_position",
  "reconciliation.unmatched_local_position",
  "operator.runtime_started",
  "operator.runtime_stopped",
  "health.stream_stale",
  "health.stream_recovered",
  "health.polling_fallback_started",
  "health.polling_fallback_stopped",
  "health.broker_auth_failed",
] as const;

const CATEGORY_OPTIONS = ["strategy", "risk", "execution", "reconciliation", "operator", "health"] as const;
const SEVERITY_OPTIONS = ["info", "warning", "error"] as const;

type EventsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function readParam(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function makeTabHref(current: Record<string, string | string[] | undefined>, tab: "all" | "errors"): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(current)) {
    const normalized = readParam(value);
    if (!normalized || key === "tab" || key === "severity") {
      continue;
    }
    query.set(key, normalized);
  }
  query.set("tab", tab);
  if (tab === "errors") {
    query.set("severity", "error");
  }
  const suffix = query.toString();
  return `/events${suffix ? `?${suffix}` : ""}`;
}

function makeSelectedHref(current: Record<string, string | string[] | undefined>, eventId: string): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(current)) {
    const normalized = readParam(value);
    if (!normalized) {
      continue;
    }
    query.set(key, normalized);
  }
  query.set("selected", eventId);
  const suffix = query.toString();
  return `/events${suffix ? `?${suffix}` : ""}`;
}

function makeClearSelectedHref(current: Record<string, string | string[] | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(current)) {
    const normalized = readParam(value);
    if (!normalized || key === "selected") {
      continue;
    }
    query.set(key, normalized);
  }
  const suffix = query.toString();
  return `/events${suffix ? `?${suffix}` : ""}`;
}

function payloadPreview(payload: Record<string, unknown>) {
  const text = JSON.stringify(payload);
  if (text === "{}") {
    return "No payload";
  }
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

export default async function EventsPage({ searchParams }: EventsPageProps) {
  const resolvedParams = (await searchParams) ?? {};
  const tab = readParam(resolvedParams.tab) === "errors" ? "errors" : "all";
  const eventType = readParam(resolvedParams.event_type);
  const errorType = readParam(resolvedParams.error_type);
  const category = readParam(resolvedParams.category);
  const severity = tab === "errors" ? "error" : readParam(resolvedParams.severity);
  const strategyName = readParam(resolvedParams.strategy_name);
  const instrument = readParam(resolvedParams.instrument);
  const correlationId = readParam(resolvedParams.correlation_id);
  const selectedId = readParam(resolvedParams.selected);
  const limitValue = readParam(resolvedParams.limit);
  const limit = Number.parseInt(limitValue || "150", 10);

  const events = await getDomainEvents({
    limit: Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 500) : 150,
    eventType: eventType || undefined,
    errorType: errorType || undefined,
    category: category || undefined,
    severity: severity || undefined,
    strategyName: strategyName || undefined,
    instrument: instrument || undefined,
    correlationId: correlationId || undefined,
  });

  const selectedEvent = selectedId ? (events.find((event) => String(event.id) === selectedId) ?? null) : null;

  return (
    <main className="console-page console-page--dense">
      <StickyToolbar className="toolbar-events">
        <div className="toolbar-group">
          <Link href={makeTabHref(resolvedParams, "all")} className={`console-chip${tab === "all" ? " is-active" : ""}`}>
            All
          </Link>
          <Link href={makeTabHref(resolvedParams, "errors")} className={`console-chip${tab === "errors" ? " is-active" : ""}`}>
            Errors
          </Link>
        </div>
        <div className="toolbar-group">
          <ResetHistoryButton />
        </div>
      </StickyToolbar>

      <Panel title="Filters" priority="passive" tone="inactive" compact>
        <form className="console-form-grid" method="get">
          <input type="hidden" name="tab" value={tab} />
          <label>
            <span className="console-kicker">{tab === "errors" ? "Error" : "Event"}</span>
            {tab === "errors" ? (
              <input className="console-input" name="error_type" defaultValue={errorType} placeholder="IGBrokerError" />
            ) : (
              <select className="console-select" name="event_type" defaultValue={eventType}>
                <option value="">All</option>
                {EVENT_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            )}
          </label>

          <label>
            <span className="console-kicker">Category</span>
            <select className="console-select" name="category" defaultValue={category}>
              <option value="">All</option>
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="console-kicker">Severity</span>
            <select className="console-select" name="severity" defaultValue={severity} disabled={tab === "errors"}>
              <option value="">All</option>
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {tab === "errors" ? <input type="hidden" name="severity" value="error" /> : null}
          </label>

          <label>
            <span className="console-kicker">Strategy</span>
            <input className="console-input" name="strategy_name" defaultValue={strategyName} placeholder="mean_reversion" />
          </label>
          <label>
            <span className="console-kicker">Instrument</span>
            <input className="console-input" name="instrument" defaultValue={instrument} placeholder="CS.D.EURUSD.CFD.IP" />
          </label>
          <label>
            <span className="console-kicker">Correlation</span>
            <input className="console-input" name="correlation_id" defaultValue={correlationId} placeholder="ent-..." />
          </label>
          <label>
            <span className="console-kicker">Limit</span>
            <input className="console-input" name="limit" defaultValue={String(limit)} inputMode="numeric" />
          </label>

          <div className="console-inline-actions">
            <button type="submit" className="console-button">
              Apply
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="Event Log" priority="primary" tone={tab === "errors" ? "negative" : "neutral"} compact>
        <CompactTable
          rows={events}
          emptyLabel="No events match the current filters."
          getRowTone={(row) => (row.severity === "error" ? "negative" : row.severity === "warning" ? "warning" : "neutral")}
          getRowActive={(row) => row.id === selectedEvent?.id}
          columns={[
            {
              key: "time",
              header: "Time",
              render: (row) => (
                <Link href={makeSelectedHref(resolvedParams, String(row.id))} className="block w-full">
                  {formatDateTime(row.created_at)}
                </Link>
              ),
            },
            {
              key: "sev",
              header: "Severity",
              render: (row) => (
                <Link href={makeSelectedHref(resolvedParams, String(row.id))} className="block w-full">
                  <StatusPill label={row.severity} tone={row.severity === "error" ? "negative" : row.severity === "warning" ? "warning" : "neutral"} />
                </Link>
              ),
            },
            {
              key: "event",
              header: "Event",
              render: (row) => (
                <Link href={makeSelectedHref(resolvedParams, String(row.id))} className="block w-full">
                  {row.event_type}
                </Link>
              ),
            },
            {
              key: "title",
              header: "Title",
              render: (row) => (
                <Link href={makeSelectedHref(resolvedParams, String(row.id))} className="block w-full">
                  {row.title}
                </Link>
              ),
            },
            {
              key: "source",
              header: "Source",
              render: (row) => (
                <Link href={makeSelectedHref(resolvedParams, String(row.id))} className="block w-full">
                  {row.strategy_name ?? row.source}
                </Link>
              ),
            },
          ]}
        />
      </Panel>

      {selectedEvent ? (
        <div className="fixed inset-0 z-40">
          <Link
            href={makeClearSelectedHref(resolvedParams)}
            className="absolute inset-0 bg-[rgba(6,18,28,0.16)] backdrop-blur-[4px] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),inset_0_0_120px_rgba(6,18,28,0.1)]"
            aria-label="Close event details"
          />
          <aside
            className="absolute right-0 w-full max-w-[620px] overflow-x-hidden border-l border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_96%,transparent)] shadow-[var(--shadow-raised)] backdrop-blur-[16px]"
            style={{ top: 0, height: "100vh" }}
          >
            <div className="flex items-start justify-between gap-3 border-b border-[color:var(--border)] px-5 py-4">
              <div className="min-w-0 flex-1">
                <div className="text-[1rem] font-semibold tracking-[-0.01em]">Selected Event</div>
                <p className="text-[0.82rem] text-[color:var(--text-secondary)]">Event context and payload details.</p>
              </div>
              <Link
                href={makeClearSelectedHref(resolvedParams)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
                aria-label="Close event details"
              >
                <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
                  <path d="M5.22 5.22a.75.75 0 0 1 1.06 0L10 8.94l3.72-3.72a.75.75 0 1 1 1.06 1.06L11.06 10l3.72 3.72a.75.75 0 0 1-1.06 1.06L10 11.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06L8.94 10 5.22 6.28a.75.75 0 0 1 0-1.06Z" fill="currentColor" />
                </svg>
              </Link>
            </div>
            <div className="flex h-[calc(100%-73px)] flex-col gap-3 overflow-y-auto p-5">
              <div className="summary-bar">
                <div className="summary-bar__item">
                  <span>Severity</span>
                  <strong>{selectedEvent.severity}</strong>
                  <em>{selectedEvent.category}</em>
                </div>
                <div className="summary-bar__item">
                  <span>Time</span>
                  <strong>{formatDateTime(selectedEvent.created_at)}</strong>
                  <em>{selectedEvent.correlation_id ?? "no correlation"}</em>
                </div>
                <div className="summary-bar__item">
                  <span>Source</span>
                  <strong>{selectedEvent.strategy_name ?? selectedEvent.source}</strong>
                  <em>{selectedEvent.instrument ?? "system"}</em>
                </div>
              </div>

              <div className="detail-block">
                <span className="console-kicker">Summary</span>
                <p>{selectedEvent.title}</p>
                <p>{selectedEvent.message ?? "No message provided."}</p>
              </div>

              <div className="detail-block">
                <span className="console-kicker">Payload</span>
                <p className="break-words whitespace-pre-wrap">{payloadPreview(selectedEvent.payload_json)}</p>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </main>
  );
}
