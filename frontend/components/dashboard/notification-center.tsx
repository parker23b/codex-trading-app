"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { formatDateTime, formatInstrumentLabel, formatPrice } from "@/lib/format";
import { BrokerAuthStatus, Execution, StreamHealthStatus } from "@/lib/types";

type NotificationTone = "positive" | "warning" | "negative" | "neutral";

type NotificationItem = {
  id: string;
  tone: NotificationTone;
  category: string;
  title: string;
  detail: string;
  timestamp: string;
  strategyName?: string;
  instrument?: string;
};

type NotificationCenterProps = {
  executions: Execution[];
  brokerAuth: BrokerAuthStatus;
  streamHealth: StreamHealthStatus;
};

const DISMISSED_STORAGE_KEY = "trading-platform-dismissed-notifications";

function buildExecutionDetail(execution: Execution) {
  const size = execution.filled_size ?? execution.requested_size;
  const price = execution.average_fill_price ?? execution.requested_price;
  const parts = [
    execution.strategy_name,
    formatInstrumentLabel(execution.instrument),
    typeof size === "number" ? `size ${size}` : null,
    typeof price === "number" ? `px ${formatPrice(price, execution.instrument)}` : null,
  ].filter(Boolean);

  if (execution.error_message) {
    parts.push(execution.error_message);
  } else if (execution.reason) {
    parts.push(execution.reason);
  }

  return parts.join(" • ");
}

function buildExecutionNotification(execution: Execution): NotificationItem {
  const timestamp = execution.last_transition_at;

  switch (execution.status) {
    case "FAILED":
      return {
        id: `execution-${execution.id}`,
        tone: "negative",
        category: execution.phase === "ENTRY" ? "Entry Error" : "Exit Error",
        title: execution.phase === "ENTRY" ? "Trade entry failed" : "Trade exit failed",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    case "NEEDS_MANUAL_REVIEW":
      return {
        id: `execution-${execution.id}`,
        tone: "warning",
        category: "Manual Review",
        title: execution.phase === "ENTRY" ? "Entry needs manual review" : "Exit needs manual review",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    case "RISK_REJECTED":
      return {
        id: `execution-${execution.id}`,
        tone: "warning",
        category: "Risk Control",
        title: "Trade blocked by risk controls",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    case "POSITION_OPENED":
      return {
        id: `execution-${execution.id}`,
        tone: "positive",
        category: "Trade Entry",
        title: "Position opened",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    case "CLOSE_CONFIRMED":
      return {
        id: `execution-${execution.id}`,
        tone: "neutral",
        category: "Trade Exit",
        title: "Position closed",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    case "ORDER_SUBMITTED":
      return {
        id: `execution-${execution.id}`,
        tone: "neutral",
        category: execution.phase === "ENTRY" ? "Entry Working" : "Exit Working",
        title: execution.phase === "ENTRY" ? "Entry order submitted" : "Exit order submitted",
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
    default:
      return {
        id: `execution-${execution.id}`,
        tone: "neutral",
        category: execution.phase === "ENTRY" ? "Execution Update" : "Close Update",
        title: execution.reason ?? execution.status.replaceAll("_", " "),
        detail: buildExecutionDetail(execution),
        timestamp,
        strategyName: execution.strategy_name,
        instrument: execution.instrument,
      };
  }
}

function buildSystemNotifications(brokerAuth: BrokerAuthStatus, streamHealth: StreamHealthStatus): NotificationItem[] {
  const items: NotificationItem[] = [];
  const now = new Date().toISOString();

  if (brokerAuth.state !== "connected") {
    items.push({
      id: `broker-${brokerAuth.state}-${brokerAuth.detail}`,
      tone: "negative",
      category: "Broker",
      title: brokerAuth.label,
      detail: brokerAuth.detail,
      timestamp: now,
    });
  }

  if (streamHealth.enabled && !streamHealth.connected) {
    items.push({
      id: `stream-disconnected-${streamHealth.last_tick_at ?? "none"}`,
      tone: "warning",
      category: "Price Stream",
      title: "Streaming connection down",
      detail: streamHealth.last_error ?? streamHealth.last_status ?? "Live price updates are not connected.",
      timestamp: streamHealth.last_tick_at ?? now,
    });
  }

  if (streamHealth.enabled && !streamHealth.dependency_ready) {
    items.push({
      id: `stream-dependency-${streamHealth.last_tick_at ?? "none"}`,
      tone: "warning",
      category: "Price Stream",
      title: "Streaming dependency not ready",
      detail: "The live streaming dependency is unavailable, so updates may fall back to polling or stale prices.",
      timestamp: streamHealth.last_tick_at ?? now,
    });
  }

  return items;
}

function NotificationCard({
  notification,
  onDismiss,
}: {
  notification: NotificationItem;
  onDismiss: (id: string) => void;
}) {
  return (
    <article className={`notification-item notification-item--${notification.tone}`}>
      <div className="notification-item__meta">
        <span className="eyebrow">{notification.category}</span>
        <time dateTime={notification.timestamp}>{formatDateTime(notification.timestamp)}</time>
      </div>
      <div className="notification-item__header">
        <strong>{notification.title}</strong>
        <button
          type="button"
          className="notification-dismiss"
          onClick={() => onDismiss(notification.id)}
          aria-label={`Dismiss ${notification.title}`}
        >
          Dismiss
        </button>
      </div>
      {notification.strategyName && notification.instrument ? (
        <div className="notification-item__context">
          {notification.strategyName} • {formatInstrumentLabel(notification.instrument)}
        </div>
      ) : null}
      <p className="notification-item__detail">{notification.detail}</p>
    </article>
  );
}

export function NotificationCenter({ executions, brokerAuth, streamHealth }: NotificationCenterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [dismissedIds, setDismissedIds] = useState<string[]>([]);
  const [toastIds, setToastIds] = useState<string[]>([]);
  const seenIdsRef = useRef<Set<string>>(new Set());
  const toastTimeoutsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(DISMISSED_STORAGE_KEY);
      if (!stored) {
        return;
      }
      const parsed = JSON.parse(stored) as string[];
      setDismissedIds(Array.isArray(parsed) ? parsed : []);
    } catch {
      setDismissedIds([]);
    }
  }, []);

  const notifications = useMemo(
    () =>
      [...buildSystemNotifications(brokerAuth, streamHealth), ...executions.map(buildExecutionNotification)]
        .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime())
        .slice(0, 40),
    [brokerAuth, executions, streamHealth],
  );

  useEffect(() => {
    const seenIds = seenIdsRef.current;
    const nextToastIds: string[] = [];

    notifications.forEach((notification) => {
      if (!seenIds.has(notification.id)) {
        seenIds.add(notification.id);
        if (!dismissedIds.includes(notification.id)) {
          nextToastIds.push(notification.id);
        }
      }
    });

    if (nextToastIds.length > 0) {
      setToastIds((current) => [...nextToastIds, ...current].slice(0, 5));
      nextToastIds.forEach((id) => {
        const existingTimeout = toastTimeoutsRef.current.get(id);
        if (existingTimeout) {
          window.clearTimeout(existingTimeout);
        }
        const timeoutId = window.setTimeout(() => {
          setToastIds((current) => current.filter((toastId) => toastId !== id));
          toastTimeoutsRef.current.delete(id);
        }, 3000);
        toastTimeoutsRef.current.set(id, timeoutId);
      });
    }
  }, [dismissedIds, notifications]);

  useEffect(() => {
    const toastTimeouts = toastTimeoutsRef.current;
    return () => {
      toastTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId));
      toastTimeouts.clear();
    };
  }, []);

  const activeNotifications = notifications.filter((notification) => !dismissedIds.includes(notification.id));
  const dropdownNotifications = activeNotifications.slice().reverse();
  const toasts = toastIds
    .map((id) => activeNotifications.find((notification) => notification.id === id))
    .filter((notification): notification is NotificationItem => Boolean(notification));

  const persistDismissedIds = (nextIds: string[]) => {
    setDismissedIds(nextIds);
    try {
      window.localStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify(nextIds));
    } catch {
      // Ignore storage failures and keep local state updated.
    }
  };

  const handleDismiss = (id: string) => {
    if (!dismissedIds.includes(id)) {
      persistDismissedIds([...dismissedIds, id]);
    }
    const timeoutId = toastTimeoutsRef.current.get(id);
    if (timeoutId) {
      window.clearTimeout(timeoutId);
      toastTimeoutsRef.current.delete(id);
    }
    setToastIds((current) => current.filter((toastId) => toastId !== id));
  };

  const handleDismissAll = () => {
    persistDismissedIds(Array.from(new Set([...dismissedIds, ...activeNotifications.map((notification) => notification.id)])));
    toastTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    toastTimeoutsRef.current.clear();
    setToastIds([]);
  };

  return (
    <>
      <div className="notification-launcher">
        <button type="button" className="notification-fab" onClick={() => setIsOpen((open) => !open)}>
          <span>Notifications</span>
          <span className="notification-fab__count">{activeNotifications.length}</span>
        </button>
        {!isOpen ? (
          <div className="notification-toast-stack" aria-live="polite" aria-atomic="false">
            {toasts.map((notification) => (
              <NotificationCard key={`toast-${notification.id}`} notification={notification} onDismiss={handleDismiss} />
            ))}
          </div>
        ) : null}
      </div>
      {isOpen ? (
        <div className="notification-popup" role="dialog" aria-label="Notification Center">
          <div className="notification-popup__header">
            <div>
              <h2>Notification Center</h2>
              <p className="muted">Live trade and platform alerts with manual dismiss.</p>
            </div>
            <div className="notification-popup__actions">
              {activeNotifications.length > 0 ? (
                <button type="button" className="notification-action" onClick={handleDismissAll}>
                  Dismiss all
                </button>
              ) : null}
              <button type="button" className="notification-action" onClick={() => setIsOpen(false)}>
                Close
              </button>
            </div>
          </div>
          <div className="notification-popup__body">
            {activeNotifications.length === 0 ? (
              <div className="empty-state">No active notifications.</div>
            ) : (
              <div className="notification-center">
                {dropdownNotifications.map((notification) => (
                  <NotificationCard key={notification.id} notification={notification} onDismiss={handleDismiss} />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
