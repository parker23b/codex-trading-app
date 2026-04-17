import { getOperatorSummaryReview, getReviewHistory } from "@/lib/api";

function formatDateTime(value: string) {
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
    getReviewHistory("operator_summary", 5),
  ]);

  return (
    <main className="console-page">
      <section className="rounded-[22px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface)] p-5 shadow-[var(--shadow-panel)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-[720px]">
            <div className="text-[0.74rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
              Reviewer Route
            </div>
            <h1 className="mt-2 text-[1.5rem] font-semibold tracking-[-0.03em]">
              A.I.M.E.E now lives above the platform, not inside the main
              navigation.
            </h1>
            <p className="mt-3 text-[0.94rem] text-[color:var(--text-secondary)]">
              Use the persistent launcher in the bottom-right corner to open
              A.I.M.E.E from any page. This compatibility route remains
              available for direct access and audit continuity.
            </p>
          </div>
          <div className="min-w-[220px] rounded-[18px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-4 py-3 shadow-[var(--shadow-soft)]">
            <div className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
              Current Lead
            </div>
            <div className="mt-2 text-[1rem] font-semibold">
              {review.derived_observations[0]?.label ??
                "No active reviewer observation"}
            </div>
            <div className="mt-2 text-[0.82rem] text-[color:var(--text-secondary)]">
              {review.warnings.length} warnings · last generated{" "}
              {formatDateTime(review.metadata.generated_at)}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="rounded-[20px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] p-4 shadow-[var(--shadow-soft)]">
          <div className="text-[0.76rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
            Why A.I.M.E.E
          </div>
          <ul className="mt-3 grid gap-2 pl-5 text-[0.86rem] text-[color:var(--text-secondary)]">
            <li>Global launcher and right-side intelligence panel.</li>
            <li>Structured briefing plus read-only Q&amp;A.</li>
            <li>Context-aware summaries based on the current page.</li>
          </ul>
        </article>

        <article className="rounded-[20px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] p-4 shadow-[var(--shadow-soft)]">
          <div className="text-[0.76rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
            Recent Reviews
          </div>
          <div className="mt-3 grid gap-2">
            {history.map((item) => (
              <div
                key={item.review_id}
                className="rounded-[14px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-3">
                <div className="text-[0.84rem] font-semibold">
                  Review #{item.review_id}
                </div>
                <div className="mt-1 text-[0.76rem] text-[color:var(--text-secondary)]">
                  {formatDateTime(item.generated_at)} ·{" "}
                  {item.generation_mode === "deterministic_plus_llm"
                    ? "AI-assisted"
                    : "Deterministic"}
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
