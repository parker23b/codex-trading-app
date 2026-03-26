"use client";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatPrice, formatSignedPercent } from "@/lib/format";
import { MarketInstrument } from "@/lib/types";

type InstrumentRowProps = {
  instrument: MarketInstrument;
  starred: boolean;
  onToggleStar: (instrumentId: string) => void;
};

function statusTone(status: MarketInstrument["status"]) {
  if (status === "OPEN") {
    return "positive" as const;
  }
  if (status === "LIMITED") {
    return "warning" as const;
  }
  return "negative" as const;
}

function activityTone(level: MarketInstrument["activityLevel"]) {
  if (level === "HIGH") {
    return "positive" as const;
  }
  if (level === "MEDIUM") {
    return "warning" as const;
  }
  return "neutral" as const;
}

export function InstrumentRow({ instrument, starred, onToggleStar }: InstrumentRowProps) {
  return (
    <tr>
      <td>
        <div className="instrument-cell">
          <button
            type="button"
            className={`star-button ${starred ? "is-active" : ""}`.trim()}
            aria-label={starred ? `Remove ${instrument.name} from watchlist` : `Add ${instrument.name} to watchlist`}
            onClick={() => onToggleStar(instrument.id)}
          >
            ★
          </button>
          <div className="cell-stack">
            <strong>{instrument.name}</strong>
            <span className="muted">{instrument.symbol}</span>
          </div>
        </div>
      </td>
      <td>
        <StatusBadge label={instrument.status} tone={statusTone(instrument.status)} />
      </td>
      <td>
        <StatusBadge label={instrument.tradable ? "Yes" : "No"} tone={instrument.tradable ? "positive" : "negative"} />
      </td>
      <td>
        <StatusBadge label={instrument.activityLevel} tone={activityTone(instrument.activityLevel)} />
      </td>
      <td>
        <div className="strategy-pill-list">
          {instrument.strategyCompatibility.map((strategy) => (
            <span key={strategy} className="strategy-pill">
              {strategy}
            </span>
          ))}
        </div>
        {instrument.sessionNote ? <div className="status-note status-note--inline">{instrument.sessionNote}</div> : null}
      </td>
      <td>
        <div className="cell-stack">
          <strong>{formatPrice(instrument.price, instrument.symbol)}</strong>
          <span className={instrument.changePercent >= 0 ? "value-positive" : "value-negative"}>
            {formatSignedPercent(instrument.changePercent, 2)}
          </span>
        </div>
      </td>
    </tr>
  );
}
