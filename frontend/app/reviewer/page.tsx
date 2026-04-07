import { OperatorSummaryPanel } from "@/components/dashboard/operator-summary-panel";
import { getOperatorSummaryReview } from "@/lib/api";

export default async function ReviewerPage() {
  const review = await getOperatorSummaryReview();

  return (
    <main className="reviewer-page">
      <section className="page-grid">
        <OperatorSummaryPanel review={review} />
      </section>
    </main>
  );
}
