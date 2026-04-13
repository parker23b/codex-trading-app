import type {
  AimeeControlPlaneSummary,
  AimeeCoverageSummary,
  AimeeStrategySummary,
  DomainEvent,
  OperationalQuestionReviewResponse,
  OperationalTelemetry,
  OperatorSummaryReview,
  ReviewHistoryItem,
} from "@/lib/types";

export type Tone = "positive" | "warning" | "negative" | "neutral";
export type RouteContext = "operate" | "control-plane" | "coverage" | "events" | "strategies" | "general";

export type AimeeSnapshot = {
  review: OperatorSummaryReview | null;
  history: ReviewHistoryItem[];
  controlPlane: AimeeControlPlaneSummary | null;
  coverage: AimeeCoverageSummary | null;
  telemetry: OperationalTelemetry | null;
  events: DomainEvent[];
  strategies: AimeeStrategySummary[];
  updatedAt: string | null;
};

export type OverviewCard = {
  id: string;
  title: string;
  detail: string;
  meta?: string;
  tone: Tone;
};

export type WarningItem = {
  id: string;
  title: string;
  detail: string;
  tone: Tone;
};

export type ChangeItem = {
  id: string;
  title: string;
  detail: string;
  at?: string | null;
};

export type ChatMessage =
  | {
      id: string;
      role: "user";
      createdAt: string;
      question: string;
    }
  | {
      id: string;
      role: "assistant";
      createdAt: string;
      question: string;
      status: "loading" | "ready" | "error";
      response?: OperationalQuestionReviewResponse | null;
      error?: string | null;
    };
