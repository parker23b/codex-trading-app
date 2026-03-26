import { Card } from "@/components/ui/card";
import { formatPrice } from "@/lib/format";

type StrategyTapeRow = {
  name: string;
  instrument: string;
  instrumentLabel: string;
  runtimeKey?: string;
  brokerReference?: string | null;
  hasOpenPosition?: boolean;
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
            <article key={row.runtimeKey ?? `${row.name}:${row.instrument}`} className="strategy-tape__row">
              <div>
                <div className="eyebrow">{row.name}</div>
                <strong>{row.instrumentLabel}</strong>
                <div className="muted">
                  {row.hasOpenPosition ? row.brokerReference ?? "position open" : "scan runtime"}
                </div>
              </div>
              <div className="strategy-tape__price">{row.lastPrice != null ? formatPrice(row.lastPrice, row.instrument) : "Waiting..."}</div>
            </article>
          ))}
        </div>
      )}
    </Card>
  );
}
