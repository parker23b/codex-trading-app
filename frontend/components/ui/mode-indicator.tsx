import { BrokerAuthStatus } from "@/lib/types";
import { StatusBadge } from "@/components/ui/status-badge";

type ModeIndicatorProps = {
  mode: "DEMO" | "LIVE";
  brokerAuth?: BrokerAuthStatus;
};

export function ModeIndicator({ mode, brokerAuth }: ModeIndicatorProps) {
  const brokerTone =
    brokerAuth?.state === "connected"
      ? "live"
      : brokerAuth?.state === "disconnected"
        ? "negative"
        : "neutral";
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
      </div>
      <div className="mode-indicator__badges">
        <StatusBadge
          label={mode === "DEMO" ? "Demo Account" : "Live Account"}
          tone={mode === "DEMO" ? "warning" : "neutral"}
        />
        {brokerAuth ? (
          <StatusBadge label={brokerAuth.label} tone={brokerTone} />
        ) : null}
      </div>
    </div>
  );
}
