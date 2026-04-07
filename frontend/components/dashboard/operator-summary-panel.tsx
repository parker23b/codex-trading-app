"use client";

import { Card } from "@/components/ui/card";
import { OperatorSummaryReview, PossibleContributor, ReviewObservation, SupportingMetric } from "@/lib/types";

type OperatorSummaryPanelProps = {
  review: OperatorSummaryReview;
};

function formatMetric(metric: SupportingMetric) {
  if (metric.value === null || metric.value === undefined) {
    return "n/a";
  }
  if (typeof metric.value === "number") {
    if (metric.unit === "pct") {
      return `${metric.value.toFixed(2)}%`;
    }
    if (metric.unit === "ccy") {
      return metric.value.toFixed(2);
    }
    return metric.value.toString();
  }
  return metric.value;
}

function formatDelta(metric: SupportingMetric) {
  if (metric.delta_value === null || metric.delta_value === undefined || typeof metric.delta_value !== "number") {
    return null;
  }
  const sign = metric.delta_value > 0 ? "+" : "";
  return `${sign}${metric.delta_value.toFixed(1)}% vs baseline`;
}

function ObservationRow({ observation }: { observation: ReviewObservation }) {
  return (
    <article className={`review-observation review-observation--${observation.severity}`}>
      <div className="review-observation__header">
        <strong>{observation.label}</strong>
        <span className="review-badge">{observation.severity}</span>
      </div>
      <p>{observation.detail}</p>
      <div className="review-observation__meta">
        <span>{Math.round(observation.confidence * 100)}% confidence</span>
        <span>{observation.time_scope}</span>
      </div>
    </article>
  );
}

function ContributorRow({ contributor }: { contributor: PossibleContributor }) {
  return (
    <article className="review-contributor">
      <strong>{contributor.label}</strong>
      <p>{contributor.detail}</p>
      <div className="review-observation__meta">
        <span>{Math.round(contributor.confidence * 100)}% confidence</span>
        <span>{contributor.time_scope}</span>
      </div>
    </article>
  );
}

export function OperatorSummaryPanel({ review }: OperatorSummaryPanelProps) {
  const generatedAt = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  }).format(new Date(review.metadata.generated_at));

  const topAttention = review.derived_observations.slice(0, 3);
  const explanation =
    review.ai_summary?.summary ??
    "Deterministic review mode is active. The explanation layer is disabled, so operator guidance is coming from ranked backend observations only.";

  return (
    <Card title="Operator Summary" subtitle="Read-only review of change, concentration, anomalies, and operator attention.">
      <section className="review-panel__section">
        <div className="review-panel__label">Hard Metrics</div>
        <div className="review-metrics-grid">
          {review.supporting_metrics.slice(0, 4).map((metric) => (
            <div className="review-metric" key={metric.key}>
              <span className="eyebrow">{metric.label}</span>
              <strong>{formatMetric(metric)}</strong>
              {formatDelta(metric) ? <span className={`review-trend review-trend--${metric.trend}`}>{formatDelta(metric)}</span> : <span className="review-trend review-trend--unknown">No baseline</span>}
            </div>
          ))}
        </div>
      </section>

      <section className="review-panel__section">
        <div className="review-panel__label">Top Attention Items</div>
        <div className="review-stack">
          {topAttention.length ? topAttention.map((observation) => <ObservationRow key={observation.code} observation={observation} />) : <div className="status-note status-note--inline">No high-signal abnormal conditions were detected in the current snapshot.</div>}
        </div>
      </section>

      <section className="review-panel__section">
        <div className="review-panel__label">AI Explanation</div>
        <div className="review-explanation">{explanation}</div>
      </section>

      <section className="review-panel__split">
        <div>
          <div className="review-panel__label">Possible Contributors</div>
          <div className="review-stack">
            {review.possible_contributors.length ? review.possible_contributors.slice(0, 3).map((contributor) => <ContributorRow key={contributor.code} contributor={contributor} />) : <div className="status-note status-note--inline">No likely contributors were inferred beyond the observed conditions.</div>}
          </div>
        </div>
        <div>
          <div className="review-panel__label">Warnings And Provenance</div>
          <div className="review-stack">
            {review.warnings.map((warning) => (
              <div className="status-note status-note--inline" key={warning.code}>
                {warning.message}
              </div>
            ))}
            <div className="review-provenance">
              <span>Review #{review.metadata.review_id ?? "pending"}</span>
              <span>{review.metadata.generation_mode === "deterministic_plus_llm" ? "Deterministic + AI" : "Deterministic only"}</span>
              <span>Prompt {review.provenance?.prompt_version ?? "ai-reviewer-v1"}</span>
              <span>Generated {generatedAt}</span>
            </div>
          </div>
        </div>
      </section>
    </Card>
  );
}
