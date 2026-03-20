"use client";

import { useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";

type TimeFilter = "6 Trades" | "10 Trades" | "16 Trades" | "All";

type EquityPoint = {
  label: string;
  value: number;
  drawdown: number;
};

type EquityPanelProps = {
  points: EquityPoint[];
  latestValue: number;
  delta: number;
};

function buildLine(points: EquityPoint[], width: number, height: number, padding: number, valueKey: "value" | "drawdown") {
  const values = points.map((point) => point[valueKey]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return points
    .map((point, index) => {
      const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
      const y = height - padding - ((point[valueKey] - min) / range) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function EquityPanel({ points, latestValue, delta }: EquityPanelProps) {
  const [filter, setFilter] = useState<TimeFilter>("10 Trades");

  const filteredPoints = useMemo(() => {
    if (filter === "All") {
      return points;
    }
    const counts: Record<Exclude<TimeFilter, "All">, number> = {
      "6 Trades": 6,
      "10 Trades": 10,
      "16 Trades": 16,
    };
    return points.slice(-counts[filter]);
  }, [filter, points]);

  const width = 760;
  const height = 300;
  const padding = 24;
  const equityPath = buildLine(filteredPoints, width, height, padding, "value");
  const drawdownPath = buildLine(filteredPoints, width, height, padding, "drawdown");

  return (
    <Card
      title="Performance"
      subtitle="Recent equity and drawdown by closed trade."
      action={<SegmentedControl options={["6 Trades", "10 Trades", "16 Trades", "All"]} value={filter} onChange={setFilter} />}
      className="equity-panel"
    >
      <div className="equity-panel__summary">
        <div>
          <div className="eyebrow">Equity</div>
          <div className="chart-value">{formatCurrency(latestValue)}</div>
        </div>
        <div className={delta >= 0 ? "value-positive live-pulse" : "value-negative live-pulse"}>
          {formatSignedCurrency(delta)}
        </div>
      </div>
      <div className="equity-panel__chart">
        <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label="Equity chart">
          <path className="drawdown-line" d={drawdownPath} fill="none" strokeWidth="2.5" strokeDasharray="6 5" />
          <path className="chart-line" d={equityPath} fill="none" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="chart-legend">
          <span><i className="legend-swatch legend-swatch--equity" /> Equity</span>
          <span><i className="legend-swatch legend-swatch--drawdown" /> Drawdown</span>
        </div>
        <div className="chart-axis">
          {filteredPoints.map((point) => (
            <span key={point.label}>{point.label}</span>
          ))}
        </div>
      </div>
    </Card>
  );
}
