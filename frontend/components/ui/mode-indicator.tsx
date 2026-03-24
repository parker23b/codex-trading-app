import { BrokerAuthStatus } from "@/lib/types";
import { StatusBadge } from "@/components/ui/status-badge";

type ModeIndicatorProps = {
  mode: "DEMO" | "LIVE";
  backendMode?: "live" | "dev-fallback";
  brokerAuth?: BrokerAuthStatus;
};

export function ModeIndicator({ mode, backendMode = "live", brokerAuth }: ModeIndicatorProps) {
  const brokerTone =
    brokerAuth?.state === "connected"
      ? "live"
      : brokerAuth?.state === "disconnected"
        ? "negative"
        : "neutral";
  const backendConnected = backendMode === "live";
  const modeDetail =
    mode === "LIVE"
      ? "Orders are pointed at the live environment."
      : "Frontend is configured for simulated behavior.";

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
        <StatusBadge label={backendConnected ? "Backend Connected" : "Demo Mode"} tone={backendConnected ? "live" : "warning"} />
        {brokerAuth ? (
          <StatusBadge label={brokerAuth.label} tone={brokerTone} />
        ) : null}
      </div>
    </div>
  );
}
