import { formatCurrency, formatPercent, formatSignedCurrency, formatSignedPercent } from "@/lib/format";

type DecisionMetric = {
  label: string;
  value: string;
  context: string;
  tone: "positive" | "negative" | "warning" | "neutral";
};

type KpiBarProps = {
  accountValue: number;
  accountChangePercent: number;
  dailyPnl: number;
  dailyPnlPercent: number;
  openRiskPercent: number;
  winRate: number;
  riskRewardRatio: number;
};

export function KpiBar({
  accountValue,
  accountChangePercent,
  dailyPnl,
  dailyPnlPercent,
  openRiskPercent,
  winRate,
  riskRewardRatio,
}: KpiBarProps) {
  const metrics: DecisionMetric[] = [
    {
      label: "Account Value",
      value: formatCurrency(accountValue),
      context: `${formatSignedPercent(accountChangePercent)} today`,
      tone: accountChangePercent >= 0 ? "positive" : "negative",
    },
    {
      label: "Daily PnL",
      value: formatSignedCurrency(dailyPnl),
      context: `${formatSignedPercent(dailyPnlPercent)} session move`,
      tone: dailyPnl >= 0 ? "positive" : "negative",
    },
    {
      label: "Open Risk",
      value: formatPercent(openRiskPercent),
      context: openRiskPercent < 2 ? "Contained" : openRiskPercent < 4 ? "Watch size" : "Reduce risk",
      tone: openRiskPercent < 2 ? "positive" : openRiskPercent < 4 ? "warning" : "negative",
    },
    {
      label: "Win Rate",
      value: `${Math.round(winRate)}%`,
      context: "Last 30 trades",
      tone: winRate >= 55 ? "positive" : winRate >= 45 ? "warning" : "negative",
    },
    {
      label: "Risk / Reward",
      value: `${riskRewardRatio.toFixed(2)}R`,
      context: riskRewardRatio >= 1.5 ? "Healthy expectancy" : "Needs review",
      tone: riskRewardRatio >= 1.5 ? "positive" : "warning",
    },
  ];

  return (
    <section className="kpi-bar">
      {metrics.map((metric) => (
        <article key={metric.label} className="kpi-card">
          <div className="eyebrow">{metric.label}</div>
          <div className="kpi-card__value">{metric.value}</div>
          <div className={`kpi-card__context ${metric.tone}`}>{metric.context}</div>
        </article>
      ))}
    </section>
  );
}

