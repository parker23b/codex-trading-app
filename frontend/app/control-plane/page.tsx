import { ControlPlaneLive } from "@/components/control-plane/control-plane-live";
import { EMPTY_CONTROL_PLANE_SUMMARY, getControlPlaneSummary, withFallback } from "@/lib/api";

export default async function ControlPlanePage() {
  const summary = await withFallback(() => getControlPlaneSummary(), EMPTY_CONTROL_PLANE_SUMMARY);

  return <ControlPlaneLive initialSummary={summary} />;
}
