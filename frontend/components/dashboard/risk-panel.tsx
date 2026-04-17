import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { type RiskConsoleSummary } from "@/lib/risk-allocation";

type RiskPanelProps = {
  summary: RiskConsoleSummary;
};

function getRiskTone(value: number, warningThreshold: number, dangerThreshold: number) {
  if (value >= dangerThreshold) {
    return { label: "Danger", tone: "negative" as const };
  }
  if (value >= warningThreshold) {
    return { label: "Warning", tone: "warning" as const };
  }
  return { label: "Safe", tone: "positive" as const };
}

export function RiskPanel({ summary }: RiskPanelProps) {
  const overall = getRiskTone(summary.totalActiveRiskPercent, 3.5, 5);
  const items = [
    summary.metrics[0],
    summary.metrics[1],
    summary.metrics[2],
    summary.metrics[3],
  ];

  return (
    <Card
      title="Risk"
      subtitle="Canonical portfolio risk summary from allocation, drift, and alerts."
      action={<StatusBadge label={overall.label} tone={overall.tone} />}
      className="risk-panel card--compact board-surface board-surface--rail"
    >
      <div className="risk-grid">
        {items.map((item) => {
          return (
            <div key={item.label} className="risk-item">
              <div>
                <div className="eyebrow">{item.label}</div>
                <div className="risk-item__value">{item.value}</div>
                {item.meta ? <div className="text-xs text-muted-foreground">{item.meta}</div> : null}
              </div>
              <StatusBadge label={item.tone === "negative" ? "Danger" : item.tone === "warning" ? "Warning" : "Nominal"} tone={item.tone === "inactive" ? "neutral" : item.tone} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}
