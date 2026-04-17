import { Card } from "@/components/ui/card";
import { formatInstrumentLabel, formatPercent } from "@/lib/format";
import { buildRiskAllocationSummary, type RiskConsoleSummary } from "@/lib/risk-allocation";
import { type AllocationExposureSummary } from "@/lib/types";

type RiskAllocationPanelProps = {
  exposure: AllocationExposureSummary;
  summary: RiskConsoleSummary;
};

export function RiskAllocationPanel({ exposure, summary }: RiskAllocationPanelProps) {
  const allocation = buildRiskAllocationSummary(exposure);
  const totalDirectional = Math.max(allocation.longRiskPercent + allocation.shortRiskPercent, 1);
  const netBiasLabel =
    allocation.netRiskPercent > 0.1 ? "Net Long" : allocation.netRiskPercent < -0.1 ? "Net Short" : "Balanced";

  return (
    <Card
      title="Allocation"
      subtitle="Directional and instrument concentration from the live allocation read model."
      className="card--compact allocation-card"
    >
      <div className="allocation-summary">
        <div className="allocation-summary__item">
          <span className="eyebrow">Gross Risk</span>
          <strong>{formatPercent(allocation.grossRiskPercent)}</strong>
        </div>
        <div className="allocation-summary__item">
          <span className="eyebrow">Net Bias</span>
          <strong>{netBiasLabel}</strong>
        </div>
        <div className="allocation-summary__item">
          <span className="eyebrow">Open Lines</span>
          <strong>{allocation.openPositionCount}</strong>
        </div>
      </div>
      <div className="allocation-split">
        <div className="allocation-split__row">
          <div className="allocation-split__meta">
            <span>Gross Long vs Short</span>
            <span>
              {formatPercent((allocation.longRiskPercent / totalDirectional) * 100)} / {formatPercent((allocation.shortRiskPercent / totalDirectional) * 100)}
            </span>
          </div>
          <div className="allocation-split__track">
            <div
              className="allocation-split__long"
              style={{ width: `${(allocation.longRiskPercent / totalDirectional) * 100}%` }}
            />
            <div
              className="allocation-split__short"
              style={{ width: `${(allocation.shortRiskPercent / totalDirectional) * 100}%` }}
            />
          </div>
        </div>
      </div>
      <div className="status-note">
        {summary.lastCycleStatus.meta}. {allocation.reservedIntentCount} reserved intents are holding additional capital outside the live book.
      </div>
      <div className="bar-chart">
        {allocation.topInstruments.map((bucket) => (
          <div className="bar-row" key={bucket.instrument}>
            <div className="bar-meta">
              <span>{formatInstrumentLabel(bucket.instrument)}</span>
              <span>{formatPercent(bucket.totalRiskPercent)}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.min(bucket.utilizationPercent ?? bucket.totalRiskPercent, 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
