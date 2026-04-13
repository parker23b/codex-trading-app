import type { FormEvent } from "react";

import type { ChatMessage } from "@/components/aimee/types";
import { formatDateTime, formatMetricValue, joinClasses, reviewResponseSummary, toneClasses, toneFromWarningSeverity } from "@/components/aimee/utils";

type AimeeConversationProps = {
  isLoading: boolean;
  loadingError: string | null;
  messages: ChatMessage[];
  suggestedQuestions: string[];
  onSubmitQuestion: (question: string) => Promise<void>;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
};

export function AimeeConversation({
  isLoading,
  loadingError,
  messages,
  suggestedQuestions,
  onSubmitQuestion,
  inputValue,
  onInputChange,
  onSubmit,
}: AimeeConversationProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-[0.82rem] font-semibold uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Questions</h3>
        </div>
      </div>

      <div className="flex flex-col gap-3 pb-1">
        {isLoading ? (
          <div className="rounded-[18px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] px-4 py-3 text-[0.84rem] text-[color:var(--text-secondary)] shadow-[var(--shadow-soft)]">
            AIMEE is refreshing system context.
          </div>
        ) : null}
        {loadingError ? (
          <div className="rounded-[18px] border border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))] bg-[color:var(--negative-soft)] px-4 py-3 text-[0.84rem] text-[color:var(--negative)] shadow-[var(--shadow-soft)]">
            {loadingError}
          </div>
        ) : null}

        {messages.length === 0 ? (
          <div className="rounded-[20px] border border-dashed border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-4 py-4">
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((question) => (
                <button
                  key={`empty-${question}`}
                  type="button"
                  className="rounded-[10px] border border-[color:var(--border)] bg-[color:var(--bg-surface)] px-3 py-2 text-left text-[0.76rem] text-[color:var(--text-secondary)] transition-colors duration-150 hover:bg-[color:var(--bg-muted)] hover:text-[color:var(--text-primary)]"
                  onClick={() => void onSubmitQuestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) =>
            message.role === "user" ? (
              <article key={message.id} className="ml-auto max-w-[88%] rounded-[18px] border border-[color:color-mix(in_srgb,var(--accent)_28%,var(--border))] bg-[color:var(--accent-soft)] px-4 py-3 text-[0.84rem] shadow-[var(--shadow-soft)]">
                <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Operator</div>
                <div className="mt-1 font-medium text-[color:var(--text-primary)]">{message.question}</div>
              </article>
            ) : (
              <article key={message.id} className="max-w-[96%] rounded-[20px] border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface)] px-4 py-4 shadow-[var(--shadow-panel)]">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">AIMEE</div>
                  <div className="text-[0.72rem] text-[color:var(--text-tertiary)]">{message.status === "loading" ? "Thinking" : formatDateTime(message.createdAt)}</div>
                </div>
                {message.status === "loading" ? (
                  <div className="mt-2 text-[0.84rem] text-[color:var(--text-secondary)]">Interpreting current system state for that question.</div>
                ) : message.status === "error" ? (
                  <div className="mt-2 rounded-[14px] border border-[color:color-mix(in_srgb,var(--negative)_40%,var(--border))] bg-[color:var(--negative-soft)] px-3 py-3 text-[0.82rem] text-[color:var(--negative)]">
                    {message.error ?? "AIMEE could not answer that question."}
                  </div>
                ) : message.response ? (
                  <div className="mt-3 grid gap-3">
                    <div>
                      <div className="text-[0.72rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">Answer</div>
                      <p className="mt-1 text-[0.86rem] text-[color:var(--text-primary)]">{reviewResponseSummary(message.response)}</p>
                    </div>

                    {message.response.derived_observations.length ? (
                      <div className="grid gap-2">
                        {message.response.derived_observations.slice(0, 3).map((observation) => (
                          <div key={observation.code} className="rounded-[14px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-[0.82rem] font-semibold">{observation.label}</div>
                              <span className={joinClasses("rounded-full border px-2 py-[5px] text-[0.64rem] uppercase tracking-[0.08em]", toneClasses(toneFromWarningSeverity(observation.severity)))}>
                                {observation.severity}
                              </span>
                            </div>
                            <p className="mt-1 text-[0.76rem] text-[color:var(--text-secondary)]">{observation.detail}</p>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {message.response.supporting_metrics.length ? (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {message.response.supporting_metrics.slice(0, 4).map((metric) => (
                          <div key={metric.key} className="rounded-[14px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-2">
                            <div className="text-[0.68rem] uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">{metric.label}</div>
                            <div className="mt-1 text-[0.84rem] font-semibold">
                              {typeof metric.value === "number"
                                ? metric.unit === "pct"
                                  ? formatMetricValue(metric.value, "percent")
                                  : formatMetricValue(metric.value, "count")
                                : String(metric.value ?? "n/a")}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {message.response.warnings.length ? (
                      <div className="flex flex-wrap gap-2">
                        {message.response.warnings.map((warning) => (
                          <span key={warning.code} className={joinClasses("rounded-full border px-3 py-[7px] text-[0.7rem]", toneClasses(toneFromWarningSeverity(warning.severity)))}>
                            {warning.message}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ),
          )
        )}
      </div>

      <form onSubmit={onSubmit} className="mt-3 flex-none rounded-[20px] border border-[color:var(--glass-stroke)] bg-[color:color-mix(in_srgb,var(--bg-shell)_96%,transparent)] p-3 shadow-[var(--shadow-panel)] backdrop-blur-[16px]">
        <div className="flex items-end gap-2">
          <label className="flex-1">
            <span className="sr-only">Ask AIMEE a system question</span>
            <textarea
              value={inputValue}
              onChange={(event) => onInputChange(event.target.value)}
              rows={2}
              placeholder="Ask AIMEE to explain the current system state..."
              className="min-h-[72px] w-full resize-none rounded-[16px] border border-[color:var(--glass-stroke)] bg-[color:var(--bg-surface-muted)] px-3 py-3 text-[0.84rem] text-[color:var(--text-primary)] outline-none transition-colors placeholder:text-[color:var(--text-tertiary)] focus:border-[color:color-mix(in_srgb,var(--accent)_36%,var(--glass-stroke))]"
            />
          </label>
          <button
            type="submit"
            className="inline-flex h-11 shrink-0 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--accent)_32%,var(--border))] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--accent-soft)_70%,white_18%),color-mix(in_srgb,var(--accent-soft)_94%,transparent))] px-4 text-[0.82rem] font-semibold text-[color:var(--text-primary)] shadow-[var(--shadow-soft)] transition-transform duration-150 hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!inputValue.trim()}
          >
            Ask
          </button>
        </div>
      </form>
    </section>
  );
}
