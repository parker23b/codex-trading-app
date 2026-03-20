import { StatusBadge } from "@/components/ui/status-badge";

type ModeIndicatorProps = {
  mode: "DEMO" | "LIVE";
};

export function ModeIndicator({ mode }: ModeIndicatorProps) {
  return (
    <div className="mode-indicator">
      <div>
        <div className="eyebrow">Execution Mode</div>
        <div className="mode-indicator__value">{mode}</div>
        <div className="muted">Frontend is configured for simulated behavior.</div>
      </div>
      <StatusBadge label={mode === "DEMO" ? "Simulated" : "Live Account"} tone={mode === "DEMO" ? "warning" : "neutral"} />
    </div>
  );
}
