import { BrokerAuthStatus, StreamHealthStatus } from "@/lib/types";
import { StatusBadge } from "@/components/ui/status-badge";

type ModeIndicatorProps = {
  mode: "DEMO" | "LIVE";
  brokerAuth?: BrokerAuthStatus;
  streamHealth?: StreamHealthStatus;
};

export function ModeIndicator({ mode, brokerAuth, streamHealth }: ModeIndicatorProps) {
  const brokerTone =
    brokerAuth?.state === "connected"
      ? "live"
      : brokerAuth?.state === "disconnected"
        ? "negative"
        : "neutral";
  const streamLabel = !streamHealth?.enabled
    ? "Streaming Off"
    : streamHealth.connected
      ? "Stream Healthy"
      : "Stream Degraded";
  const streamTone = !streamHealth?.enabled ? "neutral" : streamHealth.connected ? "positive" : "warning";
  const modeDetail =
    mode === "LIVE"
      ? "Orders are pointed at the live environment."
      : "Orders are pointed at the demo environment.";

  return (
    <div className="mode-indicator">
      <div>
        <div className="eyebrow">Execution Mode</div>
        <div className="mode-indicator__value">{mode}</div>
        <div className="muted">{modeDetail}</div>
        {brokerAuth ? (
          <div className="mode-indicator__substatus">
            <div className="eyebrow">Broker Auth</div>
            <div className="muted">{brokerAuth.detail}</div>
          </div>
        ) : null}
        {streamHealth ? (
          <div className="mode-indicator__substatus">
            <div className="eyebrow">Price Stream</div>
            <div className="muted">
              {streamHealth.connected
                ? `Connected with ${streamHealth.subscribed_instruments.length} instrument${streamHealth.subscribed_instruments.length === 1 ? "" : "s"} subscribed`
                : streamHealth.last_error ?? streamHealth.last_status ?? "Awaiting stream connection"}
            </div>
          </div>
        ) : null}
      </div>
      <div className="mode-indicator__badges">
        <StatusBadge
          label={mode === "DEMO" ? "Demo Account" : "Live Account"}
          tone={mode === "DEMO" ? "warning" : "neutral"}
        />
        {brokerAuth ? (
          <StatusBadge label={brokerAuth.label} tone={brokerTone} />
        ) : null}
        {streamHealth ? <StatusBadge label={streamLabel} tone={streamTone} /> : null}
      </div>
    </div>
  );
}
