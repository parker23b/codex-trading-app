import { ControlPlaneLive } from "@/components/control-plane/control-plane-live";
import { UNAVAILABLE_CONTROL_PLANE_SUMMARY, getControlPlaneSummary, loadWithMeta } from "@/lib/api";

export default async function ControlPlanePage() {
  const summary = await loadWithMeta(() => getControlPlaneSummary());

  return <ControlPlaneLive initialSummary={summary.data ?? UNAVAILABLE_CONTROL_PLANE_SUMMARY} initialSummaryError={summary.error} />;
}
