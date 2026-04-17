"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  EMPTY_BROKER_AUTH_STATUS,
  EMPTY_CONTROL_PLANE_SUMMARY,
  EMPTY_STREAM_HEALTH_STATUS,
  getBrokerAuthStatus,
  getControlPlaneSummary,
  getStreamHealth,
} from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

const links = [
  { href: "/", label: "Operate" },
  { href: "/risk", label: "Risk" },
  { href: "/control-plane", label: "Control Plane" },
  { href: "/coverage", label: "Coverage" },
  { href: "/markets", label: "Investigate" },
  { href: "/events", label: "Events" },
  { href: "/strategies", label: "Strategies" },
];

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
  const [broker, setBroker] = useState(EMPTY_BROKER_AUTH_STATUS);
  const [streamHealth, setStreamHealth] = useState(EMPTY_STREAM_HEALTH_STATUS);
  const [controlPlane, setControlPlane] = useState(EMPTY_CONTROL_PLANE_SUMMARY);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [nextBroker, nextStreamHealth, nextControlPlane] = await Promise.all([
          getBrokerAuthStatus(),
          getStreamHealth(),
          getControlPlaneSummary(),
        ]);

        if (cancelled) {
          return;
        }

        setBroker(nextBroker);
        setStreamHealth(nextStreamHealth);
        setControlPlane(nextControlPlane);
      } catch {
        // Keep last known header status if refresh fails.
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const healthTone = !controlPlane.effective_autonomous_control_enabled || controlPlane.misaligned_count > 0
    ? "warning"
    : broker.state === "unavailable" || !streamHealth.connected
      ? "negative"
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
        <div className={indicatorTone(healthTone).className} style={indicatorTone(healthTone).style}>
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Health</span>
          <strong>{controlPlane.misaligned_count > 0 ? `${controlPlane.misaligned_count} mismatches` : "Nominal"}</strong>
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
        >
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Broker</span>
          <strong>{broker.label}</strong>
        </div>
        <div
          className={indicatorTone(streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "neutral").className}
          style={indicatorTone(streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "neutral").style}
        >
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Stream</span>
          <strong>{streamHealth.connected ? "Connected" : streamHealth.enabled ? "Interrupted" : "Disabled"}</strong>
        </div>
        <div className="flex min-w-0 min-w-[82px] flex-col gap-[2px] rounded-[12px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] px-2 py-[7px] shadow-[var(--shadow-soft)]">
          <span className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Env</span>
          <strong>Demo</strong>
        </div>
        <ThemeToggle variant="nav" />
      </div>
    </div>
  );
}
