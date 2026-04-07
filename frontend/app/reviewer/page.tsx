import { OperatorSummaryPanel } from "@/components/dashboard/operator-summary-panel";
import { ReviewHistoryRail } from "@/components/reviewer/review-history-rail";
import { getOperatorSummaryReview, getReviewHistory } from "@/lib/api";

export default async function ReviewerPage() {
  const [review, history] = await Promise.all([
    getOperatorSummaryReview(),
    getReviewHistory("operator_summary", 8),
  ]);

  return (
    <main className="reviewer-page">
      <section className="reviewer-hero">
        <div className="reviewer-hero__copy">
          <span className="eyebrow">AI Reviewer</span>
          <h2>Operational review with room for evidence, attention, and audit trail.</h2>
          <p className="muted">
            This page separates hard metrics from detected observations, possible contributors, warnings, and reviewer provenance so the summary reads like an ops console instead of a dashboard widget.
          </p>
        </div>
        <div className="reviewer-hero__stats">
          <div className="reviewer-hero__stat">
            <span className="eyebrow">Current Review</span>
            <strong>#{review.metadata.review_id ?? "pending"}</strong>
          </div>
          <div className="reviewer-hero__stat">
            <span className="eyebrow">Mode</span>
            <strong>{review.metadata.generation_mode === "deterministic_plus_llm" ? "Deterministic + AI" : "Deterministic"}</strong>
          </div>
          <div className="reviewer-hero__stat">
            <span className="eyebrow">History Loaded</span>
            <strong>{history.length}</strong>
          </div>
        </div>
      </section>
      <section className="page-grid">
        <div className="reviewer-layout">
          <div className="reviewer-layout__main">
            <OperatorSummaryPanel review={review} />
          </div>
          <aside className="reviewer-layout__rail">
            <ReviewHistoryRail items={history} />
          </aside>
        </div>
      </section>
    </main>
  );
}
