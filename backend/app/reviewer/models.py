from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReviewType = Literal[
    "operator_summary",
    "daily_review",
    "strategy_review",
    "runtime_health_review",
    "trade_postmortem",
    "operational_question",
]

Severity = Literal["info", "warning", "critical"]
Trend = Literal["up", "down", "flat", "unknown"]


class ReviewSourceCoverage(BaseModel):
    trades_available: bool = True
    positions_available: bool = True
    executions_available: bool = True
    runtimes_available: bool = True
    reconciliation_available: bool = True
    broker_summary_available: bool = False
    stream_health_available: bool = True
    coverage_notes: list[str] = Field(default_factory=list)


class ReviewMetadata(BaseModel):
    review_id: int | None = None
    review_type: ReviewType
    generated_at: datetime
    as_of: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    requested_date: date | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    source_coverage: ReviewSourceCoverage
    generation_mode: Literal["deterministic_only", "deterministic_plus_llm"] = "deterministic_only"


class SupportingMetric(BaseModel):
    key: str
    label: str
    value: float | int | str | None
    unit: str | None = None
    baseline_value: float | int | str | None = None
    delta_value: float | int | str | None = None
    trend: Trend = "unknown"
    description: str | None = None


class ObservationMetric(BaseModel):
    key: str
    label: str
    value: float | int | str | None
    unit: str | None = None
    baseline_value: float | int | str | None = None
    delta_value: float | int | str | None = None


class ReviewObservation(BaseModel):
    code: str
    severity: Severity = "info"
    label: str
    detail: str
    confidence: float = 0.5
    rank: int = 0
    time_scope: str
    supporting_metrics: list[ObservationMetric] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None


class PossibleContributor(BaseModel):
    code: str
    label: str
    detail: str
    confidence: float = 0.5
    time_scope: str
    related_observation_codes: list[str] = Field(default_factory=list)
    supporting_metrics: list[ObservationMetric] = Field(default_factory=list)


class ReviewWarning(BaseModel):
    code: str
    severity: Severity = "warning"
    message: str


class AIReviewSummary(BaseModel):
    summary: str
    notable_points: list[str] = Field(default_factory=list)
    operator_checks: list[str] = Field(default_factory=list)


class AIReviewProvenance(BaseModel):
    llm_attempted: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    prompt_version: str = "ai-reviewer-v1"
    generated_at: datetime | None = None
    prompt_facts: dict[str, Any] = Field(default_factory=dict)
    raw_response: str | None = None


class ExposureFact(BaseModel):
    strategy_name: str
    instrument: str
    direction: str
    risk_percent: float
    unrealized_pnl: float | None = None
    notional_estimate: float | None = None
    share_of_open_risk_percent: float | None = None


class StrategyHealthFact(BaseModel):
    strategy_name: str
    status: str
    active_runtime_count: int
    open_position_count: int
    trade_count_24h: int
    pnl_24h: float
    win_rate_24h: float | None = None
    stale_runtime_count: int = 0


class OperatorSummaryFacts(BaseModel):
    account_value: float | None = None
    account_value_change_percent: float | None = None
    daily_pnl: float
    daily_pnl_percent: float | None = None
    open_risk_percent: float
    open_positions_count: int
    active_runtimes: int
    main_open_risk: ExposureFact | None = None
    largest_risk_share_percent: float = 0.0
    top_risk_exposures: list[ExposureFact] = Field(default_factory=list)
    strategy_health: list[StrategyHealthFact] = Field(default_factory=list)
    risk_rejections_24h: int = 0
    execution_failures_24h: int = 0
    reconciliation_issues_24h: int = 0
    stale_runtimes: int = 0
    stream_connected: bool | None = None
    stream_last_tick_at: datetime | None = None
    baseline_open_risk_percent: float | None = None
    baseline_largest_risk_share_percent: float | None = None
    baseline_trade_count_24h: float | None = None
    baseline_win_rate_24h: float | None = None


class DailyReviewFacts(BaseModel):
    review_date: date
    strategies_ran: list[str] = Field(default_factory=list)
    active_instruments: list[str] = Field(default_factory=list)
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    risk_rejections: int = 0
    risk_rejections_by_rule: dict[str, int] = Field(default_factory=dict)
    execution_failures: int = 0
    runtime_health_issues: int = 0
    reconciliation_issues: int = 0
    baseline_trade_count: float | None = None
    baseline_realised_pnl: float | None = None
    baseline_win_rate: float | None = None


class StrategyReviewFacts(BaseModel):
    strategy_name: str
    period_days: int
    status: str
    active_runtime_count: int
    active_instruments: list[str] = Field(default_factory=list)
    open_position_count: int
    trade_count: int
    win_count: int
    loss_count: int
    realised_pnl: float
    unrealised_pnl: float
    win_rate: float | None = None
    baseline_trade_count: float | None = None
    baseline_win_rate: float | None = None
    stale_price_events: int = 0
    risk_rejections: int = 0
    execution_failures: int = 0


class RuntimeIssueFact(BaseModel):
    strategy_name: str
    instrument: str
    issue_type: str
    detail: str
    last_seen_at: datetime | None = None


class RuntimeHealthFacts(BaseModel):
    active_runtime_count: int
    stale_price_count: int
    heartbeat_issue_count: int
    disconnected_stream: bool
    polling_fallback_suspected: bool
    reconciliation_issue_count: int
    execution_failure_count: int
    risk_rejection_count: int
    issues: list[RuntimeIssueFact] = Field(default_factory=list)


class TradeClusterPattern(BaseModel):
    pattern: str
    count: int
    share_percent: float
    detail: str


class TradePostMortemFacts(BaseModel):
    trade_id: int
    strategy_name: str
    instrument: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    holding_minutes: float
    pnl: float
    outcome: str
    recent_loss_count_same_strategy: int
    recent_loss_count_same_instrument: int
    matched_normal_trade_size: bool = True
    execution_warning_count: int = 0
    clustered_patterns: list[TradeClusterPattern] = Field(default_factory=list)


class OperationalQuestionFacts(BaseModel):
    question: str
    answer_type: str
    routed_review_type: ReviewType
    routed_scope: dict[str, Any] = Field(default_factory=dict)
    supporting_review: dict[str, Any] = Field(default_factory=dict)


class ReviewRecordSummary(BaseModel):
    review_id: int
    review_type: ReviewType
    generated_at: datetime
    scope: dict[str, Any] = Field(default_factory=dict)
    generation_mode: Literal["deterministic_only", "deterministic_plus_llm"] = "deterministic_only"
    provider: str | None = None
    model: str | None = None


class BaseReviewResponse(BaseModel):
    metadata: ReviewMetadata
    facts: Any
    derived_observations: list[ReviewObservation] = Field(default_factory=list)
    possible_contributors: list[PossibleContributor] = Field(default_factory=list)
    warnings: list[ReviewWarning] = Field(default_factory=list)
    supporting_metrics: list[SupportingMetric] = Field(default_factory=list)
    ai_summary: AIReviewSummary | None = None
    provenance: AIReviewProvenance | None = None


class OperatorSummaryReview(BaseReviewResponse):
    facts: OperatorSummaryFacts


class DailyReviewResponse(BaseReviewResponse):
    facts: DailyReviewFacts


class StrategyReviewResponse(BaseReviewResponse):
    facts: StrategyReviewFacts


class RuntimeHealthReviewResponse(BaseReviewResponse):
    facts: RuntimeHealthFacts


class TradePostMortemReviewResponse(BaseReviewResponse):
    facts: TradePostMortemFacts


class OperationalQuestionReviewResponse(BaseReviewResponse):
    facts: OperationalQuestionFacts


class PersistedReviewRecord(BaseModel):
    review_id: int
    review_type: ReviewType
    scope: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    facts: dict[str, Any] = Field(default_factory=dict)
    derived_observations: list[dict[str, Any]] = Field(default_factory=list)
    possible_contributors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    supporting_metrics: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary: dict[str, Any] | None = None
    prompt_version: str = "ai-reviewer-v1"
    provider: str | None = None
    model: str | None = None
    raw_model_response: str | None = None
    generation_mode: Literal["deterministic_only", "deterministic_plus_llm"] = "deterministic_only"
