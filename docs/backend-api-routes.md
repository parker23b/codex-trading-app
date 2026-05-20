# Backend API route reference

This document describes the FastAPI routes currently registered by `backend/app/api/router.py`.
Routes under `/testing/*` are conditional and are only registered when `TESTING_ROUTES_ENABLED=true`.
It is an implementation reference, not a requirements spec. Requirements live in `docs/spec/`,
and audit findings live in `docs/audit-status.md`.

Generated from the registered route table on 2026-05-05 and supplemented with service-call
audit notes from the backend API audit.

## Classification legend

| Classification | Meaning |
| --- | --- |
| `PASSIVE_READ` | Read-only route with no expected local writes, refreshes, broker calls, runtime changes, or event creation. |
| `ACTIVE_READ_REFRESH` | GET/read-shaped route that can refresh, seed, sync, persist, or otherwise update local state while returning a read model. |
| `BROKER_READ` | Route that can call broker read APIs or broker-derived market/account data paths. |
| `MUTATION` | Route that intentionally mutates local state, runtime state, governance, watchlists, alerts, reviews, or deployments. |
| `BROKER_MUTATION` | Route that can submit broker-changing actions. No direct registered API route was classified this way in the audit. |
| `TEST_ONLY_MUTATION` | Route intended for test/dev reset behavior. Must be environment-gated before production use. |
| `NEEDS_AUDIT` | Route requiring more service tracing before classification can be trusted. |

## Known audit notes

| Finding ID | Applies to | Summary |
| --- | --- | --- |
| `AUDIT-003` | `/allocation/alerts`, `/allocation/alerts/unresolved-critical` | Default alert reads can refresh and persist alert rows. |
| `AUDIT-API-001` | `/control-plane/summary`, `/control-plane/operator-state`, `/control-plane/strategies/{strategy_name}`, `/strategies` | Passive-looking GET routes can seed operator/governance defaults. |
| `AUDIT-API-002` | `/coverage/summary`, `/strategy-watchlist`, `/market-data/feed-state` | Verified fixed for the read/write boundary: these GET routes now use passive snapshots (`sync=false`) where intended and have no-write regression evidence. |
| `AUDIT-API-003` | `/reviews/operator-summary`, `/reviews/daily`, `/reviews/strategies/{strategy_name}`, `/reviews/runtime-health`, `/reviews/trades/{trade_id}/postmortem` | Review GET routes persist `GeneratedReviewRecord` rows by default. |
| `AUDIT-API-004` | `/testing/reset-history` | Verified fixed: test reset route is registered only when `TESTING_ROUTES_ENABLED=true`; frontend control/API helper require `NEXT_PUBLIC_TESTING_CONTROLS_ENABLED=true`. |
| `AUDIT-API-005` | `/dashboard` | Dashboard performs a live broker account read despite passive-style wording. |
| `AUDIT-API-006` | Multiple frontend-used routes | Allocation/risk, AIMEE/review, and the markets/watchlist/feed-state/live-chart frontend-consumed slice are now modelled; several other operator-critical route families still return raw dict/list shapes rather than modeled schemas. |
| `AUDIT-API-007` | `/aimee/snapshot` | AIMEE passive snapshot indirectly performs a broker account read. |
| `AUDIT-API-008` | Control-plane and strategy mutations | Safety-relevant mutation audit events are persisted best-effort and can fail silently. |

## Route reference

| Method | Path | Handler | Classification | Response contract | Frontend consumer | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `app.api.routes.health.health_check` | `PASSIVE_READ` | `dict[str, str]` | None found | Static health response. |
| GET | `/health/stream` | `app.api.routes.health.stream_health_check` | `PASSIVE_READ` | `StreamHealthResponse` | `getStreamHealth` | Reads streaming health state. |
| GET | `/system/health` | `app.api.routes.health.system_health_check` | `PASSIVE_READ` | `SystemHealthResponse` | None found | Reads system health report. |
| GET | `/system/telemetry` | `app.api.routes.health.operational_telemetry` | `PASSIVE_READ` | `OperationalTelemetryResponse` | `getOperationalTelemetry`, `getBrokerAuthStatus` | Reads telemetry, runtime, and health state. |
| GET | `/system/limits` | `app.api.routes.system.get_system_operating_limits` | `PASSIVE_READ` | `SystemOperatingLimitsResponse` | `getSystemOperatingLimits` | Reads settings and strategy registry limits. |
| GET | `/broker/positions` | `app.api.routes.broker.list_broker_positions` | `BROKER_READ` | `list[BrokerPositionResponse]` | None found | Calls broker position read path and updates in-memory broker health. |
| GET | `/control-plane/summary` | `app.api.routes.control_plane.get_control_plane_summary` | `ACTIVE_READ_REFRESH` | `ControlPlaneSummaryResponse` | `getControlPlaneSummary` | Can seed governance defaults. See `AUDIT-API-001`. |
| GET | `/control-plane/operator-state` | `app.api.routes.control_plane.get_operator_control_state` | `ACTIVE_READ_REFRESH` | `OperatorControlResponse` | `getOperatorControlState` | Can seed `OperatorControlState`. See `AUDIT-API-001`. |
| PUT | `/control-plane/operator-state` | `app.api.routes.control_plane.update_operator_control_state` | `MUTATION` | `OperatorControlResponse` | `updateOperatorControlState` | Updates autonomy override and records audit event best-effort. See `AUDIT-API-008`. |
| GET | `/control-plane/strategies/{strategy_name}` | `app.api.routes.control_plane.get_control_plane_strategy_detail` | `ACTIVE_READ_REFRESH` | `dict[str, object]` | `getControlPlaneFamily` | Can seed governance defaults. Needs modeled schema. See `AUDIT-API-001`, `AUDIT-API-006`. |
| POST | `/control-plane/reconcile` | `app.api.routes.control_plane.reconcile_control_plane` | `MUTATION` | `dict[str, int]` | None found | Reconciles deployment/runtime alignment and records audit events best-effort. See `AUDIT-API-008`. |
| PUT | `/control-plane/governance/{strategy_name}` | `app.api.routes.control_plane.update_strategy_governance` | `MUTATION` | `dict[str, object]` | `updateStrategyGovernance` | Updates governance and records audit event best-effort. Needs modeled schema. See `AUDIT-API-006`, `AUDIT-API-008`. |
| GET | `/coverage/summary` | `app.api.routes.coverage.get_coverage_summary` | `ACTIVE_READ_REFRESH` | `CoverageSummaryResponse` | `getCoverageSummary` | Can sync watchlist state and perform broker market reads. See `AUDIT-API-002`. |
| GET | `/dashboard` | `app.api.routes.dashboard.get_dashboard` | `BROKER_READ` | `dict[str, object]` | `getDashboardSnapshot` | Calls broker account summary read path. Needs modeled schema. See `AUDIT-API-005`, `AUDIT-API-006`. |
| GET | `/events` | `app.api.routes.events.list_events` | `PASSIVE_READ` | `list[DomainEventResponse]` | `getDomainEvents` | Reads domain-event history. |
| GET | `/events/{event_id}` | `app.api.routes.events.get_event` | `PASSIVE_READ` | `DomainEventResponse` | None found | Reads one domain event. |
| GET | `/allocation/cycles` | `app.api.routes.allocation.list_allocation_cycles` | `PASSIVE_READ` | `list[AllocationCycleResponse]` | `getAllocationCycles` | Allocation read model. Nested contract is now modelled. |
| GET | `/allocation/cycles/{cycle_id}` | `app.api.routes.allocation.get_allocation_cycle` | `PASSIVE_READ` | `AllocationCycleResponse` | `getAllocationCycle` | Allocation read model. Nested contract is now modelled. |
| GET | `/allocation/intents` | `app.api.routes.allocation.list_allocation_intents` | `PASSIVE_READ` | `list[AllocationIntentResponse]` | `getAllocationIntents` | Allocation read model. Nested execution/position/trade provenance is now modelled. |
| GET | `/allocation/intents/{trade_intent_id}` | `app.api.routes.allocation.get_allocation_intent` | `PASSIVE_READ` | `AllocationIntentResponse` | `getAllocationIntent` | Allocation read model. Nested execution/position/trade provenance is now modelled. |
| GET | `/allocation/drift` | `app.api.routes.allocation.get_allocation_drift_summary` | `PASSIVE_READ` | `AllocationDriftSummaryResponse` | `getAllocationDriftSummary` | Computed allocation drift read model. Contract is now modelled. |
| GET | `/allocation/alerts` | `app.api.routes.allocation.list_allocation_alerts` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `refresh=true` | `list[AllocationAlertResponse]` | `getAllocationAlerts` | Default `refresh=false` is passive. `refresh=true` can persist alert rows. See `AUDIT-003`. |
| POST | `/allocation/alerts/{alert_id}/acknowledge` | `app.api.routes.allocation.acknowledge_allocation_alert` | `MUTATION` | `AllocationAlertMutationResponse` | `acknowledgeAllocationAlert` | Acknowledges alert state. Mutation response is now modelled. |
| POST | `/allocation/alerts/{alert_id}/resolve` | `app.api.routes.allocation.resolve_allocation_alert` | `MUTATION` | `AllocationAlertMutationResponse` | `resolveAllocationAlert` | Resolves alert state. Mutation response is now modelled. |
| GET | `/allocation/alerts/unresolved-critical` | `app.api.routes.allocation.list_unresolved_critical_allocation_alerts` | `PASSIVE_READ` | `list[AllocationAlertResponse]` | `getUnresolvedCriticalAllocationAlerts` | Reads persisted unresolved critical alerts without refresh. Contract now matches the full alert schema used by the frontend. See `AUDIT-003`. |
| GET | `/allocation/exposure` | `app.api.routes.allocation.get_allocation_exposure_summary` | `PASSIVE_READ` | `AllocationExposureSummaryResponse` | `getAllocationExposureSummary` | Computed exposure read model. Contract is now modelled. |
| GET | `/market-status/{instrument}` | `app.api.routes.market_status.get_market_status` | `BROKER_READ` | `MarketStatusResponse` | None found | Calls broker market-details read path and updates in-memory broker health. |
| GET | `/markets/overview` | `app.api.routes.markets.get_market_overview` | `BROKER_READ` | `MarketCategoryOverviewResponse` | `getMarketOverview` | Calls broker market-details read path. Backend-owned schema now models market status/count fields used by Markets. |
| GET | `/markets/catalogue` | `app.api.routes.markets.get_market_catalogue` | `PASSIVE_READ` | `MarketCatalogueResponse` | `getMarketCatalogue` | Reads catalogue/runtime projection without watchlist sync. |
| GET | `/watchlist/shortlist` | `app.api.routes.markets.get_shortlist` | `PASSIVE_READ` | `ShortlistResponse` | None found | Reads shortlist projection with shortlist timestamps and separate streaming/watchlist flags. |
| POST | `/watchlist/shortlist/{instrument_id}` | `app.api.routes.markets.add_shortlist_item` | `MUTATION` | `ShortlistMutationResponse` | `addShortlistInstrument` | Adds or updates shortlist entry with explicit typed mutation response. |
| DELETE | `/watchlist/shortlist/{instrument_id}` | `app.api.routes.markets.remove_shortlist_item` | `MUTATION` | `ShortlistMutationResponse` | `removeShortlistInstrument` | Removes shortlist entry with explicit typed mutation response. |
| POST | `/strategy-watchlist/bulk` | `app.api.routes.markets.add_strategy_watchlist_items` | `MUTATION` | `StrategyWatchlistBulkResponse` | `addStrategyWatchlistInstruments` | Adds strategy-watchlist entries and preserves structured added/skipped reasons. |
| GET | `/strategy-watchlist` | `app.api.routes.markets.get_strategy_watchlist` | `PASSIVE_READ` | `StrategyWatchlistResponse` | `getStrategyWatchlist` | Uses passive `sync=false` watchlist snapshot; route-tested no-write. See `AUDIT-API-002`. |
| DELETE | `/strategy-watchlist/{instrument_id}` | `app.api.routes.markets.remove_strategy_watchlist_item` | `MUTATION` | `StrategyWatchlistMutationResponse` | `removeStrategyWatchlistInstrument` | Removes or cools down strategy-watchlist entry with explicit typed mutation response. |
| GET | `/market-data/feed-state` | `app.api.routes.markets.get_feed_state` | `BROKER_READ` | `FeedStateResponse` | `getFeedState` | Passive no-write snapshot route, but still broker-read because per-instrument market readiness may refresh broker market status. |
| GET | `/market-data/feed-state/{instrument_id}` | `app.api.routes.markets.get_instrument_feed_state` | `BROKER_READ` | `FeedStateInstrumentResponse` | `getInstrumentFeedState` | Exposes stream/freshness/provenance fields, unavailable market-status detail, and evaluation-vs-streaming distinction. |
| GET | `/live/instruments/{instrument_id}/chart` | `app.api.routes.markets.get_live_instrument_chart` | `BROKER_READ` | `LiveChartResponse` | `getLiveInstrumentChart` | Can call broker historical-candle and market-status reads; explicit schema keeps chart-source vs feed-state provenance visible. |
| GET | `/charts/equity` | `app.api.routes.charts.get_equity_chart` | `PASSIVE_READ` | `list[dict[str, float | str]]` | None found | Computes persisted equity projection. |
| GET | `/charts/drawdown` | `app.api.routes.charts.get_drawdown_chart` | `PASSIVE_READ` | `list[dict[str, float | str]]` | None found | Computes persisted drawdown projection. |
| GET | `/charts/risk-allocation` | `app.api.routes.charts.get_risk_allocation_chart` | `PASSIVE_READ` | `dict[str, object]` | None found | Computes persisted risk allocation projection. Needs modeled schema. |
| GET | `/positions` | `app.api.routes.positions.list_positions` | `PASSIVE_READ` | `list[PositionResponse]` | None found | Reads persisted positions. |
| GET | `/executions` | `app.api.routes.executions.list_executions` | `PASSIVE_READ` | `list[ExecutionResponse]` | `getExecutions` | Reads persisted executions. |
| GET | `/trades` | `app.api.routes.trades.list_trades` | `PASSIVE_READ` | `list[TradeResponse]` | `getTrades` | Reads persisted trades. |
| GET | `/trades/positions` | `app.api.routes.trades.list_positions_compat` | `PASSIVE_READ` | `list[dict[str, object]]` | `getOpenPositions` | Compatibility persisted-position read. Needs modeled schema. |
| GET | `/strategies` | `app.api.routes.strategies.list_strategies` | `ACTIVE_READ_REFRESH` | `list[dict[str, object]]` | `getStrategies` | Can seed governance defaults. Needs modeled schema. See `AUDIT-API-001`. |
| POST | `/strategy/start` | `app.api.routes.strategies.start_strategy` | `MUTATION` | `dict[str, str]` | `startStrategy` | Starts runtime and syncs persisted runtime state. Audit event is best-effort. See `AUDIT-API-008`. |
| POST | `/strategy/stop` | `app.api.routes.strategies.stop_strategy` | `MUTATION` | `dict[str, str]` | `stopStrategy` | Stops runtime and syncs persisted runtime state. Audit event is best-effort. See `AUDIT-API-008`. |
| POST | `/strategies/{name}/start` | `app.api.routes.strategies.start_strategy_by_name` | `MUTATION` | `StrategyControlResponse` | None found | Compatibility strategy-start route. |
| POST | `/strategies/{name}/stop` | `app.api.routes.strategies.stop_strategy_by_name` | `MUTATION` | `StrategyControlResponse` | None found | Compatibility strategy-stop route. |
| GET | `/aimee/snapshot` | `app.api.routes.aimee.get_snapshot` | `BROKER_READ` | `AimeeSnapshotResponse` | `getAimeeSnapshot` | Passive AIMEE snapshot is now backend-modelled and route-tested for no-write behavior. It no longer performs the old indirect dashboard broker-account read. See `AUDIT-API-007`, `AUDIT-API-006`. |
| GET | `/reviews/operator-summary` | `app.api.routes.ai_reviewer.get_operator_summary` | `ACTIVE_READ_REFRESH` when `persist=true`; otherwise passive preview | `OperatorSummaryReview` | `getOperatorSummaryReview` | Default preview is non-persisting; explicit `persist=true` persists a review record and durable audit event. See `AUDIT-API-003`, `AUDIT-API-008`. |
| GET | `/reviews/daily` | `app.api.routes.ai_reviewer.get_daily_review` | `ACTIVE_READ_REFRESH` when `persist=true`; otherwise passive preview | `DailyReviewResponse` | None found | Default preview is non-persisting; explicit `persist=true` persists a review record and durable audit event. See `AUDIT-API-003`, `AUDIT-API-008`. |
| GET | `/reviews/strategies/{strategy_name}` | `app.api.routes.ai_reviewer.get_strategy_review` | `ACTIVE_READ_REFRESH` when `persist=true`; otherwise passive preview | `StrategyReviewResponse` | None found | Default preview is non-persisting; explicit `persist=true` persists a review record and durable audit event. See `AUDIT-API-003`, `AUDIT-API-008`. |
| GET | `/reviews/runtime-health` | `app.api.routes.ai_reviewer.get_runtime_health_review` | `ACTIVE_READ_REFRESH` when `persist=true`; otherwise passive preview | `RuntimeHealthReviewResponse` | None found | Default preview is non-persisting; explicit `persist=true` persists a review record and durable audit event. See `AUDIT-API-003`, `AUDIT-API-008`. |
| GET | `/reviews/trades/{trade_id}/postmortem` | `app.api.routes.ai_reviewer.get_trade_postmortem` | `ACTIVE_READ_REFRESH` when `persist=true`; otherwise passive preview | `TradePostMortemReviewResponse` | None found | Default preview is non-persisting; explicit `persist=true` persists a review record and durable audit event. See `AUDIT-API-003`, `AUDIT-API-008`. |
| POST | `/reviews/questions` | `app.api.routes.ai_reviewer.answer_operational_question` | `MUTATION` | `OperationalQuestionReviewResponse` | `askOperationalQuestion` | Persists explicit advisory artifact. |
| GET | `/reviews/history` | `app.api.routes.ai_reviewer.list_review_history` | `PASSIVE_READ` | `list[ReviewRecordSummary]` | `getReviewHistory` | Reads persisted review history. |
| GET | `/reviews/history/{review_id}` | `app.api.routes.ai_reviewer.get_review_record` | `PASSIVE_READ` | `PersistedReviewRecord` | None found | Reads one persisted review record. |
| POST | `/testing/reset-history` | `app.api.routes.testing.reset_history` | `TEST_ONLY_MUTATION` | `ResetHistoryResponse` | `resetTestHistory` when `NEXT_PUBLIC_TESTING_CONTROLS_ENABLED=true` | Conditional route: registered only when `TESTING_ROUTES_ENABLED=true`. Deletes trading, reconciliation, domain-event, runtime, and review history when enabled. See `AUDIT-API-004`. |

## Recommended route documentation tests

- Assert the registered route inventory matches this document and `docs/spec/04-backend-api-contract.md`.
- Add no-write tests for routes documented as `PASSIVE_READ`.
- Add explicit side-effect tests for `ACTIVE_READ_REFRESH` routes.
- Add broker-call provenance tests for `BROKER_READ` routes.
- Add response-schema contract tests for the remaining frontend-consumed raw dict/list routes outside the covered allocation/risk and AIMEE/review frontend-consumed families.
- Maintain production-gating tests for `TEST_ONLY_MUTATION` routes.
