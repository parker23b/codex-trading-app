import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatPercent } from "@/lib/format";

type RiskPanelProps = {
  capitalAtRisk: number;
  largestPosition: number;
  concentration: number;
  drawdown: number;
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

export function RiskPanel({
  capitalAtRisk,
  largestPosition,
  concentration,
  drawdown,
}: RiskPanelProps) {
  const overall = getRiskTone(Math.max(capitalAtRisk, largestPosition, concentration, drawdown), 4, 7);
  const items = [
    { label: "Capital At Risk", value: capitalAtRisk, thresholds: [2, 4] as const },
    { label: "Largest Position", value: largestPosition, thresholds: [15, 25] as const },
    { label: "Concentration", value: concentration, thresholds: [35, 50] as const },
    { label: "Current Drawdown", value: drawdown, thresholds: [3, 6] as const },
  ];

  return (
    <Card
      title="Risk"
      subtitle="Main portfolio risk checks for the current book."
      action={<StatusBadge label={overall.label} tone={overall.tone} />}
      className="risk-panel card--compact"
    >
      <div className="risk-stack">
        {items.map((item) => {
          const status = getRiskTone(item.value, item.thresholds[0], item.thresholds[1]);
          return (
            <div key={item.label} className="risk-item">
              <div>
                <div className="eyebrow">{item.label}</div>
                <div className="risk-item__value">{formatPercent(item.value)}</div>
              </div>
              <StatusBadge label={status.label} tone={status.tone} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}
