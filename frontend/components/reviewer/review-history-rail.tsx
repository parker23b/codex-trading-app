import { Card } from "@/components/ui/card";
import { ReviewHistoryItem } from "@/lib/types";

type ReviewHistoryRailProps = {
  items: ReviewHistoryItem[];
};

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ReviewHistoryRail({ items }: ReviewHistoryRailProps) {
  return (
    <Card title="Recent Reviews" subtitle="Persisted operator-summary generations for audit context.">
      <div className="review-history-list">
        {items.length ? (
          items.map((item) => (
            <article className="review-history-item" key={item.review_id}>
              <div className="review-history-item__top">
                <strong>Review #{item.review_id}</strong>
                <span className="review-badge">
                  {item.generation_mode === "deterministic_plus_llm" ? "Deterministic + AI" : "Deterministic"}
                </span>
              </div>
              <div className="review-history-item__meta">
                <span>{formatTimestamp(item.generated_at)}</span>
                <span>{item.review_type.replaceAll("_", " ")}</span>
              </div>
              <div className="review-history-item__meta">
                <span>Provider: {item.provider ?? "none"}</span>
                <span>Model: {item.model ?? "n/a"}</span>
              </div>
            </article>
          ))
        ) : (
          <div className="status-note status-note--inline">
            No persisted review history yet. Generating the page will create the first stored record.
          </div>
        )}
      </div>
    </Card>
  );
}
