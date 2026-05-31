# Backend API route reference

This document is rendered from the checked-in route manifest in `backend/app/api/route_inventory.py` by `python3 scripts/check_backend_route_inventory.py --write-docs`.

## Current inventory

- Registered route count: `60` total (`59` always-on, `1` conditional test-only).
- Frontend-consumed route families: `43`.
- Query-triggered active-read variants: `6`.
- Reviewed raw-response exceptions: `3`.

## Classification counts

- `PASSIVE_READ`: `39`
- `ACTIVE_READ_REFRESH`: `0`
- `BROKER_READ`: `6`
- `MUTATION`: `14`
- `TEST_ONLY_MUTATION`: `1`

## Route reference

| Method | Path | Handler | Classification | Scope | Frontend consumers | Response contract | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DELETE | `/strategy-watchlist/{instrument_id}` | `app.api.routes.markets.remove_strategy_watchlist_item` | `MUTATION` | `operator` | `removeStrategyWatchlistInstrument` | Explicit model: StrategyWatchlistMutationResponse | Strategy-watchlist remove mutation. |
| DELETE | `/watchlist/shortlist/{instrument_id}` | `app.api.routes.markets.remove_shortlist_item` | `MUTATION` | `operator` | `removeShortlistInstrument` | Explicit model: ShortlistMutationResponse | Shortlist remove mutation. |
| GET | `/aimee/snapshot` | `app.api.routes.aimee.get_snapshot` | `PASSIVE_READ` | `operator` | `getAimeeSnapshot` | Explicit model: AimeeSnapshotResponse | Passive AIMEE snapshot. |
| GET | `/allocation/alerts` | `app.api.routes.allocation.list_allocation_alerts` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | `getAllocationAlerts` | Explicit model: list[AllocationAlertResponse] | Default alert reads are passive when refresh=false. Active-read variants: `?refresh=true` -> Explicit alert refresh persists recalculated alerts. |
| GET | `/allocation/alerts/unresolved-critical` | `app.api.routes.allocation.list_unresolved_critical_allocation_alerts` | `PASSIVE_READ` | `operator` | `getUnresolvedCriticalAllocationAlerts` | Explicit model: list[AllocationAlertResponse] | Reads persisted unresolved critical alerts without refresh. |
| GET | `/allocation/cycles` | `app.api.routes.allocation.list_allocation_cycles` | `PASSIVE_READ` | `operator` | `getAllocationCycles` | Explicit model: list[AllocationCycleResponse] | Allocation-cycle read. |
| GET | `/allocation/cycles/{cycle_id}` | `app.api.routes.allocation.get_allocation_cycle` | `PASSIVE_READ` | `operator` | `getAllocationCycle` | Explicit model: AllocationCycleResponse | Allocation-cycle detail read. |
| GET | `/allocation/drift` | `app.api.routes.allocation.get_allocation_drift_summary` | `PASSIVE_READ` | `operator` | `getAllocationDriftSummary` | Explicit model: AllocationDriftSummaryResponse | Computed allocation-drift projection. |
| GET | `/allocation/exposure` | `app.api.routes.allocation.get_allocation_exposure_summary` | `PASSIVE_READ` | `operator` | `getAllocationExposureSummary` | Explicit model: AllocationExposureSummaryResponse | Computed allocation-exposure projection. |
| GET | `/allocation/intents` | `app.api.routes.allocation.list_allocation_intents` | `PASSIVE_READ` | `operator` | `getAllocationIntents` | Explicit model: list[AllocationIntentResponse] | Allocation-intent read. |
| GET | `/allocation/intents/{trade_intent_id}` | `app.api.routes.allocation.get_allocation_intent` | `PASSIVE_READ` | `operator` | `getAllocationIntent` | Explicit model: AllocationIntentResponse | Allocation-intent detail read. |
| GET | `/broker/positions` | `app.api.routes.broker.list_broker_positions` | `BROKER_READ` | `operator` | None | Explicit model: list[BrokerPositionResponse] | Broker position read path. |
| GET | `/charts/drawdown` | `app.api.routes.charts.get_drawdown_chart` | `PASSIVE_READ` | `operator` | None | Reviewed raw exception | Persisted drawdown chart projection. |
| GET | `/charts/equity` | `app.api.routes.charts.get_equity_chart` | `PASSIVE_READ` | `operator` | None | Reviewed raw exception | Persisted equity chart projection. |
| GET | `/charts/risk-allocation` | `app.api.routes.charts.get_risk_allocation_chart` | `PASSIVE_READ` | `operator` | `getRiskAllocationChart` | Explicit model: RiskAllocationChartResponse | Risk-allocation chart contract is backend-owned. |
| GET | `/control-plane/operator-state` | `app.api.routes.control_plane.get_operator_control_state` | `PASSIVE_READ` | `operator` | `getOperatorControlState` | Explicit model: OperatorControlResponse | Operator override read. |
| GET | `/control-plane/strategies/{strategy_name}` | `app.api.routes.control_plane.get_control_plane_strategy_detail` | `PASSIVE_READ` | `operator` | `getControlPlaneFamily` | Explicit model: ControlPlaneFamilyResponse | Control-plane family detail projection. |
| GET | `/control-plane/summary` | `app.api.routes.control_plane.get_control_plane_summary` | `PASSIVE_READ` | `operator` | `getControlPlaneSummary` | Explicit model: ControlPlaneSummaryResponse | Control-plane summary projection. |
| GET | `/coverage/summary` | `app.api.routes.coverage.get_coverage_summary` | `PASSIVE_READ` | `operator` | `getCoverageSummary` | Explicit model: CoverageSummaryResponse | Coverage projection using passive watchlist snapshots. |
| GET | `/dashboard` | `app.api.routes.dashboard.get_dashboard` | `PASSIVE_READ` | `operator` | `getDashboardSnapshot` | Explicit model: DashboardSnapshotResponse | Persisted dashboard snapshot without broker account read. |
| GET | `/events` | `app.api.routes.events.list_events` | `PASSIVE_READ` | `operator` | `getDomainEvents` | Explicit model: list[DomainEventResponse] | Domain-event history projection. |
| GET | `/events/{event_id}` | `app.api.routes.events.get_event` | `PASSIVE_READ` | `operator` | None | Explicit model: DomainEventResponse | Single domain-event read. |
| GET | `/executions` | `app.api.routes.executions.list_executions` | `PASSIVE_READ` | `operator` | `getExecutions` | Explicit model: list[ExecutionResponse] | Execution-history read. |
| GET | `/health` | `app.api.routes.health.health_check` | `PASSIVE_READ` | `internal/diagnostic` | None | Reviewed raw exception | Static health response. |
| GET | `/health/stream` | `app.api.routes.health.stream_health_check` | `PASSIVE_READ` | `internal/diagnostic` | `getStreamHealth` | Explicit model: StreamHealthResponse | Streaming health projection. |
| GET | `/live/instruments/{instrument_id}/chart` | `app.api.routes.markets.get_live_instrument_chart` | `BROKER_READ` | `operator` | `getLiveInstrumentChart` | Explicit model: LiveChartResponse | Live chart projection with broker candle reads. |
| GET | `/market-data/feed-state` | `app.api.routes.markets.get_feed_state` | `BROKER_READ` | `operator` | `getFeedState` | Explicit model: FeedStateResponse | Feed-state snapshot with broker-backed readiness metadata. |
| GET | `/market-data/feed-state/{instrument_id}` | `app.api.routes.markets.get_instrument_feed_state` | `BROKER_READ` | `operator` | `getInstrumentFeedState` | Explicit model: FeedStateInstrumentResponse | Per-instrument feed-state snapshot. |
| GET | `/market-status/{instrument}` | `app.api.routes.market_status.get_market_status` | `BROKER_READ` | `operator` | None | Explicit model: MarketStatusResponse | Broker/market status read. |
| GET | `/markets/catalogue` | `app.api.routes.markets.get_market_catalogue` | `PASSIVE_READ` | `operator` | `getMarketCatalogue` | Explicit model: MarketCatalogueResponse | Markets catalogue projection. |
| GET | `/markets/overview` | `app.api.routes.markets.get_market_overview` | `BROKER_READ` | `operator` | `getMarketOverview` | Explicit model: MarketCategoryOverviewResponse | Broker-backed markets overview. |
| GET | `/positions` | `app.api.routes.positions.list_positions` | `PASSIVE_READ` | `operator` | None | Explicit model: list[OpenPositionResponse] | Compatibility open-position read. |
| GET | `/reviews/daily` | `app.api.routes.ai_reviewer.get_daily_review` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | None | Explicit model: DailyReviewResponse | Default daily review is a passive preview. Active-read variants: `?persist=true` -> Explicit daily-review archival persists a GeneratedReviewRecord. |
| GET | `/reviews/history` | `app.api.routes.ai_reviewer.list_review_history` | `PASSIVE_READ` | `operator` | `getReviewHistory` | Explicit model: list[ReviewRecordSummary] | Persisted review-history read. |
| GET | `/reviews/history/{review_id}` | `app.api.routes.ai_reviewer.get_review_record` | `PASSIVE_READ` | `operator` | None | Explicit model: PersistedReviewRecord | Persisted review-record read. |
| GET | `/reviews/operator-summary` | `app.api.routes.ai_reviewer.get_operator_summary` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | `getOperatorSummaryReview` | Explicit model: OperatorSummaryReview | Default operator-summary review is a passive preview. Active-read variants: `?persist=true` -> Explicit review archival persists a GeneratedReviewRecord. |
| GET | `/reviews/runtime-health` | `app.api.routes.ai_reviewer.get_runtime_health_review` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | None | Explicit model: RuntimeHealthReviewResponse | Default runtime-health review is a passive preview. Active-read variants: `?persist=true` -> Explicit runtime-health review archival persists a GeneratedReviewRecord. |
| GET | `/reviews/strategies/{strategy_name}` | `app.api.routes.ai_reviewer.get_strategy_review` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | None | Explicit model: StrategyReviewResponse | Default strategy review is a passive preview. Active-read variants: `?persist=true` -> Explicit strategy-review archival persists a GeneratedReviewRecord. |
| GET | `/reviews/trades/{trade_id}/postmortem` | `app.api.routes.ai_reviewer.get_trade_postmortem` | `PASSIVE_READ with ACTIVE_READ_REFRESH variant(s)` | `operator` | None | Explicit model: TradePostMortemReviewResponse | Default trade postmortem is a passive preview. Active-read variants: `?persist=true` -> Explicit trade-postmortem archival persists a GeneratedReviewRecord. |
| GET | `/strategies` | `app.api.routes.strategies.list_strategies` | `PASSIVE_READ` | `operator` | `getStrategies` | Explicit model: list[StrategySummaryResponse] | Strategy-summary projection. |
| GET | `/strategy-watchlist` | `app.api.routes.markets.get_strategy_watchlist` | `PASSIVE_READ` | `operator` | `getStrategyWatchlist` | Explicit model: StrategyWatchlistResponse | Strategy-watchlist projection with sync=false. |
| GET | `/system/health` | `app.api.routes.health.system_health_check` | `PASSIVE_READ` | `internal/diagnostic` | None | Explicit model: SystemHealthResponse | Aggregated health projection. |
| GET | `/system/limits` | `app.api.routes.system.get_system_operating_limits` | `PASSIVE_READ` | `operator` | `getSystemOperatingLimits` | Explicit model: SystemOperatingLimitsResponse | Settings and operating-limits projection. |
| GET | `/system/telemetry` | `app.api.routes.health.operational_telemetry` | `PASSIVE_READ` | `internal/diagnostic` | `getOperationalTelemetry`, `getBrokerAuthStatus` | Explicit model: OperationalTelemetryResponse | Aggregated telemetry projection. |
| GET | `/trades` | `app.api.routes.trades.list_trades` | `PASSIVE_READ` | `operator` | `getTrades` | Explicit model: list[TradeResponse] | Trade-history read. |
| GET | `/trades/positions` | `app.api.routes.trades.list_positions_compat` | `PASSIVE_READ` | `operator` | `getOpenPositions` | Explicit model: list[OpenPositionResponse] | Frontend-consumed compatibility positions read. |
| GET | `/watchlist/shortlist` | `app.api.routes.markets.get_shortlist` | `PASSIVE_READ` | `operator` | None | Explicit model: ShortlistResponse | Shortlist projection. |
| POST | `/allocation/alerts/{alert_id}/acknowledge` | `app.api.routes.allocation.acknowledge_allocation_alert` | `MUTATION` | `operator` | `acknowledgeAllocationAlert` | Explicit model: AllocationAlertMutationResponse | Acknowledges an allocation alert. |
| POST | `/allocation/alerts/{alert_id}/resolve` | `app.api.routes.allocation.resolve_allocation_alert` | `MUTATION` | `operator` | `resolveAllocationAlert` | Explicit model: AllocationAlertMutationResponse | Resolves an allocation alert. |
| POST | `/control-plane/reconcile` | `app.api.routes.control_plane.reconcile_control_plane` | `MUTATION` | `operator` | None | Explicit model: ControlPlaneReconcileResponse | Deployment/runtime reconciliation mutation. |
| POST | `/reviews/questions` | `app.api.routes.ai_reviewer.answer_operational_question` | `MUTATION` | `operator` | `askOperationalQuestion` | Explicit model: OperationalQuestionReviewResponse | Explicit advisory-question persistence route. |
| POST | `/strategies/{name}/start` | `app.api.routes.strategies.start_strategy_by_name` | `MUTATION` | `operator` | None | Explicit model: StrategyMutationStatusResponse | Compatibility strategy start mutation. |
| POST | `/strategies/{name}/stop` | `app.api.routes.strategies.stop_strategy_by_name` | `MUTATION` | `operator` | None | Explicit model: StrategyMutationStatusResponse | Compatibility strategy stop mutation. |
| POST | `/strategy-watchlist/bulk` | `app.api.routes.markets.add_strategy_watchlist_items` | `MUTATION` | `operator` | `addStrategyWatchlistInstruments` | Explicit model: StrategyWatchlistBulkResponse | Bulk strategy-watchlist mutation. |
| POST | `/strategy/start` | `app.api.routes.strategies.start_strategy` | `MUTATION` | `operator` | `startStrategy` | Explicit model: StrategyMutationStatusResponse | Strategy start mutation. |
| POST | `/strategy/stop` | `app.api.routes.strategies.stop_strategy` | `MUTATION` | `operator` | `stopStrategy` | Explicit model: StrategyMutationStatusResponse | Strategy stop mutation. |
| POST | `/testing/reset-history` | `app.api.routes.testing.reset_history` | `TEST_ONLY_MUTATION` | `test-only` | `resetTestHistory` | Explicit model: ResetHistoryResponse | Conditional destructive test reset route. Registered only when `TESTING_ROUTES_ENABLED=true`. |
| POST | `/watchlist/shortlist/{instrument_id}` | `app.api.routes.markets.add_shortlist_item` | `MUTATION` | `operator` | `addShortlistInstrument` | Explicit model: ShortlistMutationResponse | Shortlist add mutation. |
| PUT | `/control-plane/governance/{strategy_name}` | `app.api.routes.control_plane.update_strategy_governance` | `MUTATION` | `operator` | `updateStrategyGovernance` | Explicit model: GovernanceMutationResponse | Governance mutation. |
| PUT | `/control-plane/operator-state` | `app.api.routes.control_plane.update_operator_control_state` | `MUTATION` | `operator` | `updateOperatorControlState` | Explicit model: OperatorControlResponse | Operator override mutation. |

## Reviewed raw-response exceptions

- `GET /health`: Static service heartbeat used for local diagnostics only; not a current frontend-consumed operator contract.
- `GET /charts/equity`: Persisted chart projection not currently consumed by frontend/lib/api.ts; keep raw until an operator surface depends on it.
- `GET /charts/drawdown`: Persisted chart projection not currently consumed by frontend/lib/api.ts; keep raw until an operator surface depends on it.

## Guardrails

- Registered FastAPI routes are checked against the checked-in manifest.
- A new route fails the check if it is undocumented, unclassified, or wired to a different handler than the manifest expects.
- Mutation routes and query-triggered active-read routes fail the check if they bypass `requires_operator_auth()`.
- Test-only routes fail the check if they register outside the explicit testing gate.
- Raw responses are allowed only through a reviewed exception entry with rationale.
- Frontend-consumed route families are expected to keep explicit backend response models; the reviewed raw-exception path is reserved for deliberate cases only.
