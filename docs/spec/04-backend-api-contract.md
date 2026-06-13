# Backend API contract

Backend APIs expose operational truth and mutations to the operator console. Routes must be classified clearly. Passive reads must not mutate state. Mutations must be obvious in HTTP method, path, UI copy, audit trail, and tests. Frontend-consumed response fields must be stable, typed, or documented.

## Route classification categories

Every route should use one of these classifications:

- `PASSIVE_READ`: observes existing local state only. Must not write, flush, commit, seed defaults, refresh persisted state, reconcile broker state, start/stop runtimes, mutate broker state, create events, or persist advisory records.
- `ACTIVE_READ_REFRESH`: returns a read model but intentionally refreshes, reconciles, seeds, persists, or otherwise changes local state as part of the request. This is mutation-like and must be documented/tested as such.
- `BROKER_READ`: reads broker/account/market/position/sizing information without intentionally changing broker state. May still be operationally sensitive and must expose freshness/provenance where operator-critical.
- `MUTATION`: intentionally changes local operational state, governance, runtime, watchlist, alerts, reviews, events, or other persisted state.
- `BROKER_MUTATION`: can place, close, amend, cancel, or otherwise change broker-side trading state. Requires lifecycle authority and audit evidence.
- `TEST_ONLY_MUTATION`: mutation route intended only for local/dev/test workflows. Must be environment-gated and unavailable in production-like operation.

Routes currently labelled with softer terms such as `Read/projection`, `Read by default; mutation-like when refresh=true`, or `Mutation-like advisory GET` should be migrated toward these categories.

## API invariants

| Spec ID | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- |
| API-001 | GET routes MUST be `PASSIVE_READ` unless explicitly classified as `ACTIVE_READ_REFRESH`, `BROKER_READ`, or another documented exception. Passive GET routes must not mutate operational state directly or indirectly. | Route tests or code review proving no commit/add/delete/flush/reconciliation/default seeding/watchlist sync/alert refresh/review persistence/runtime mutation/broker mutation. | P1 | Medium |
| API-002 | Mutating routes MUST make side effects clear in HTTP method, path, request body, route classification, service name, and frontend UI copy. Mutation-like GET routes must be treated as exceptions or redesign candidates. | Route inventory, frontend controls, route tests, and UI copy review. | P1 | Medium |
| API-003 | Response fields consumed by frontend operator surfaces MUST be stable, typed, or documented. Operator-critical routes should use Pydantic response models or documented dict schemas. | Pydantic response models, OpenAPI schemas, documented dict response contracts, or frontend type contract tests. | P1 | Medium |
| API-004 | Backend route response changes MUST update frontend types, API client assumptions, and this spec when the changed fields are consumed by the operator console. | Changes to route response shape include updates to `frontend/lib/types.ts`, `frontend/lib/api.ts`, relevant component assumptions, and this spec. | P1 | Low |
| API-005 | Broker mutation routes MUST NOT bypass lifecycle authority or audit. Entry orders require approved `TradeIntent` admission. Exit/close actions require known open risk, recovery/reconciliation authority, or explicit operator action. | Tests for order/close/recovery mutation paths proving intent/execution/reconciliation/event evidence. | P0 | Medium |
| API-006 | Error responses for operator actions must include actionable detail where possible. | Route tests for 4xx/5xx detail and frontend display. | P2 | Low |
| API-007 | Every route in `backend/app/api/router.py` and `backend/app/api/routes/*` must appear in this inventory with method, path, route function, classification, side-effect notes, frontend consumer, response contract status, and confidence. | Route inventory audit comparing registered FastAPI routes to this spec. | P1 | Medium |
| API-008 | Write-on-read behavior must be explicitly classified as `ACTIVE_READ_REFRESH` and treated as mutation-like for tests, UI copy, audit, and future redesign. It must not be labelled as passive read. | Route tests proving write behavior is intentional and documented; redesign notes for GET routes that persist state. | P1 | Medium |
| API-009 | Test-only mutation routes must be environment-gated and unavailable in production-like operation. | Tests/config review proving test routes are only registered or usable in approved test/dev environments. | P0 | Medium |
| API-010 | Mutation and broker-action failures must preserve durable audit state before returning operator-facing errors where practical. The API must not return a clean failure while losing execution/reconciliation/manual-review evidence. | Route/service tests for broker failure, reconciliation failure, runtime failure, and alert/review mutation failure paths. | P1 | Medium |
| API-011 | Routes with unknown frontend consumers must be marked `Needs confirmation` and audited as used, compatibility-only, dev-only, stale, or removable. Unknown consumer status must not be treated as evidence that the route is unused. | Frontend API client/code search and route usage audit. | P2 | Medium |
| API-012 | Operator-visible broker environment and dealing status MUST come from a backend-owned typed contract. Frontend code must not infer environment from URLs, regexes, or fallback literals. Invalid or unavailable broker-environment truth must fail closed visibly. | Typed response model, route tests, frontend type/client tests, and browser coverage for the primary shell status. | P0 | High |

Operator authentication and authorization:

- Production-like environments require named server-side operator credentials.
- The authenticated credential determines `actor_id`; payload/query `actor_id` values are not authoritative.
- Credentials carry `operate`, `deal`, and/or `admin` scopes. Runtime starts require `deal`; control-plane override, reconcile, governance, and test-only mutations require `admin`; ordinary mutations require `operate`.
- Disabled credential records are revoked immediately on configuration reload/restart.
- The legacy shared `OPERATOR_API_TOKEN` is local-development compatibility only and is rejected as the sole production-like credential.
- Internet-facing deployments should replace static credentials with an external OIDC authorization-code flow and short-lived sessions. The scope model remains the backend authorization boundary.

## Route documentation standards

Every route should document:

- Method and path.
- Route file/function.
- Service owner.
- Route classification using the formal categories above.
- Operational side effects, including indirect writes through helper services.
- Broker interaction, if any.
- Lifecycle authority required for mutations or broker actions.
- Frontend consumers, or `Needs confirmation`.
- Response model, OpenAPI schema, or documented dict schema.
- Error status behavior and operator-facing error detail.
- Audit/domain event behavior for mutations.
- Environment restrictions for test-only/dev-only routes.

## Route inventory

This inventory was discovered from `backend/app/api/router.py` and `backend/app/api/routes/*`. Confidence is lower where responses are untyped dicts or indirect side effects were not fully traced. `Needs audit` means the route classification is plausible from route code/name but helper-service side effects have not been mechanically proven.

| Method | Path | Route file/function | Classification | Side-effect notes | Known frontend consumer | Response contract | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `routes/health.py:health_check` | `PASSIVE_READ` | None known | Health/dev checks | Raw dict needs schema | Medium |
| GET | `/health/stream` | `routes/health.py:stream_health_check` | `PASSIVE_READ` | Stream health projection; no writes known | `getStreamHealth` | Pydantic model | High |
| GET | `/system/health` | `routes/health.py:system_health_check` | `PASSIVE_READ` | System health projection; needs write audit | Needs confirmation | Pydantic model | Medium |
| GET | `/system/telemetry` | `routes/health.py:operational_telemetry` | `PASSIVE_READ` | Telemetry projection; needs write audit | `getOperationalTelemetry`, broker status | Pydantic model | Medium |
| GET | `/system/broker-environment` | `routes/health.py:broker_environment_status` | `PASSIVE_READ` | Backend-owned broker environment and dealing-status projection; must not expose credentials, account ids, or raw secrets | `getBrokerEnvironmentStatus` | Pydantic model | High |
| GET | `/system/limits` | `routes/system.py:get_system_operating_limits` | `PASSIVE_READ` | Settings projection | Dashboard/coverage | Pydantic model | High |
| GET | `/broker/positions` | `routes/broker.py:list_broker_positions` | `BROKER_READ` | Reads broker positions; freshness/provenance needs audit | Needs confirmation | Pydantic list model | Medium |
| GET | `/control-plane/summary` | `routes/control_plane.py:get_control_plane_summary` | `PASSIVE_READ` | Projection; default governance/deployment seeding removed and regression-tested; broader indirect write audit still needed | Control plane, dashboard | Pydantic model | Medium |
| GET | `/control-plane/operator-state` | `routes/control_plane.py:get_operator_control_state` | `PASSIVE_READ` | Operator state read; default operator-control seeding removed and regression-tested | Control plane | Pydantic model | High |
| PUT | `/control-plane/operator-state` | `routes/control_plane.py:update_operator_control_state` | `MUTATION` | Updates operator control state | Control plane toggle | Pydantic model | High |
| GET | `/control-plane/strategies/{strategy_name}` | `routes/control_plane.py:get_control_plane_strategy_detail` | `PASSIVE_READ` | Projection; default governance/deployment seeding removed and regression-tested; explicit family contract preserves governance, deployment, runtime, alignment, and open-risk uncertainty | Control plane | `ControlPlaneFamilyResponse` | High |
| POST | `/control-plane/reconcile` | `routes/control_plane.py:reconcile_control_plane` | `MUTATION` | Reconciles control-plane state; may create/update lifecycle evidence | Needs confirmation | `ControlPlaneReconcileResponse` | High |
| PUT | `/control-plane/governance/{strategy_name}` | `routes/control_plane.py:update_strategy_governance` | `MUTATION` | Updates strategy governance | Control plane | `GovernanceMutationResponse` | High |
| GET | `/coverage/summary` | `routes/coverage.py:get_coverage_summary` | `PASSIVE_READ` | Coverage projection; uses passive watchlist plan snapshots without syncing or timestamp writes | Coverage/dashboard | Pydantic model | High |
| GET | `/dashboard` | `routes/dashboard.py:get_dashboard` | `PASSIVE_READ` | Dashboard projection; passive-read route tests now prove no broker-account read and preserve missing broker/runtime/open-risk truth as unavailable rather than healthy defaults | Operate dashboard | `DashboardSnapshotResponse` | High |
| GET | `/events` | `routes/events.py:list_events` | `PASSIVE_READ` | Event read | Events page/live view | Pydantic list model | High |
| GET | `/events/{event_id}` | `routes/events.py:get_event` | `PASSIVE_READ` | Event read | Events detail | Pydantic model | High |
| GET | `/allocation/cycles` | `routes/allocation.py:list_allocation_cycles` | `PASSIVE_READ` | Allocation cycle read | Dashboard/risk | List DTO; schema needs confirmation | High |
| GET | `/allocation/cycles/{cycle_id}` | `routes/allocation.py:get_allocation_cycle` | `PASSIVE_READ` | Allocation cycle read | Risk drawer | Documented dict needed | High |
| GET | `/allocation/intents` | `routes/allocation.py:list_allocation_intents` | `PASSIVE_READ` | Allocation intent read | Dashboard/risk | List DTO; schema needs confirmation | High |
| GET | `/allocation/intents/{trade_intent_id}` | `routes/allocation.py:get_allocation_intent` | `PASSIVE_READ` | Allocation intent read | Risk drawer | Documented dict needed | High |
| GET | `/allocation/drift` | `routes/allocation.py:get_allocation_drift_summary` | `PASSIVE_READ` | Projection; indirect write audit needed | Dashboard/risk | Raw dict needs schema | Medium |
| GET | `/allocation/alerts` | `routes/allocation.py:list_allocation_alerts` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `refresh=true` | Default query is passive; explicit refresh can persist alerts | Dashboard/risk | List DTO; schema needs confirmation | High |
| GET | `/allocation/alerts?refresh=true` | `routes/allocation.py:list_allocation_alerts` | `ACTIVE_READ_REFRESH` | Refreshes persisted alerts | Dashboard/risk | List DTO; schema needs confirmation | Medium |
| POST | `/allocation/alerts/{alert_id}/acknowledge` | `routes/allocation.py:acknowledge_allocation_alert` | `MUTATION` | Acknowledges alert | Risk UI | Documented dict needed | High |
| POST | `/allocation/alerts/{alert_id}/resolve` | `routes/allocation.py:resolve_allocation_alert` | `MUTATION` | Resolves alert | Risk UI | Documented dict needed | High |
| GET | `/allocation/alerts/unresolved-critical` | `routes/allocation.py:list_unresolved_critical_allocation_alerts` | `PASSIVE_READ` | Reads persisted unresolved critical alerts without refresh | Needs confirmation | List DTO; schema needs confirmation | High |
| GET | `/allocation/exposure` | `routes/allocation.py:get_allocation_exposure_summary` | `PASSIVE_READ` | Exposure projection; indirect write audit needed | Dashboard/risk | Raw dict needs schema | Medium |
| GET | `/market-status/{instrument}` | `routes/market_status.py:get_market_status` | `BROKER_READ` | Broker/market status read; freshness/provenance required | Needs confirmation | Pydantic model | Medium |
| GET | `/markets/overview` | `routes/markets.py:get_market_overview` | `BROKER_READ` | Market overview reads broker market details; no local write path documented in the route contract tests | Markets page | `MarketCategoryOverviewResponse` | High |
| GET | `/markets/catalogue` | `routes/markets.py:get_market_catalogue` | `PASSIVE_READ` | Catalogue projection; route contract and passive-read tests show no watchlist sync or timestamp writes | Markets page | `MarketCatalogueResponse` | High |
| GET | `/watchlist/shortlist` | `routes/markets.py:get_shortlist` | `PASSIVE_READ` | Shortlist projection; route contract tests keep shortlist/watchlist state read-only | Markets page | `ShortlistResponse` | High |
| POST | `/watchlist/shortlist/{instrument_id}` | `routes/markets.py:add_shortlist_item` | `MUTATION` | Adds shortlist item | Markets page | `ShortlistMutationResponse` | High |
| DELETE | `/watchlist/shortlist/{instrument_id}` | `routes/markets.py:remove_shortlist_item` | `MUTATION` | Removes shortlist item | Markets page | `ShortlistMutationResponse` | High |
| POST | `/strategy-watchlist/bulk` | `routes/markets.py:add_strategy_watchlist_items` | `MUTATION` | Bulk adds strategy watchlist items | Markets page | `StrategyWatchlistBulkResponse` | High |
| GET | `/strategy-watchlist` | `routes/markets.py:get_strategy_watchlist` | `PASSIVE_READ` | Watchlist read with `sync=false`; route tests prove no watchlist sync or timestamp writes | Markets/coverage | `StrategyWatchlistResponse` | High |
| DELETE | `/strategy-watchlist/{instrument_id}` | `routes/markets.py:remove_strategy_watchlist_item` | `MUTATION` | Removes strategy watchlist item | Markets page | `StrategyWatchlistMutationResponse` | High |
| GET | `/market-data/feed-state` | `routes/markets.py:get_feed_state` | `BROKER_READ` | Feed-state snapshot keeps `sync=false` passive no-write behavior, but per-instrument market readiness may call broker market-status reads | Coverage/markets/live | `FeedStateResponse` | High |
| GET | `/market-data/feed-state/{instrument_id}` | `routes/markets.py:get_instrument_feed_state` | `BROKER_READ` | Instrument feed-state projection exposes streaming/freshness/provenance and degraded market-status detail | Live chart | `FeedStateInstrumentResponse` | High |
| GET | `/live/instruments/{instrument_id}/chart` | `routes/markets.py:get_live_instrument_chart` | `BROKER_READ` | Chart projection can call broker historical candles and market-status reads while preserving feed/chart provenance in the response | Markets/live | `LiveChartResponse` | High |
| GET | `/charts/equity` | `routes/charts.py:get_equity_chart` | `PASSIVE_READ` | Chart projection | Needs confirmation | Raw dict needs schema | Medium |
| GET | `/charts/drawdown` | `routes/charts.py:get_drawdown_chart` | `PASSIVE_READ` | Chart projection | Needs confirmation | Raw dict needs schema | Medium |
| GET | `/charts/risk-allocation` | `routes/charts.py:get_risk_allocation_chart` | `PASSIVE_READ` | Chart projection; explicit contract now preserves unavailable/degraded/provisional/simulated/unknown risk truth, exposes generated/source/reason metadata, and refuses zero-default substitution when risk cannot be charted safely | Typed client boundary only; no active page/component caller confirmed in repo search | `RiskAllocationChartResponse` | High |
| GET | `/positions` | `routes/positions.py:list_positions` | `PASSIVE_READ` | Local open-position read; explicit contract preserves broker sync provenance, close provenance, risk confidence, and derived time-in-trade fields | Needs confirmation/compat | `list[OpenPositionResponse]` | High |
| GET | `/executions` | `routes/executions.py:list_executions` | `PASSIVE_READ` | Execution read | Dashboard/strategies | Pydantic list model | High |
| GET | `/trades` | `routes/trades.py:list_trades` | `PASSIVE_READ` | Trade read; explicit contract preserves close provenance, risk confidence, and entry-risk fields consumed by operator surfaces | Dashboard | `list[TradeResponse]` | High |
| GET | `/trades/positions` | `routes/trades.py:list_positions_compat` | `PASSIVE_READ` | Compatibility positions read; shared contract with `/positions` keeps simulated/broker/unknown sync truth explicit instead of route-local raw dict drift | Dashboard | `list[OpenPositionResponse]` | High |
| GET | `/strategies` | `routes/strategies.py:list_strategies` | `PASSIVE_READ` | Strategy projection; default governance seeding removed and regression-tested; explicit schema now preserves deployment, runtime, persisted-runtime, and authorization/open-risk-adjacent fields used by the operator UI | Strategies page | `list[StrategySummaryResponse]` | High |
| POST | `/strategy/start` | `routes/strategies.py:start_strategy` | `MUTATION` | Starts runtime; mutation response now preserves explicit strategy/runtime status fields used by the UI | Strategies page | `StrategyMutationStatusResponse` | High |
| POST | `/strategy/stop` | `routes/strategies.py:stop_strategy` | `MUTATION` | Stops runtime; mutation response now preserves explicit strategy/runtime status fields used by the UI | Strategies page | `StrategyMutationStatusResponse` | High |
| POST | `/strategies/{name}/start` | `routes/strategies.py:start_strategy_by_name` | `MUTATION` | Starts runtime by name | Needs confirmation/compat | `StrategyMutationStatusResponse` | High |
| POST | `/strategies/{name}/stop` | `routes/strategies.py:stop_strategy_by_name` | `MUTATION` | Stops runtime by name | Needs confirmation/compat | `StrategyMutationStatusResponse` | High |
| GET | `/aimee/snapshot` | `routes/aimee.py:get_snapshot` | `PASSIVE_READ` | Passive AIMEE snapshot; must not persist/reconcile/sync | AIMEE drawer | Raw dict needs schema | High |
| GET | `/reviews/operator-summary` | `routes/ai_reviewer.py:get_operator_summary` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `persist=true` | Default preview does not persist; explicit `persist=true` creates `GeneratedReviewRecord` | Reviewer/AIMEE | Pydantic model | High |
| GET | `/reviews/daily` | `routes/ai_reviewer.py:get_daily_review` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `persist=true` | Default preview does not persist; explicit `persist=true` creates `GeneratedReviewRecord` | Needs confirmation | Pydantic model | High |
| GET | `/reviews/strategies/{strategy_name}` | `routes/ai_reviewer.py:get_strategy_review` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `persist=true` | Default preview does not persist; explicit `persist=true` creates `GeneratedReviewRecord` | Needs confirmation | Pydantic model | High |
| GET | `/reviews/runtime-health` | `routes/ai_reviewer.py:get_runtime_health_review` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `persist=true` | Default preview does not persist; explicit `persist=true` creates `GeneratedReviewRecord` | Needs confirmation | Pydantic model | High |
| GET | `/reviews/trades/{trade_id}/postmortem` | `routes/ai_reviewer.py:get_trade_postmortem` | `PASSIVE_READ` by default; `ACTIVE_READ_REFRESH` when `persist=true` | Default preview does not persist; explicit `persist=true` creates `GeneratedReviewRecord` | Needs confirmation | Pydantic model | High |
| POST | `/reviews/questions` | `routes/ai_reviewer.py:answer_operational_question` | `MUTATION` | Persists requested advisory artifact | AIMEE/reviewer | Pydantic model | High |
| GET | `/reviews/history` | `routes/ai_reviewer.py:list_review_history` | `PASSIVE_READ` | Review history read | AIMEE/reviewer | Pydantic list model | High |
| GET | `/reviews/history/{review_id}` | `routes/ai_reviewer.py:get_review_record` | `PASSIVE_READ` | Review record read | Reviewer | Pydantic model | High |
| POST | `/testing/reset-history` | `routes/testing.py:reset_history` | `TEST_ONLY_MUTATION` | Registered only when `TESTING_ROUTES_ENABLED=true`; clears persisted test history when enabled | Events testing button when `NEXT_PUBLIC_TESTING_CONTROLS_ENABLED=true` | Pydantic model | High |

## Write-on-read exceptions and redesign candidates

The following routes are not passive reads even though they use GET or read-like naming:

| Route | Current behavior | Required classification | Preferred future direction |
| --- | --- | --- | --- |
| `GET /reviews/operator-summary?persist=true` | Explicitly persists `GeneratedReviewRecord`. | `ACTIVE_READ_REFRESH` | Prefer POST persistence long term if review archival becomes an operator workflow. |
| `GET /reviews/daily?persist=true` | Explicitly persists `GeneratedReviewRecord`. | `ACTIVE_READ_REFRESH` | Same as above. |
| `GET /reviews/strategies/{strategy_name}?persist=true` | Explicitly persists `GeneratedReviewRecord`. | `ACTIVE_READ_REFRESH` | Same as above. |
| `GET /reviews/runtime-health?persist=true` | Explicitly persists `GeneratedReviewRecord`. | `ACTIVE_READ_REFRESH` | Same as above. |
| `GET /reviews/trades/{trade_id}/postmortem?persist=true` | Explicitly persists `GeneratedReviewRecord`. | `ACTIVE_READ_REFRESH` | Same as above. |
| `GET /allocation/alerts?refresh=true` | Can refresh persisted alerts. | `ACTIVE_READ_REFRESH` | Prefer POST refresh or separate mutation endpoint. |

## Side-effect rules

- `PASSIVE_READ` routes must be side-effect free.
- GET routes must not mutate operational state unless explicitly classified as `ACTIVE_READ_REFRESH` and documented as a write-on-read exception.
- GET routes must not call broker mutation paths.
- Passive routes must not perform reconciliation, runtime start/stop, governance default seeding, watchlist sync, alert refresh, review persistence, event creation, or database commit/flush.
- Any unavoidable read-triggered write must be downgraded from `PASSIVE_READ` classification and receive behavioral tests.
- Query parameters such as `refresh=true`, `persist=true`, or `reconcile=true` must be treated as mutation-like when they can write durable state.
- Frontend UI copy must not present mutation-like routes as harmless refreshes when they can persist or alter operational state.

## Error handling expectations

- Operator mutation failures should return `HTTPException` or equivalent structured error responses with useful `detail`.
- Broker/reconciliation/order errors must preserve audit state before surfacing failure where practical.
- Broker confirmation ambiguity must surface as pending/manual-review/reconciliation-needed rather than silent success or silent failure.
- Frontend callers must not silently swallow mutation or broker-action errors.
- Error responses for operator-critical actions should include enough context for the UI to explain what failed, what state was preserved, and what the operator should check next.
- Error payloads must not leak broker secrets, session tokens, or sensitive raw adapter internals.

## Frontend contract rules

Frontend-consumed route fields must be treated as part of the API contract.

- Operator-critical fields should come from typed backend response models, documented dict schemas, or explicit frontend contract tests.
- Frontend code must not infer lifecycle truth, broker truth, risk confidence, market-data freshness, or approval state when backend fields are absent.
- Compatibility routes consumed by the frontend must be labelled as compatibility routes and given a migration/removal note where appropriate.
- Unknown frontend consumers must be audited through `frontend/lib/api.ts`, `frontend/lib/types.ts`, page loaders, and component imports.

## Test-only route boundary

Routes under `/testing/*` are mutation-capable and must be treated as `TEST_ONLY_MUTATION`.

They must be unavailable in production-like operation unless explicitly protected by environment configuration, authentication, or other safeguards. The current `/testing/reset-history` route is not registered unless `TESTING_ROUTES_ENABLED=true`, the app is in a local/test posture, and live dealing is not enabled. The frontend reset control/API helper are separately gated by `NEXT_PUBLIC_TESTING_CONTROLS_ENABLED=true`. Test-only route use in frontend development tools must not normalize unsafe reset/destructive actions as operator features.

## Known unknowns

- Route classification has not yet been mechanically checked against every registered FastAPI route.
- Some `PASSIVE_READ` or projection-labelled routes may call services that seed defaults, refresh alerts, reconcile broker state, create events, or commit/flush indirectly.
- Response contract status is unclear for many raw dict responses consumed by frontend components.
- Unknown frontend consumer status requires code search before treating routes as unused.
- `/reviews/*` GET persistence now requires explicit `persist=true`; a future API redesign may still move archival persistence to POST.
- `/allocation/alerts?refresh=true` may need to move to POST or a clearly mutation-classified endpoint.
- `GET /allocation/alerts` now defaults to passive `refresh=false`; explicit `refresh=true` remains mutation-like and tested.
- Test-only route gating currently has router-registration regression evidence for `/testing/reset-history`; broader HTTP route harness evidence is still missing.
- Many dict responses lack Pydantic response models.

## Required tests

- Route inventory test or review checklist comparing registered FastAPI routes to this spec.
- Route-level tests proving `PASSIVE_READ` routes do not write, flush, commit, seed defaults, reconcile broker state, refresh alerts, create events, persist reviews, or mutate runtime/broker state.
- Tests proving `ACTIVE_READ_REFRESH` routes have intentional documented side effects.
- Tests proving `/reviews/*` default previews do not write and `persist=true` active reads intentionally persist review records.
- Tests proving `GET /allocation/alerts` default behavior is passive and `refresh=true` behavior is classified/tested as mutation-like, or migrated to POST.
- Tests proving broker mutation routes require lifecycle authority and preserve audit state.
- Tests proving test-only routes are unavailable in production-like operation.
- Frontend contract tests for operator-critical fields in `frontend/lib/types.ts`, `frontend/lib/api.ts`, and critical dashboard/control-plane/risk/coverage/AIMEE surfaces.
- Route-level tests for mutation side effects, audit preservation, structured errors, and frontend-visible error detail.

## Audit questions for Codex

- Does the route inventory exactly match all registered FastAPI routes?
- Which routes currently labelled read/projection call services that can write indirectly?
- Which GET routes can persist reviews, refresh alerts, reconcile broker state, seed defaults, create events, or commit/flush?
- Which routes should be reclassified as `ACTIVE_READ_REFRESH` rather than `PASSIVE_READ`?
- Should `/reviews/*` GET endpoints be split into passive preview and explicit POST persistence endpoints?
- Should `/allocation/alerts?refresh=true` move to POST?
- Which raw dict responses are consumed by frontend operator-critical surfaces without typed or documented contracts?
- Which routes marked with unknown frontend consumer are actually used, compatibility-only, dev-only, stale, or removable?
- Are `/testing/*` routes gated away from production-like operation?
- Can any API route trigger broker mutation without approved intent, known open risk, recovery/reconciliation authority, or explicit operator action?
# Historical data and backtest routes

The typed route inventory includes:

- `GET /historical-data/providers` and `GET /historical-data/providers/{provider_id}` as passive capability reads.
- `POST /historical-data/imports` and `POST /historical-data/imports/csv` as explicit ingestion mutations.
- `GET /historical-data/imports/{dataset_id}`, `GET /historical-data/datasets`, and `GET /historical-data/datasets/{dataset_id}` as passive provenance/coverage reads.
- `POST /backtests` as a bounded synchronous simulation mutation.
- `GET /backtests` and the run configuration, metrics, trades, equity, warnings, and instrument routes as passive reads.

A backtest references an immutable dataset ID and checksum. It never accepts a provider/date range as a replay source.
