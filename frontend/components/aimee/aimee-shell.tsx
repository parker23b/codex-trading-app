"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";

import { AimeeConversation } from "@/components/aimee/aimee-conversation";
import { buildSnapshotSignature, loadSnapshot } from "@/components/aimee/data";
import { AimeeDrawerHeader } from "@/components/aimee/aimee-drawer-header";
import { AimeeLauncher } from "@/components/aimee/aimee-launcher";
import { AimeeOverview } from "@/components/aimee/aimee-overview";
import type { AimeeSnapshot, ChatMessage } from "@/components/aimee/types";
import {
  buildRecentChanges,
  buildSystemSummary,
  buildWarningItems,
  buildWhatMatters,
  joinClasses,
  routeContextFromPath,
  SUGGESTED_QUESTIONS,
} from "@/components/aimee/utils";
import { askOperationalQuestion } from "@/lib/api";
import { formatPercent } from "@/lib/format";

const EMPTY_SNAPSHOT: AimeeSnapshot = {
  review: null,
  history: [],
  controlPlane: null,
  coverage: null,
  telemetry: null,
  events: [],
  strategies: [],
  updatedAt: null,
};

export function AimeeShell() {
  const pathname = usePathname();
  const context = routeContextFromPath(pathname);
  const [isOpen, setIsOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<AimeeSnapshot>(EMPTY_SNAPSHOT);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isOverviewExpanded, setIsOverviewExpanded] = useState(true);
  const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false);
  const [hasAttentionPulse, setHasAttentionPulse] = useState(false);
  const lastSignatureRef = useRef<string | null>(null);
  const panelScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async (initial = false) => {
      if (initial) {
        setIsLoading(true);
      }

      try {
        const nextSnapshot = await loadSnapshot();
        if (cancelled) {
          return;
        }

        setSnapshot(nextSnapshot);
        setLoadingError(null);

        const nextSignature = buildSnapshotSignature(nextSnapshot);
        if (
          lastSignatureRef.current &&
          lastSignatureRef.current !== nextSignature &&
          !isOpen
        ) {
          setHasAttentionPulse(true);
        }
        lastSignatureRef.current = nextSignature;
      } catch (error) {
        if (!cancelled) {
          setLoadingError(
            error instanceof Error
              ? error.message
              : "Failed to load AIMEE context.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void refresh(true);
    const intervalId = window.setInterval(() => {
      void refresh(false);
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setHasAttentionPulse(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const { body, documentElement } = document;
    const previousBodyOverflow = body.style.overflow;
    const previousHtmlOverflow = documentElement.style.overflow;

    body.style.overflow = "hidden";
    documentElement.style.overflow = "hidden";

    return () => {
      body.style.overflow = previousBodyOverflow;
      documentElement.style.overflow = previousHtmlOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    const container = panelScrollRef.current;
    if (!container || hasAutoCollapsed || !isOverviewExpanded) {
      return;
    }

    if (
      container.scrollHeight > container.clientHeight + 24 &&
      messages.length >= 2
    ) {
      setIsOverviewExpanded(false);
      setHasAutoCollapsed(true);
    }
  }, [hasAutoCollapsed, isOverviewExpanded, messages]);

  useEffect(() => {
    const container = panelScrollRef.current;
    if (!container) {
      return;
    }

    container.scrollTo({
      top: container.scrollHeight,
      behavior: messages.length > 2 ? "smooth" : "auto",
    });
  }, [messages]);

  const systemSummary = useMemo(
    () => buildSystemSummary(snapshot, context),
    [context, snapshot],
  );
  const whatMatters = useMemo(
    () => buildWhatMatters(snapshot, context),
    [context, snapshot],
  );
  const warningItems = useMemo(() => buildWarningItems(snapshot), [snapshot]);
  const recentChanges = useMemo(() => buildRecentChanges(snapshot), [snapshot]);
  const suggestedQuestions = SUGGESTED_QUESTIONS[context];

  const attentionCount = warningItems.length;
  const compactMetric =
    context === "operate"
      ? snapshot.review
        ? `${formatPercent(snapshot.review.facts.open_risk_percent)} risk`
        : "Risk n/a"
      : context === "control-plane"
        ? `${snapshot.controlPlane?.misaligned_count ?? 0} mismatches`
        : `${attentionCount} warnings`;

  const submitQuestion = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    const timestamp = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: `${timestamp}-user`,
      role: "user",
      createdAt: timestamp,
      question: trimmed,
    };
    const assistantMessage: ChatMessage = {
      id: `${timestamp}-assistant`,
      role: "assistant",
      createdAt: timestamp,
      question: trimmed,
      status: "loading",
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setInputValue("");
    setIsOpen(true);

    try {
      const response = await askOperationalQuestion({ question: trimmed });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                status: "ready",
                response,
              }
            : message,
        ),
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                status: "error",
                error:
                  error instanceof Error
                    ? error.message
                    : "AIMEE could not answer that question.",
              }
            : message,
        ),
      );
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitQuestion(inputValue);
  };

  return (
    <>
      <div
        className={joinClasses(
          "pointer-events-none fixed inset-0 z-40",
          isOpen ? "opacity-100" : "opacity-0",
        )}
        aria-hidden={!isOpen}>
        <button
          type="button"
          className={joinClasses(
            "absolute inset-0 bg-[rgba(6,18,28,0.16)] backdrop-blur-[4px] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),inset_0_0_120px_rgba(6,18,28,0.1)] transition-opacity duration-200 max-[920px]:bg-[rgba(6,18,28,0.28)] max-[920px]:backdrop-blur-[6px]",
            isOpen ? "pointer-events-auto opacity-100" : "opacity-0",
          )}
          onClick={() => setIsOpen(false)}
          tabIndex={isOpen ? 0 : -1}
          aria-label="Close A.I.M.E.E panel"
        />
        <aside
          className={joinClasses(
            "pointer-events-auto absolute right-0 top-0 flex h-full w-full max-w-[620px] flex-col overflow-x-hidden border-l border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_96%,transparent)] shadow-[var(--shadow-raised)] backdrop-blur-[16px] transition-transform duration-200 ease-out max-[920px]:top-auto max-[920px]:h-[86vh] max-[920px]:rounded-t-[28px] max-[920px]:border-l-0 max-[920px]:border-t",
            isOpen
              ? "translate-x-0 max-[920px]:translate-y-0"
              : "translate-x-full max-[920px]:translate-y-full",
          )}
          aria-label="A.I.M.E.E operator assistant"
          onWheel={(event) => event.stopPropagation()}
          onTouchMove={(event) => event.stopPropagation()}>
          <AimeeDrawerHeader
            context={context}
            onClose={() => setIsOpen(false)}
          />

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-5 pb-5">
            <div
              ref={panelScrollRef}
              className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1">
              <div className="flex min-h-full flex-col gap-4 pt-4">
                <AimeeOverview
                  isExpanded={isOverviewExpanded}
                  onToggle={() => setIsOverviewExpanded((value) => !value)}
                  systemSummary={systemSummary}
                  compactMetric={compactMetric}
                  attentionCount={attentionCount}
                  updatedAt={snapshot.updatedAt}
                  whatMatters={whatMatters}
                  warningItems={warningItems}
                  recentChanges={recentChanges}
                />
                <AimeeConversation
                  isLoading={isLoading}
                  loadingError={loadingError}
                  messages={messages}
                  suggestedQuestions={suggestedQuestions}
                  onSubmitQuestion={submitQuestion}
                  inputValue={inputValue}
                  onInputChange={setInputValue}
                  onSubmit={handleSubmit}
                />
              </div>
            </div>
          </div>
        </aside>
      </div>

      <AimeeLauncher
        tone={systemSummary.tone}
        attentionCount={attentionCount}
        hasAttentionPulse={hasAttentionPulse}
        onOpen={() => setIsOpen(true)}
      />
    </>
  );
}
