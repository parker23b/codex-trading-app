import Link from "next/link";

import { Card } from "@/components/card";
import { StatusBadge } from "@/components/ui/status-badge";
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

function badgeTone(severity: string): "positive" | "negative" | "warning" | "neutral" {
  if (severity === "error") {
    return "negative";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}

function payloadPreview(payload: Record<string, unknown>) {
  const text = JSON.stringify(payload, null, 2);
  return text === "{}" ? "No payload" : text;
}

export default async function EventsPage({ searchParams }: EventsPageProps) {
  const resolvedParams = (await searchParams) ?? {};
  const eventType = readParam(resolvedParams.event_type);
  const category = readParam(resolvedParams.category);
  const severity = readParam(resolvedParams.severity);
  const strategyName = readParam(resolvedParams.strategy_name);
  const instrument = readParam(resolvedParams.instrument);
  const correlationId = readParam(resolvedParams.correlation_id);
  const limitValue = readParam(resolvedParams.limit);
  const limit = Number.parseInt(limitValue || "150", 10);

  const events = await getDomainEvents({
    limit: Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 500) : 150,
    eventType: eventType || undefined,
    category: category || undefined,
    severity: severity || undefined,
    strategyName: strategyName || undefined,
    instrument: instrument || undefined,
    correlationId: correlationId || undefined,
  });

  return (
    <main className="events-page">
      <section className="events-hero">
        <div className="events-hero__copy">
          <span className="eyebrow">Event Journal</span>
          <h2>Structured operational history for what happened, in what order, and why.</h2>
          <p className="muted">
            Filter the append-only timeline by event type, category, severity, strategy, instrument, or correlation id to inspect specific trade narratives and system transitions.
          </p>
        </div>
        <div className="events-hero__stats">
          <div className="events-hero__stat">
            <span className="eyebrow">Loaded</span>
            <strong>{events.length}</strong>
          </div>
          <div className="events-hero__stat">
            <span className="eyebrow">Event Type</span>
            <strong>{eventType || "All"}</strong>
          </div>
          <div className="events-hero__stat">
            <span className="eyebrow">Correlation</span>
            <strong>{correlationId || "Any"}</strong>
          </div>
        </div>
      </section>

      <section className="page-grid">
        <Card
          title="Filters"
          subtitle="Use exact event type filters for execution milestones like position opened, order rejected, or runtime transitions."
        >
          <form className="events-filters" method="get">
            <label>
              <span className="eyebrow">Event Type</span>
              <select name="event_type" defaultValue={eventType}>
                <option value="">All event types</option>
                {EVENT_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className="eyebrow">Category</span>
              <select name="category" defaultValue={category}>
                <option value="">All categories</option>
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className="eyebrow">Severity</span>
              <select name="severity" defaultValue={severity}>
                <option value="">All severities</option>
                {SEVERITY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className="eyebrow">Strategy</span>
              <input name="strategy_name" defaultValue={strategyName} placeholder="mean_reversion" />
            </label>

            <label>
              <span className="eyebrow">Instrument</span>
              <input name="instrument" defaultValue={instrument} placeholder="CS.D.EURUSD.CFD.IP" />
            </label>

            <label>
              <span className="eyebrow">Correlation ID</span>
              <input name="correlation_id" defaultValue={correlationId} placeholder="ent-..." />
            </label>

            <label>
              <span className="eyebrow">Limit</span>
              <input name="limit" defaultValue={String(limit)} inputMode="numeric" />
            </label>

            <div className="events-filters__actions">
              <button type="submit" className="button">
                Apply Filters
              </button>
              <Link href="/events" className="button secondary">
                Reset
              </Link>
            </div>
          </form>
        </Card>
      </section>

      <section className="page-grid">
        <Card
          title="Recent Events"
          subtitle="Newest first. Expand payload to inspect structured context for each event."
        >
          {events.length === 0 ? (
            <div className="empty-state">No events matched the current filters.</div>
          ) : (
            <div className="table-shell">
              <table className="table analysis-table events-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Event</th>
                    <th>Severity</th>
                    <th>Scope</th>
                    <th>Narrative</th>
                    <th>Context</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <strong>{formatDateTime(event.created_at)}</strong>
                        <div className="muted">#{event.id}</div>
                      </td>
                      <td>
                        <strong>{event.title}</strong>
                        <div className="muted">{event.event_type}</div>
                        <div className="muted">{event.category}</div>
                      </td>
                      <td>
                        <StatusBadge label={event.severity} tone={badgeTone(event.severity)} />
                      </td>
                      <td>
                        <strong>{event.strategy_name ?? "system"}</strong>
                        <div className="muted">{event.instrument ?? "no instrument"}</div>
                      </td>
                      <td>
                        <div>{event.message ?? "No message provided."}</div>
                        {event.correlation_id ? <div className="muted">Correlation: {event.correlation_id}</div> : null}
                        {event.runtime_id ? <div className="muted">Runtime: {event.runtime_id}</div> : null}
                      </td>
                      <td>
                        <details className="events-payload">
                          <summary>Payload</summary>
                          <pre>{payloadPreview(event.payload_json)}</pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </section>
    </main>
  );
}
