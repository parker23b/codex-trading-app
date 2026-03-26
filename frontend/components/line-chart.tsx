type LineChartPoint = {
  label: string;
  value: number;
};

type LineChartProps = {
  title: string;
  subtitle: string;
  points: LineChartPoint[];
  latestValue: string;
  delta?: string;
  tone?: "positive" | "negative" | "neutral";
};

function buildPath(points: LineChartPoint[], width: number, height: number, padding: number) {
  if (points.length === 0) {
    return "";
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return points
    .map((point, index) => {
      const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
      const y = height - padding - ((point.value - min) / range) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function LineChart({ title, subtitle, points, latestValue, delta, tone = "neutral" }: LineChartProps) {
  const width = 620;
  const height = 250;
  const padding = 24;
  const path = buildPath(points, width, height, padding);
  const lastPoint = points[points.length - 1];

  return (
    <section className="card chart-card">
      <div className="card-header">
        <div>
          <h2>{title}</h2>
          <p className="muted">{subtitle}</p>
        </div>
        <div className="chart-highlight">
          <div className="chart-value">{latestValue}</div>
          {delta ? <div className={`metric-change ${tone}`}>{delta}</div> : null}
        </div>
      </div>
      <div className="chart-frame">
        <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label={title}>
          <defs>
            <linearGradient id="equityGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.24" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path className="chart-area" d={`${path} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`} fill="url(#equityGradient)" />
          <path className="chart-line" d={path} fill="none" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          {lastPoint ? (
            <circle
              className="chart-dot"
              cx={padding + ((points.length - 1) / Math.max(points.length - 1, 1)) * (width - padding * 2)}
              cy={(() => {
                const values = points.map((point) => point.value);
                const min = Math.min(...values);
                const max = Math.max(...values);
                const range = max - min || 1;
                return height - padding - ((lastPoint.value - min) / range) * (height - padding * 2);
              })()}
              r="6"
            />
          ) : null}
        </svg>
        <div className="chart-axis">
          {points.map((point, index) => (
            <span key={`${point.label}-${index}`}>{point.label}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
