"use client";

import { useMemo } from "react";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatCurrency, formatInstrumentLabel, formatPercent, formatPrice, formatRelativeDuration, formatSignedCurrency } from "@/lib/format";
import { Position } from "@/lib/types";

type OpenPositionsTableProps = {
  positions: Position[];
};

export function OpenPositionsTable({ positions }: OpenPositionsTableProps) {
  const activeRows = useMemo(() => positions.filter((row) => row.is_open), [positions]);

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
            <th>Broker Ref</th>
            <th>Duration</th>
            <th>PnL</th>
            <th>Risk</th>
            <th>Override Status</th>
            <th>Execution Status</th>
          </tr>
        </thead>
        <tbody>
          {activeRows.map((position) => (
            <tr key={position.id}>
              <td>
                <div className="cell-stack">
                  <strong>{formatInstrumentLabel(position.instrument)}</strong>
                  <span className="muted">{position.direction} {position.size} at {formatPrice(position.open_price, position.instrument)}</span>
                </div>
              </td>
              <td>
                <div className="cell-stack">
                  <StatusBadge label={position.strategy_name} tone="neutral" />
                  {position.reason ? <span className="muted">{position.reason}</span> : null}
                </div>
              </td>
              <td><span className="muted">{position.broker_reference ?? "pending"}</span></td>
              <td>{formatRelativeDuration(position.open_time)}</td>
              <td className={(position.unrealized_pnl ?? 0) >= 0 ? "value-positive live-pulse" : "value-negative live-pulse"}>
                <div className="cell-stack">
                  <strong>{formatSignedCurrency(position.unrealized_pnl ?? 0)}</strong>
                  <span className="muted">Px {formatPrice(position.current_price ?? position.open_price, position.instrument)}</span>
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
                <StatusBadge
                  label={position.manual_override ? "Manual Override Flagged" : "System Managed"}
                  tone={position.manual_override ? "warning" : "neutral"}
                />
              </td>
              <td>
                <span className="muted">Read-only in dashboard</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
