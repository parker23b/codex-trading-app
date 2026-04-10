import { ControlPlaneLive } from "@/components/control-plane/control-plane-live";
import { EMPTY_CONTROL_PLANE_SUMMARY, getControlPlaneSummary, loadWithMeta } from "@/lib/api";

export default async function ControlPlanePage() {
  const summary = await loadWithMeta(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY);

  return <ControlPlaneLive initialSummary={summary.data} initialSummaryError={summary.error} />;
}
