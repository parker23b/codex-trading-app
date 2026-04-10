import Link from "next/link";

import { CompactTable, Panel, SplitPanel, StatusPill, StickyToolbar } from "@/components/console/primitives";
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

  const selectedEvent = events[0] ?? null;

  return (
    <main className="console-page">
      <StickyToolbar>
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

      <SplitPanel
        left={
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
        }
        center={
          <Panel title="Event Log" priority="primary" tone={tab === "errors" ? "negative" : "neutral"}>
            <CompactTable
              rows={events}
              emptyLabel="No events match the current filters."
              getRowTone={(row) => (row.severity === "error" ? "negative" : row.severity === "warning" ? "warning" : "neutral")}
              getRowActive={(_, index) => index === 0}
              columns={[
                { key: "time", header: "Time", render: (row) => formatDateTime(row.created_at) },
                {
                  key: "sev",
                  header: "Severity",
                  render: (row) => <StatusPill label={row.severity} tone={row.severity === "error" ? "negative" : row.severity === "warning" ? "warning" : "neutral"} />,
                },
                { key: "event", header: "Event", render: (row) => row.event_type },
                { key: "title", header: "Title", render: (row) => row.title },
                { key: "source", header: "Source", render: (row) => row.strategy_name ?? row.source },
              ]}
            />
          </Panel>
        }
        right={
          <Panel title="Selected Event" priority="secondary" tone={selectedEvent?.severity === "error" ? "negative" : selectedEvent?.severity === "warning" ? "warning" : "neutral"}>
            {selectedEvent ? (
              <div className="detail-stack">
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
                  <p>{payloadPreview(selectedEvent.payload_json)}</p>
                </div>
              </div>
            ) : (
              <div className="console-empty">No event selected.</div>
            )}
          </Panel>
        }
      />
    </main>
  );
}
