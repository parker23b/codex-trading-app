type BarChartDatum = {
  label: string;
  value: number;
};

type BarChartProps = {
  title: string;
  subtitle: string;
  data: BarChartDatum[];
};

export function BarChart({ title, subtitle, data }: BarChartProps) {
  const maxValue = Math.max(...data.map((item) => item.value), 1);

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2>{title}</h2>
          <p className="muted">{subtitle}</p>
        </div>
      </div>
      <div className="bar-chart">
        {data.map((item) => (
          <div className="bar-row" key={item.label}>
            <div className="bar-meta">
              <span>{item.label}</span>
              <span>{item.value.toFixed(1)}%</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(item.value / maxValue) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

