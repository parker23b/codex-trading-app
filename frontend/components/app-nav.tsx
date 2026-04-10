"use client";

import { useEffect, useState } from "react";
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

const links = [
  { href: "/", label: "Operate" },
  { href: "/control-plane", label: "Control Plane" },
  { href: "/coverage", label: "Coverage" },
  { href: "/markets", label: "Investigate" },
  { href: "/events", label: "Events" },
  { href: "/reviewer", label: "AI Reviewer" },
  { href: "/strategies", label: "Strategies" },
];

function indicatorTone(value: "positive" | "warning" | "negative" | "neutral") {
  return `top-nav__indicator top-nav__indicator--${value}`;
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
    <div className="top-nav">
      <div className="top-nav__brand">
        <div className="top-nav__mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className="top-nav__product">Investmate Ops</div>
          <div className="top-nav__product-subtitle">Autonomous system operator console</div>
        </div>
      </div>

      <nav className="top-nav__links" aria-label="Primary navigation">
        {links.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link key={link.href} href={link.href} className={`top-nav__link${isActive ? " is-active" : ""}`}>
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div className="top-nav__status">
        <div className={indicatorTone(healthTone)}>
          <span className="top-nav__indicator-label">Health</span>
          <strong>{controlPlane.misaligned_count > 0 ? `${controlPlane.misaligned_count} mismatches` : "Nominal"}</strong>
        </div>
        <div
          className={indicatorTone(
            broker.state === "connected" ? "positive" : broker.state === "disconnected" ? "warning" : "negative",
          )}
        >
          <span className="top-nav__indicator-label">Broker</span>
          <strong>{broker.label}</strong>
        </div>
        <div className={indicatorTone(streamHealth.connected ? "positive" : streamHealth.enabled ? "negative" : "neutral")}>
          <span className="top-nav__indicator-label">Stream</span>
          <strong>{streamHealth.connected ? "Connected" : streamHealth.enabled ? "Interrupted" : "Disabled"}</strong>
        </div>
        <div className="top-nav__environment">
          <span className="top-nav__indicator-label">Env</span>
          <strong>Demo</strong>
        </div>
      </div>
    </div>
  );
}
