"use client";

import { InstrumentRow } from "@/components/markets/instrument-row";
import { MarketInstrument } from "@/lib/types";

type InstrumentsTableProps = {
  instruments: MarketInstrument[];
  starredIds: string[];
  onToggleStar: (instrumentId: string) => void;
};

export function InstrumentsTable({ instruments, starredIds, onToggleStar }: InstrumentsTableProps) {
  if (!instruments.length) {
    return <div className="empty-state">No instruments match the current filters.</div>;
  }

  return (
    <div className="table-shell">
      <table className="table analysis-table markets-table">
        <colgroup>
          <col className="markets-table__col markets-table__col--instrument" />
          <col className="markets-table__col markets-table__col--status" />
          <col className="markets-table__col markets-table__col--tradable" />
          <col className="markets-table__col markets-table__col--activity" />
          <col className="markets-table__col markets-table__col--strategy" />
          <col className="markets-table__col markets-table__col--price" />
        </colgroup>
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Status</th>
            <th>Tradable</th>
            <th>Activity</th>
            <th>Strategy Compatibility</th>
            <th>Price / Change</th>
          </tr>
        </thead>
        <tbody>
          {instruments.map((instrument) => (
            <InstrumentRow
              key={instrument.id}
              instrument={instrument}
              starred={starredIds.includes(instrument.id)}
              onToggleStar={onToggleStar}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
