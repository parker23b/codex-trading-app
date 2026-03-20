import { Card } from "@/components/ui/card";
import { formatCurrency } from "@/lib/format";

type StrategyTapeRow = {
  name: string;
  instrument: string;
  instrumentLabel: string;
  lastPrice?: number | null;
};

type StrategyTapePanelProps = {
  rows: StrategyTapeRow[];
};

export function StrategyTapePanel({ rows }: StrategyTapePanelProps) {
  return (
    <Card
      title="Running Strategies"
      subtitle="Latest broker price per live strategy runtime."
      className="card--compact card--full-width"
    >
      {rows.length === 0 ? (
        <div className="empty-state">No running strategies are publishing broker prices yet.</div>
      ) : (
        <div className="strategy-tape">
          {rows.map((row) => (
            <article key={`${row.name}:${row.instrument}`} className="strategy-tape__row">
              <div>
                <div className="eyebrow">{row.name}</div>
                <strong>{row.instrumentLabel}</strong>
              </div>
              <div className="strategy-tape__price">{row.lastPrice != null ? formatCurrency(row.lastPrice) : "Waiting..."}</div>
            </article>
          ))}
        </div>
      )}
    </Card>
  );
}
