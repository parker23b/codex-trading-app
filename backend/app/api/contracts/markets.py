from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class OperatorReasonResponse(BaseModel):
    code: str
    label: str
    operator_action: str
    components: list["OperatorReasonResponse"] | None = None


class MarketReadinessResponse(BaseModel):
    instrument: str
    is_ok: bool
    market_open: bool
    tradable: bool
    quote_fresh: bool
    spread_ok: bool
    session_valid: bool
    dealing_allowed: bool
    last_price_age_ms: float
    spread: float | None
    reason: str | None


class MarketCatalogueInstrumentResponse(BaseModel):
    id: str
    instrument: str
    name: str
    symbol: str
    asset_class: str
    category: str
    currency: str | None
    base_currency: str | None
    quote_currency: str | None
    forex_major: bool
    tradable: bool
    shortlisted: bool
    in_strategy_watchlist: bool
    streaming_now: bool
    activity_level: str
    strategy_compatibility: list[str]
    reference_price: float | None


class ShortlistInstrumentResponse(MarketCatalogueInstrumentResponse):
    shortlisted_at: datetime | None = None
    note: str | None = None


class MarketCatalogueSummaryResponse(BaseModel):
    total_count: int
    shortlisted_count: int
    strategy_watchlist_count: int
    streaming_count: int


class MarketCatalogueResponse(BaseModel):
    generated_at: datetime
    instruments: list[MarketCatalogueInstrumentResponse]
    summary: MarketCatalogueSummaryResponse


class ShortlistResponse(BaseModel):
    generated_at: datetime
    instruments: list[ShortlistInstrumentResponse]
    count: int


class ShortlistMutationResponse(BaseModel):
    status: Literal["shortlisted", "removed"]
    instrument: MarketCatalogueInstrumentResponse | str


class StrategyWatchlistMutationItemResponse(BaseModel):
    instrument: str
    reason: str
    reason_detail: OperatorReasonResponse


class StrategyWatchlistBulkResponse(BaseModel):
    added: list[StrategyWatchlistMutationItemResponse] = Field(default_factory=list)
    skipped: list[StrategyWatchlistMutationItemResponse] = Field(default_factory=list)
    limit: int


class StrategyWatchlistEntryResponse(BaseModel):
    instrument: str
    tier: str
    status: str
    asset_class: str | None
    pinned: bool
    reason: str | None
    reason_detail: OperatorReasonResponse
    protective: bool
    priority_score: float
    requested_frequency: str | None
    promotion_expires_at: datetime | None
    last_streamed_at: datetime | None
    last_refreshed_at: datetime | None
    streamed: bool


class StrategyWatchlistResponse(BaseModel):
    generated_at: datetime
    limit: int
    active_count: int
    normal_count: int
    streaming_count: int
    protective_count: int
    cap_exceeded_by_protective_coverage: bool
    instruments: list[StrategyWatchlistEntryResponse]


class StrategyWatchlistMutationResponse(BaseModel):
    status: Literal["removed"]
    instrument: str


class FeedStateInstrumentResponse(BaseModel):
    instrument: str
    stream_status: str
    stream_reason: OperatorReasonResponse
    stream_connected: bool
    stream_enabled: bool
    streaming_now: bool
    desired: bool
    capped: bool
    last_tick_at: datetime | None
    last_tick_age_ms: float | None
    spread: float | None
    price_source: Literal["STREAM", "SNAPSHOT", "STALE", "UNAVAILABLE"]
    market_status: MarketReadinessResponse | None
    market_error: str | None
    entry_eligibility: str
    entry_eligibility_reason: OperatorReasonResponse
    strategies_may_evaluate: bool
    active_strategy_runtime_count: int
    watchlist_entry: StrategyWatchlistEntryResponse | None = None


class FeedStateResponse(BaseModel):
    generated_at: datetime
    instruments: list[FeedStateInstrumentResponse]


class LiveChartCandleResponse(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int | float | None = None
    source: (
        Literal[
            "STREAM",
            "REST_CANDLES",
            "SNAPSHOT",
            "FALLBACK",
            "STALE",
            "UNAVAILABLE",
        ]
        | None
    ) = None


class LiveChartResponse(BaseModel):
    instrument: str
    timeframe: str
    source: Literal[
        "STREAM",
        "REST_CANDLES",
        "SNAPSHOT",
        "FALLBACK",
        "STALE",
        "UNAVAILABLE",
    ]
    data_state: Literal["READY", "EMPTY", "UNSUPPORTED"]
    reason_detail: OperatorReasonResponse | None = None
    candles: list[LiveChartCandleResponse]
    markers: list[dict[str, Any]]
    position_overlays: list[dict[str, Any]]
    intent_markers: list[dict[str, Any]]
    execution_markers: list[dict[str, Any]]
    feed_state: FeedStateInstrumentResponse


class MarketInstrumentResponse(BaseModel):
    id: str
    category: str
    name: str
    symbol: str
    status: Literal["OPEN", "CLOSED", "LIMITED"]
    tradable: bool
    active: bool
    activityLevel: Literal["LOW", "MEDIUM", "HIGH"]
    strategyCompatibility: list[str]
    price: float
    changePercent: float
    sessionNote: str | None = None


class MarketSummaryResponse(BaseModel):
    category: str
    label: str
    description: str
    status: Literal["OPEN", "CLOSED", "LIMITED"]
    headline: str
    detail: str
    nextTransitionAt: str
    nextTransitionLabel: Literal["Closes", "Opens"]
    tradableCount: int
    activeCount: int
    totalCount: int


class MarketCategoryOverviewResponse(BaseModel):
    generatedAt: str
    summary: MarketSummaryResponse
    instruments: list[MarketInstrumentResponse]
