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
            <td>{trade.strategy_name}</td>
            <td>{trade.instrument}</td>
            <td>
              <span className={`pill ${trade.direction.toLowerCase()}`}>{trade.direction}</span>
            </td>
            <td>{formatNumber(trade.open_price)}</td>
            <td>{formatNumber(trade.close_price)}</td>
            <td className={trade.pnl >= 0 ? "value-positive" : "value-negative"}>{formatSignedNumber(trade.pnl)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
