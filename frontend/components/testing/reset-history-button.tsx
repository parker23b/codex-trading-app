"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { resetTestHistory } from "@/lib/api";

export function ResetHistoryButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleReset = () => {
    const confirmed = window.confirm(
      "Clear persisted test history? This removes trades, executions, reconciliation events, domain events, generated reviews, closed positions, and stopped runtimes.",
    );
    if (!confirmed) {
      return;
    }

    startTransition(async () => {
      try {
        const result = await resetTestHistory();
        const deletedCount = Object.values(result.summary).reduce((sum, value) => sum + value, 0);
        setStatusMessage(deletedCount > 0 ? `Cleared ${deletedCount} persisted test records.` : "No persisted test history was available to clear.");
        router.refresh();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Reset failed";
        setStatusMessage(message);
      }
    });
  };

  return (
    <div className="events-filters__actions">
      <button type="button" className="button secondary" disabled={pending} onClick={handleReset}>
        {pending ? "Clearing..." : "Clear Test History"}
      </button>
      {statusMessage ? <div className="status-note status-note--inline">{statusMessage}</div> : null}
    </div>
  );
}
