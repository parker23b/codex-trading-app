"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatCurrency, formatInstrumentLabel, formatPercent, formatRelativeDuration, formatSignedCurrency } from "@/lib/format";
import { Position } from "@/lib/types";

type OpenPositionsTableProps = {
  positions: Position[];
};

type PositionState = Position & {
  uiPnl: number;
  closed: boolean;
};

export function OpenPositionsTable({ positions }: OpenPositionsTableProps) {
  const [rows, setRows] = useState<PositionState[]>(
    positions.map((position) => ({
      ...position,
      uiPnl: position.unrealized_pnl ?? 0,
      closed: false,
    })),
  );
  const [message, setMessage] = useState<string | null>(null);
  const [flashId, setFlashId] = useState<number | null>(null);

  useEffect(() => {
    setRows(
      positions.map((position) => ({
        ...position,
        uiPnl: position.unrealized_pnl ?? 0,
        closed: false,
      })),
    );
  }, [positions]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setRows((current) => {
        const nextRows = current.map((row, index) => {
          if (row.closed) {
            return row;
          }
          const drift = ((index % 2 === 0 ? 1 : -1) * (row.uiPnl === 0 ? 1.4 : Math.abs(row.uiPnl) * 0.035));
          const nextPnl = Number((row.uiPnl + drift).toFixed(2));
          return {
            ...row,
            uiPnl: nextPnl,
            current_price: Number(((row.current_price ?? row.open_price) + drift / Math.max(row.size, 1)).toFixed(2)),
          };
        });
        const activeRow = nextRows.find((row) => !row.closed);
        setFlashId(activeRow?.id ?? null);
        return nextRows;
      });
    }, 2400);

    return () => window.clearInterval(interval);
  }, []);

  const activeRows = useMemo(() => rows.filter((row) => !row.closed), [rows]);

  const handleClose = (id: number, instrument: string) => {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, closed: true } : row)));
    setMessage(`Simulated close queued for ${formatInstrumentLabel(instrument)}.`);
  };

  const handleOverrideToggle = (id: number) => {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, manual_override: !row.manual_override } : row)),
    );
  };

  if (activeRows.length === 0) {
    return <div className="empty-state">No open positions right now.</div>;
  }

  return (
    <div className="table-shell">
      <table className="table action-table">
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Strategy</th>
            <th>Duration</th>
            <th>PnL</th>
            <th>Risk</th>
            <th>Override</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {activeRows.map((position) => (
            <tr key={position.id}>
              <td>
                <div className="cell-stack">
                  <strong>{formatInstrumentLabel(position.instrument)}</strong>
                  <span className="muted">{position.direction} {position.size} at {formatCurrency(position.open_price)}</span>
                </div>
              </td>
              <td>
                <div className="cell-stack">
                  <StatusBadge label={position.strategy_name} tone="neutral" />
                  {position.reason ? <span className="muted">{position.reason}</span> : null}
                </div>
              </td>
              <td>{formatRelativeDuration(position.open_time)}</td>
              <td className={position.uiPnl >= 0 ? `value-positive ${flashId === position.id ? "live-pulse" : ""}` : `value-negative ${flashId === position.id ? "live-pulse" : ""}`}>
                <div className="cell-stack">
                  <strong>{formatSignedCurrency(position.uiPnl)}</strong>
                  <span className="muted">Px {formatCurrency(position.current_price ?? position.open_price)}</span>
                </div>
              </td>
              <td>
                <div className="cell-stack">
                  <strong>{formatPercent(position.risk_percent ?? 0)}</strong>
                  <StatusBadge
                    label={(position.risk_percent ?? 0) < 1 ? "Safe" : (position.risk_percent ?? 0) < 1.5 ? "Watch" : "Risk"}
                    tone={(position.risk_percent ?? 0) < 1 ? "positive" : (position.risk_percent ?? 0) < 1.5 ? "warning" : "negative"}
                  />
                </div>
              </td>
              <td>
                <label className="override-toggle">
                  <input
                    type="checkbox"
                    checked={Boolean(position.manual_override)}
                    onChange={() => handleOverrideToggle(position.id)}
                  />
                  <span>{position.manual_override ? "Sim On" : "Sim Off"}</span>
                </label>
              </td>
              <td>
                <button className="button secondary table-action" onClick={() => handleClose(position.id, position.instrument)}>
                  Sim Close
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {message ? <div className="status-note">{message}</div> : null}
    </div>
  );
}
