import { CompactTable, Panel, SplitPanel, StatusPill, StatusStrip } from "@/components/console/primitives";
import { getOperatorSummaryReview, getReviewHistory } from "@/lib/api";

function formatMetricValue(value: number | string | null | undefined, unit?: string | null) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (typeof value === "number" && unit === "pct") {
    return `${value.toFixed(2)}%`;
  }
  return String(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default async function ReviewerPage() {
  const [review, history] = await Promise.all([
    getOperatorSummaryReview(),
    getReviewHistory("operator_summary", 8),
  ]);

  const leadObservation = review.derived_observations[0] ?? null;
  const leadTone = leadObservation?.severity === "critical" ? "negative" : leadObservation?.severity === "warning" ? "warning" : "neutral";

  return (
    <main className="console-page">
      <StatusStrip
        items={[
          { label: "Review", value: `#${review.metadata.review_id ?? "pending"}`, tone: "neutral" },
          {
            label: "Lead Issue",
            value: leadObservation ? leadObservation.label : "None",
            tone: leadTone,
            emphasis: "strong",
          },
          {
            label: "Confidence",
            value: leadObservation ? `${Math.round(leadObservation.confidence * 100)}%` : "n/a",
            tone: leadTone,
            emphasis: "strong",
          },
          {
            label: "Warnings",
            value: review.warnings.length,
            tone: review.warnings.length ? "warning" : "positive",
          },
        ]}
      />

      <SplitPanel
        left={
          <Panel title="History" priority="passive" tone="inactive" compact>
            <CompactTable
              dense
              rows={history}
              emptyLabel="No review history yet."
              columns={[
                { key: "id", header: "Review", render: (row) => `#${row.review_id}` },
                { key: "time", header: "Generated", render: (row) => formatTime(row.generated_at) },
                { key: "mode", header: "Mode", render: (row) => (row.generation_mode === "deterministic_plus_llm" ? "AI" : "Deterministic") },
              ]}
            />
          </Panel>
        }
        center={
          <Panel title="Lead Observation" priority="critical" tone={leadTone}>
            {leadObservation ? (
              <div className="detail-stack">
                <div className="summary-bar">
                  <div className="summary-bar__item">
                    <span>Severity</span>
                    <strong>{leadObservation.severity}</strong>
                    <em>{leadObservation.time_scope}</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Confidence</span>
                    <strong>{Math.round(leadObservation.confidence * 100)}%</strong>
                    <em>review confidence</em>
                  </div>
                  <div className="summary-bar__item">
                    <span>Mode</span>
                    <strong>{review.metadata.generation_mode === "deterministic_plus_llm" ? "Deterministic + AI" : "Deterministic"}</strong>
                    <em>{formatTime(review.metadata.generated_at)}</em>
                  </div>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Issue</span>
                  <p>{leadObservation.label}</p>
                  <p>{leadObservation.detail}</p>
                </div>

                <div className="detail-block">
                  <span className="console-kicker">Likely Contributors</span>
                  {review.possible_contributors.slice(0, 3).map((contributor) => (
                    <p key={contributor.code}>
                      {contributor.label}: {contributor.detail}
                    </p>
                  ))}
                </div>

                <CompactTable
                  dense
                  rows={review.supporting_metrics.slice(0, 6)}
                  emptyLabel="No supporting metrics."
                  columns={[
                    { key: "metric", header: "Metric", render: (row) => row.label },
                    { key: "value", header: "Value", render: (row) => formatMetricValue(row.value, row.unit) },
                    { key: "trend", header: "Trend", render: (row) => row.trend },
                  ]}
                />
              </div>
            ) : (
              <div className="console-empty">No current observation.</div>
            )}
          </Panel>
        }
        right={
          <Panel title="Observation List" priority="secondary" tone="neutral">
            <CompactTable
              rows={review.derived_observations}
              emptyLabel="No observations for this run."
              getRowTone={(row) => (row.severity === "critical" ? "negative" : row.severity === "warning" ? "warning" : "neutral")}
              getRowActive={(_, index) => index === 0}
              columns={[
                { key: "obs", header: "Observation", render: (row) => row.label },
                {
                  key: "sev",
                  header: "Severity",
                  render: (row) => <StatusPill label={row.severity} tone={row.severity === "critical" ? "negative" : row.severity === "warning" ? "warning" : "neutral"} />,
                },
                { key: "conf", header: "Conf.", render: (row) => `${Math.round(row.confidence * 100)}%` },
              ]}
            />

            <Panel title="Warnings" priority="passive" tone={review.warnings.length ? "warning" : "inactive"} compact>
              {review.warnings.length ? (
                <div className="detail-stack">
                  {review.warnings.map((warning) => (
                    <StatusPill
                      key={warning.code}
                      label={warning.message}
                      tone={warning.severity === "critical" ? "negative" : warning.severity === "warning" ? "warning" : "neutral"}
                    />
                  ))}
                </div>
              ) : (
                <div className="console-empty">No warnings.</div>
              )}
            </Panel>
          </Panel>
        }
      />
    </main>
  );
}
