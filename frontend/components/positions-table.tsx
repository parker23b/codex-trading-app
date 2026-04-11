import { Position } from "@/lib/types";

type PositionsTableProps = {
  positions: Position[];
};

function formatNumber(value: number) {
  return value.toFixed(2);
}

export function PositionsTable({ positions }: PositionsTableProps) {
  if (positions.length === 0) {
    return <div className="empty-state">No open positions right now.</div>;
  }

  return (
    <div className="table-shell">
      <table className="table">
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Strategy</th>
            <th>Direction</th>
            <th>Size</th>
            <th>Open Price</th>
            <th>Account</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.id}>
              <td data-label="Instrument">{position.instrument}</td>
              <td data-label="Strategy">{position.strategy_name}</td>
              <td data-label="Direction">
                <span className={`pill ${position.direction.toLowerCase()}`}>{position.direction}</span>
              </td>
              <td data-label="Size">{position.size}</td>
              <td data-label="Open Price">{formatNumber(position.open_price)}</td>
              <td data-label="Account">
                <span className={`pill ${position.account_type.toLowerCase()}`}>{position.account_type}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
