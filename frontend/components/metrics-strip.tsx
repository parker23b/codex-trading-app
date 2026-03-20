export type Metric = {
  label: string;
  value: string;
  change?: string;
  tone?: "positive" | "negative" | "neutral";
};

type MetricsStripProps = {
  metrics: Metric[];
};

export function MetricsStrip({ metrics }: MetricsStripProps) {
  return (
    <section className="metrics-strip">
      {metrics.map((metric) => (
        <article className="metric-card" key={metric.label}>
          <div className="metric-label">{metric.label}</div>
          <div className="metric-value">{metric.value}</div>
          {metric.change ? <div className={`metric-change ${metric.tone ?? "neutral"}`}>{metric.change}</div> : null}
        </article>
      ))}
    </section>
  );
}
