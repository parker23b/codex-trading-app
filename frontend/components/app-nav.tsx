"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  UNAVAILABLE_BROKER_AUTH_STATUS,
  UNAVAILABLE_BROKER_ENVIRONMENT_STATUS,
  UNAVAILABLE_CONTROL_PLANE_SUMMARY,
  UNAVAILABLE_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getBrokerEnvironmentStatus,
  getControlPlaneSummary,
  getStreamHealth,
} from "@/lib/api";
import type { BrokerEnvironmentStatus } from "@/lib/types";
import { ThemeToggle } from "@/components/theme-toggle";

const links = [
  { href: "/", label: "Overview" },
  { href: "/live", label: "Live View" },
  { href: "/risk", label: "Risk" },
  { href: "/control-plane", label: "Control Plane" },
  { href: "/coverage", label: "Coverage" },
  { href: "/markets", label: "Investigate" },
  { href: "/events", label: "Events" },
  { href: "/strategies", label: "Strategies" },
];

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function indicatorTone(value: "positive" | "warning" | "negative" | "neutral") {
  const borderColor =
    value === "positive"
      ? "color-mix(in srgb, var(--positive) 32%, var(--border))"
      : value === "warning"
        ? "color-mix(in srgb, var(--warning) 36%, var(--border))"
        : value === "negative"
          ? "color-mix(in srgb, var(--negative) 38%, var(--border))"
          : "var(--glass-stroke)";

  return {
    className:
      "flex min-w-0 min-w-[82px] flex-col gap-[2px] rounded-[12px] border bg-[image:var(--glass-surface-soft)] px-2 py-[7px] shadow-[var(--shadow-soft)]",
    style: { borderColor } satisfies CSSProperties,
  };
}

function activeNavLinkStyle(isActive: boolean): CSSProperties | undefined {
  if (!isActive) {
    return undefined;
  }

  return {
    borderColor: "color-mix(in srgb, var(--accent) 34%, transparent)",
    backgroundColor: "color-mix(in srgb, var(--accent-soft) 72%, transparent)",
  };
}

export function AppNav() {
  const pathname = usePathname();
  const [broker, setBroker] = useState(UNAVAILABLE_BROKER_AUTH_STATUS);
  const [brokerEnvironment, setBrokerEnvironment] = useState<BrokerEnvironmentStatus>(
    UNAVAILABLE_BROKER_ENVIRONMENT_STATUS,
  );
  const [streamHealth, setStreamHealth] = useState(UNAVAILABLE_STREAM_HEALTH_STATUS);
  const [controlPlane, setControlPlane] = useState(UNAVAILABLE_CONTROL_PLANE_SUMMARY);
  const [brokerEnvironmentLoadError, setBrokerEnvironmentLoadError] = useState<string | null>(
    "Broker environment has not loaded yet.",
  );
  const [streamLoadError, setStreamLoadError] = useState<string | null>("Stream health has not loaded yet.");
  const [controlPlaneLoadError, setControlPlaneLoadError] = useState<string | null>("Control-plane health has not loaded yet.");

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      const [nextBroker, nextBrokerEnvironment, nextStreamHealth, nextControlPlane] = await Promise.allSettled([
        getBrokerAuthStatus(),
        getBrokerEnvironmentStatus(),
        getStreamHealth(),
        getControlPlaneSummary(),
      ]);

      if (cancelled) {
        return;
      }

      if (nextBroker.status === "fulfilled") {
        setBroker(nextBroker.value);
      } else {
        setBroker({
          ...UNAVAILABLE_BROKER_AUTH_STATUS,
          detail: errorMessage(nextBroker.reason, "Broker telemetry could not be loaded."),
        });
      }

      if (nextBrokerEnvironment.status === "fulfilled") {
        setBrokerEnvironment(nextBrokerEnvironment.value);
        setBrokerEnvironmentLoadError(null);
      } else {
        setBrokerEnvironment({
          ...UNAVAILABLE_BROKER_ENVIRONMENT_STATUS,
          blocking_reason: errorMessage(nextBrokerEnvironment.reason, "Broker environment could not be loaded."),
        });
        setBrokerEnvironmentLoadError(
          errorMessage(nextBrokerEnvironment.reason, "Broker environment could not be loaded."),
        );
      }

      if (nextStreamHealth.status === "fulfilled") {
        setStreamHealth(nextStreamHealth.value);
        setStreamLoadError(null);
      } else {
        setStreamHealth(UNAVAILABLE_STREAM_HEALTH_STATUS);
        setStreamLoadError(errorMessage(nextStreamHealth.reason, "Stream health could not be loaded."));
      }

      if (nextControlPlane.status === "fulfilled") {
        setControlPlane(nextControlPlane.value);
        setControlPlaneLoadError(null);
      } else {
        setControlPlane(UNAVAILABLE_CONTROL_PLANE_SUMMARY);
        setControlPlaneLoadError(errorMessage(nextControlPlane.reason, "Control-plane health could not be loaded."));
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const healthLabel = controlPlaneLoadError
    ? "Unknown"
    : controlPlane.misaligned_count > 0
      ? `${controlPlane.misaligned_count} mismatches`
      : !controlPlane.effective_autonomous_control_enabled
        ? "Paused"
        : "Nominal";
  const healthDetail = controlPlaneLoadError
    ? `Health unavailable: ${controlPlaneLoadError}`
    : "Control-plane health loaded from backend summary.";
  const streamLabel = streamLoadError
    ? "Unknown"
    : streamHealth.connected
      ? "Connected"
      : streamHealth.enabled
        ? "Interrupted"
        : "Disabled";
  const streamDetail = streamLoadError
    ? `Stream health unavailable: ${streamLoadError}`
    : streamHealth.last_status ?? "Stream health loaded from backend.";
  const healthTone = controlPlaneLoadError
    ? "negative"
    : !controlPlane.effective_autonomous_control_enabled || controlPlane.misaligned_count > 0
    ? "warning"
    : broker.state === "unavailable" || !streamHealth.connected
      ? "negative"
      : "positive";
  const brokerEnvironmentLabel = brokerEnvironmentLoadError
    ? "ENVIRONMENT UNKNOWN"
    : !brokerEnvironment.configuration_valid
      ? "CONFIGURATION INVALID"
      : `${brokerEnvironment.environment} \u00b7 ${brokerEnvironment.dealing_enabled ? "DEALING ENABLED" : "DEALING DISABLED"}`;
  const brokerEnvironmentDetail = brokerEnvironmentLoadError
    ? `Broker environment unavailable: ${brokerEnvironmentLoadError}`
    : !brokerEnvironment.configuration_valid
      ? brokerEnvironment.blocking_reason ?? "Broker environment configuration is invalid."
      : [
          `${brokerEnvironment.provider} ${brokerEnvironment.endpoint_classification}`,
          brokerEnvironment.streaming_enabled ? "streaming enabled" : "streaming disabled",
          brokerEnvironment.live_trading_acknowledged ? "live dealing acknowledged" : "live dealing not acknowledged",
        ].join(" \u00b7 ");
  const brokerEnvironmentTone = brokerEnvironmentLoadError || !brokerEnvironment.configuration_valid
    ? "negative"
    : brokerEnvironment.environment === "LIVE" && brokerEnvironment.dealing_enabled
      ? "negative"
      : brokerEnvironment.environment === "LIVE" || brokerEnvironment.dealing_enabled
        ? "warning"
        : "positive";

  return (
    <div className="grid h-full grid-cols-[240px_minmax(0,1fr)_auto] items-center gap-3 px-[14px] max-[720px]:grid-cols-1 max-[720px]:items-start max-[720px]:gap-2 max-[720px]:px-3 max-[720px]:py-3">
      <div className="flex items-center gap-[14px]">
        <div
          className="grid h-[38px] w-[38px] grid-cols-3 gap-1 rounded-[12px] bg-[image:radial-gradient(circle_at_top_right,color-mix(in_srgb,var(--primary)_88%,transparent),transparent_58%),radial-gradient(circle_at_bottom_left,color-mix(in_srgb,var(--secondary)_82%,transparent),transparent_60%),linear-gradient(180deg,#16304a,#0c131a)] p-[7px] shadow-[inset_0_1px_0_rgba(255,255,255,0.18)]"
          aria-hidden="true"
        >
          <span className="rounded-full bg-[rgba(255,255,255,0.82)]" />
          <span className="rounded-full bg-[rgba(255,255,255,0.82)]" />
          <span className="rounded-full bg-[rgba(255,255,255,0.82)]" />
        </div>
        <div>
          <div className="text-[0.94rem] font-bold uppercase tracking-[0.04em]">Investmate</div>
          <div className="text-[0.76rem] text-[color:var(--text-tertiary)]">Smart Investing. Made Simple.</div>
        </div>
      </div>

      <nav
        className="flex min-w-0 flex-wrap gap-1 overflow-hidden max-[720px]:order-3 max-[720px]:overflow-x-auto"
        aria-label="Primary navigation"
      >
        {links.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={[
                "cursor-pointer whitespace-nowrap rounded-full border border-transparent bg-transparent px-[10px] py-[7px] text-[0.88rem] text-[color:var(--text-secondary)] transition-[background-color,color,border-color] duration-150 ease-out hover:bg-[color:var(--bg-muted)] hover:text-[color:var(--text-primary)]",
                isActive ? "text-[color:var(--text-primary)]" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={activeNavLinkStyle(isActive)}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex min-w-0 flex-wrap items-center justify-end gap-[6px] max-[720px]:order-2">
        <div className={indicatorTone(healthTone).className} style={indicatorTone(healthTone).style} title={healthDetail}>
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Health</span>
          <strong>{healthLabel}</strong>
        </div>
        <div
          className={
            indicatorTone(
              broker.state === "connected" ? "positive" : broker.state === "disconnected" ? "warning" : "negative",
            ).className
          }
          style={
            indicatorTone(
              broker.state === "connected" ? "positive" : broker.state === "disconnected" ? "warning" : "negative",
            ).style
          }
          title={broker.detail}
        >
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Broker</span>
          <strong>{broker.label}</strong>
        </div>
        <div
          className={indicatorTone(streamLoadError ? "negative" : streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "neutral").className}
          style={indicatorTone(streamLoadError ? "negative" : streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "neutral").style}
          title={streamDetail}
        >
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Stream</span>
          <strong>{streamLabel}</strong>
        </div>
        <div
          className={indicatorTone(brokerEnvironmentTone).className}
          style={indicatorTone(brokerEnvironmentTone).style}
          title={brokerEnvironmentDetail}
        >
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Broker Env</span>
          <strong>{brokerEnvironmentLabel}</strong>
        </div>
        <ThemeToggle variant="nav" />
      </div>
    </div>
  );
}
