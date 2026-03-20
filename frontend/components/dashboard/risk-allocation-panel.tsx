import { Card } from "@/components/ui/card";
import { formatInstrumentLabel, formatPercent } from "@/lib/format";

type InstrumentAllocation = {
  instrument: string;
  allocation: number;
};

type RiskAllocationPanelProps = {
  longExposure: number;
  shortExposure: number;
  allocations: InstrumentAllocation[];
};

export function RiskAllocationPanel({
  longExposure,
  shortExposure,
  allocations,
}: RiskAllocationPanelProps) {
  const totalDirectional = Math.max(longExposure + shortExposure, 1);

  return (
    <Card title="Allocation" subtitle="Directional split and position sizing.">
      <div className="allocation-split">
        <div className="allocation-split__row">
          <div className="allocation-split__meta">
            <span>Gross Long vs Short</span>
            <span>{formatPercent((longExposure / totalDirectional) * 100)} / {formatPercent((shortExposure / totalDirectional) * 100)}</span>
          </div>
          <div className="allocation-split__track">
            <div className="allocation-split__long" style={{ width: `${(longExposure / totalDirectional) * 100}%` }} />
            <div className="allocation-split__short" style={{ width: `${(shortExposure / totalDirectional) * 100}%` }} />
          </div>
        </div>
      </div>
      <div className="status-note">Allocation uses gross exposure share, so a balanced book can still be large overall.</div>
      <div className="bar-chart">
        {allocations.map((allocation) => (
          <div className="bar-row" key={allocation.instrument}>
            <div className="bar-meta">
              <span>{formatInstrumentLabel(allocation.instrument)}</span>
              <span>{formatPercent(allocation.allocation)}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${allocation.allocation}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
