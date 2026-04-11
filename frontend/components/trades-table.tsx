import { Trade } from "@/lib/types";

type TradesTableProps = {
  trades: Trade[];
};

function formatNumber(value: number) {
  return value.toFixed(2);
}

function formatSignedNumber(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function TradesTable({ trades }: TradesTableProps) {
  if (trades.length === 0) {
    return <div className="empty-state">No trades recorded yet.</div>;
  }

  return (
    <div className="table-shell">
      <table className="table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Instrument</th>
            <th>Direction</th>
            <th>Open</th>
            <th>Close</th>
            <th>PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td data-label="Strategy">{trade.strategy_name}</td>
              <td data-label="Instrument">{trade.instrument}</td>
              <td data-label="Direction">
                <span className={`pill ${trade.direction.toLowerCase()}`}>{trade.direction}</span>
              </td>
              <td data-label="Open">{formatNumber(trade.open_price)}</td>
              <td data-label="Close">{formatNumber(trade.close_price)}</td>
              <td data-label="PnL" className={trade.pnl >= 0 ? "value-positive" : "value-negative"}>{formatSignedNumber(trade.pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
