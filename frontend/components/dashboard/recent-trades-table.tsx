import { StatusBadge } from "@/components/ui/status-badge";
import { formatInstrumentLabel, formatSignedCurrency } from "@/lib/format";
import { Trade } from "@/lib/types";

type RecentTradesTableProps = {
  trades: Trade[];
};

export function RecentTradesTable({ trades }: RecentTradesTableProps) {
  if (trades.length === 0) {
    return <div className="empty-state">No trades recorded yet.</div>;
  }

  return (
    <div className="table-shell">
      <table className="table analysis-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Instrument</th>
            <th>Outcome</th>
            <th>PnL</th>
            <th>R Multiple</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td data-label="Strategy"><StatusBadge label={trade.strategy_name} tone="neutral" /></td>
              <td data-label="Instrument">{formatInstrumentLabel(trade.instrument)}</td>
              <td data-label="Outcome">
                <StatusBadge label={trade.pnl >= 0 ? "Win" : "Loss"} tone={trade.pnl >= 0 ? "positive" : "negative"} />
              </td>
              <td data-label="PnL" className={trade.pnl >= 0 ? "value-positive" : "value-negative"}>{formatSignedCurrency(trade.pnl)}</td>
              <td data-label="R Multiple">{trade.r_multiple ? `${trade.r_multiple.toFixed(1)}R` : "—"}</td>
              <td data-label="Rationale" className="muted">{trade.reason ?? "No annotation"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
