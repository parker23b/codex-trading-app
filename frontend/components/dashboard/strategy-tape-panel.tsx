import { Card } from "@/components/ui/card";
import { formatIdentifierDisplay, formatPrice } from "@/lib/format";
import { SafeIdentifier } from "@/lib/types";

type StrategyTapeRow = {
  name: string;
  instrument: string;
  instrumentLabel: string;
  runtimeKey?: string;
  brokerReference?: SafeIdentifier | string | null;
  hasOpenPosition?: boolean;
  lastPrice?: number | null;
};

type StrategyTapePanelProps = {
  rows: StrategyTapeRow[];
};

export function StrategyTapePanel({ rows }: StrategyTapePanelProps) {
  const visibleRows = rows.slice(0, 6);

  return (
    <Card
      title="Active Runtimes"
      subtitle={rows.length > visibleRows.length ? `Showing ${visibleRows.length} of ${rows.length} live runtimes.` : "Latest broker price per live runtime."}
      className="card--compact card--full-width board-surface board-surface--rail"
    >
      {rows.length === 0 ? (
        <div className="empty-state">No running strategies are publishing broker prices yet.</div>
      ) : (
        <div className="strategy-tape">
          {visibleRows.map((row) => (
            <article key={row.runtimeKey ?? `${row.name}:${row.instrument}`} className="strategy-tape__row">
              <div>
                <div className="eyebrow">{row.name}</div>
                <strong>{row.instrumentLabel}</strong>
                <div className="muted">
                  {row.hasOpenPosition ? formatIdentifierDisplay(row.brokerReference) ?? "position open" : "scan runtime"}
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
