# Frontend operator UI contract

The frontend is an operator console. It must help a human supervise autonomous trading without overstating confidence, hiding degraded states, or triggering mutations from passive surfaces.

## UI terminology

- Authoritative backend truth: lifecycle, broker, risk, runtime, governance, deployment, execution, position, or market-data state supplied directly by backend response fields.
- Frontend-derived view: a presentation summary or grouping computed locally from backend resources. It may help explain state but must not invent lifecycle truth, confidence, approval, broker state, freshness, or risk certainty.
- Provenance: visible or inspectable information explaining where a value came from, when it was observed, how fresh it is, and how much confidence the operator should place in it.
- Passive surface: a dashboard, read model, drawer, page, or component whose purpose is observation only.
- Mutation control: a UI element that intentionally changes backend, broker, runtime, governance, watchlist, alert, testing, review, or operational state.
- Operator-critical field: any field that can affect operator confidence, trading permission, open-risk handling, market-data freshness, broker state, allocation/risk exposure, execution status, or governance/deployment/runtime interpretation.

## UI invariants

| Spec ID | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- |
| UI-001 | Every operator-critical field MUST expose provenance where applicable: backend source, timestamp/age/freshness, confidence, fallback/degraded status, derived-vs-authoritative status, or unknown/unavailable state. | Component tests and visible/inspectable fields for dashboard/risk/coverage/control-plane/live/AIMEE surfaces. | P1 | Low |
| UI-002 | Degraded, stale, estimated, simulated, fallback, unavailable, unknown, partial, or provisional backend truth MUST NOT be styled or labelled as exact, healthy, live, approved, broker-confirmed, or final. | Risk truth, fallback, stale, unavailable, simulated, partial-fill, and provisional states render distinctly. | P1 | Medium |
| UI-003 | Passive dashboards and passive drawers MUST NOT call mutation endpoints or import mutation API functions except through explicit mutation controls. | Page/component/API-client tests proving passive surfaces call passive read APIs only. | P1 | Medium |
| UI-004 | Operator controls MUST make side effects clear before and during action, including label, confirmation where destructive/high-risk, pending state, disabled reason, success state, error state, and refreshed backend truth after completion. | Control-plane, strategy, watchlist, alert, governance, emergency-stop, and testing reset controls. | P1 | Medium |
| UI-005 | Frontend enum/status labels MUST match backend semantics. Missing backend enum states must render as explicit unknown/unsupported states rather than being collapsed into healthy/default states. | Type definitions, mapping tests, fixture coverage for every backend enum state, and unknown-state rendering tests. | P1 | Medium |
| UI-006 | Frontend API client MUST preserve backend error `detail` and operator-relevant failure context for mutation and broker-action errors. Components must not silently swallow or replace these errors with generic success/failure copy. | `HttpError` handling, API-client tests, and component error display tests. | P1 | Medium |
| UI-007 | Frontend-derived views may summarize backend resources, but MUST NOT invent or upgrade lifecycle truth, broker truth, risk confidence, market-data freshness, governance approval, deployment/runtime alignment, or entry/exit eligibility. | Tests for derived summaries in live view, dashboard, risk, coverage, and control-plane components. | P1 | Low |
| UI-008 | Frontend fallback/default objects must be visibly marked as unavailable, loading, stale, error, or degraded. They must never be rendered as healthy backend truth. | API-client fallback tests and component tests for timeout/error/default data paths. | P1 | Medium |
| UI-009 | Test-only or destructive controls must be clearly labelled, environment-gated, and unavailable in production-like operation. They must not be presented as normal operator features. | Tests/config review for testing reset button and any `/testing/*` consumers. | P0 | Medium |
| UI-010 | AIMEE passive refresh MUST use passive read endpoints only. Explicit advisory actions that may persist review artifacts must be visually and technically separated from passive snapshot refresh. | API-client/component tests proving passive refresh calls `/aimee/snapshot` only and advisory persistence uses explicit user action. | P1 | Medium |
| UI-011 | Market-data, broker, stream, risk, allocation, execution, and runtime displays should show timestamp, age, or freshness state when stale data could change operator interpretation. Absence of freshness must render as unknown/degraded, not fresh. | Component tests for missing timestamp, stale timestamp, fallback timestamp, and fresh timestamp fixtures. | P1 | Low |
| UI-012 | Safety-critical status must not rely on color alone. Badges, icons, labels, tooltips, or text must make degraded, blocked, stale, fallback, manual-review, and unmanaged-risk states clear without color dependence. | Component/a11y tests or screenshot review for safety-critical statuses. | P2 | Low |
| UI-013 | Global environment and dealing status MUST come from backend-owned truth. The shell/navigation must not infer DEMO/LIVE from URLs, regexes, or hardcoded fallbacks, and unknown or invalid broker-environment status must render as degraded/blocking. | Frontend type/API-client tests plus browser coverage for global shell status states. | P0 | High |

For UI-001, "operator-critical field" means a field that could affect operator confidence, trading permission, open-risk handling, market-data freshness, broker state, allocation/risk exposure, execution status, or governance/deployment/runtime interpretation.

## Current frontend evidence

| Surface | Files | Current role |
| --- | --- | --- |
| Operate/dashboard | `frontend/app/page.tsx`, `frontend/components/dashboard/*` | Aggregates positions, trades, executions, broker status, stream health, coverage, control-plane, allocation. |
| Live view | `frontend/app/live/page.tsx`, `frontend/components/live/live-system-view.tsx`, `frontend/lib/live-system-view.ts` | Synthesizes live operational view from strategies/coverage/events/positions. |
| Control plane | `frontend/app/control-plane/page.tsx`, `frontend/components/control-plane/control-plane-live.tsx` | Governance updates, operator override, deployment/runtime alignment. |
| Risk/allocation | `frontend/app/risk/page.tsx`, `frontend/components/risk/*`, `frontend/lib/risk-allocation.ts` | Allocation cycles, intents, exposure, alerts, risk context. |
| Coverage/watchlist | `frontend/app/coverage/page.tsx`, `frontend/components/coverage/*` | Tier 1/Tier 2 coverage, feed state, promotion/allocator summaries. |
| Markets | `frontend/app/markets/page.tsx`, `frontend/components/markets/*` | Market overview, catalogue, watchlist actions, feed/chart state. |
| Events | `frontend/app/events/page.tsx` | Domain event timeline and testing reset button. |
| Strategies | `frontend/app/strategies/page.tsx`, `frontend/components/strategy/*` | Strategy registry, runtimes, manual start/stop, executions. |
| AIMEE | `frontend/components/aimee/*` | Passive drawer/shell consuming `/aimee/snapshot` and review data. |

## Frontend API client expectations

`frontend/lib/api.ts` is the contract boundary. It must:

- Use backend routes exactly as documented in `04-backend-api-contract.md`.
- Keep mutation functions explicit by name (`startStrategy`, `stopStrategy`, `updateOperatorControlState`, `updateStrategyGovernance`, alert acknowledge/resolve, watchlist mutations).
- Preserve backend error `detail` for operator actions.
- Use timeouts appropriate to market/broker reads without hiding stale data as healthy.
- Keep fallback objects visually marked as unavailable/error, not healthy defaults.
- Keep passive read functions and mutation functions clearly separated by naming and import boundaries.
- Do not allow passive pages/drawers to import mutation functions unless those functions are only passed into explicit mutation controls.
- Preserve route classification from `04-backend-api-contract.md`, especially `PASSIVE_READ`, `ACTIVE_READ_REFRESH`, `MUTATION`, `BROKER_READ`, `BROKER_MUTATION`, and `TEST_ONLY_MUTATION` if those categories exist.
- Surface timeout/error/fallback state to components rather than converting failures into healthy defaults.
- Preserve backend enum values even when the UI label is friendlier; never collapse unknown enum values into healthy/default states.

## Provenance display rules

Operator-critical displays should expose, where applicable:

- backend source or endpoint;
- authoritative vs frontend-derived status;
- timestamp, age, freshness, or last-updated value;
- confidence/provenance label such as exact, estimated, provisional, fallback, simulated, broker-confirmed, submitted, allocation-only, unknown, or degraded;
- unavailable/error state when backend fields are missing or requests fail;
- tooltip/detail text explaining why a field is degraded, blocked, estimated, or unknown.

Missing provenance must not be silently treated as exact truth.

## Frontend-derived view rules

Frontend-derived summaries are allowed for operator usability, especially on the dashboard and live view, but they must obey these rules:

- Derived fields must be labelled or inspectable as derived when they combine multiple backend resources.
- Derived fields must not override backend lifecycle states.
- Derived labels must not imply stronger certainty than the weakest relevant backend source.
- Derived health, risk, coverage, or control-plane summaries must preserve degraded, stale, fallback, unknown, manual-review, and unmanaged-risk states.
- Derived values must be deterministic and traceable to backend response fields.

## Status and confidence display

Status badges must distinguish:

- `DEMO · DEALING DISABLED`, `DEMO · DEALING ENABLED`, `LIVE · DEALING DISABLED`, `LIVE · DEALING ENABLED`, `ENVIRONMENT UNKNOWN`, and `CONFIGURATION INVALID`.
- Healthy live stream vs polling fallback vs stale vs disconnected.
- Broker connected vs disconnected vs unavailable.
- `APPROVED` governance vs deployed vs running runtime.
- `AUTO` vs `MANUAL` control mode.
- `NORMAL` vs `EXITS_ONLY` vs `STOPPED` runtime mode.
- Estimated allocation risk vs submitted risk vs fill-derived risk vs partial-fill provisional risk.
- Open-risk management `MANAGED`, `EXITS_ONLY`, `UNMANAGED_OPEN_RISK`, and `NO_OPEN_RISK`.
- Backend authoritative status vs frontend-derived summary.
- Fresh timestamp vs stale timestamp vs missing timestamp.
- Broker-confirmed vs simulated/local trading result.
- Pending/ambiguous broker confirmation vs confirmed success/failure.
- Manual review vs normal failure.
- Entry eligibility vs market tradability vs streaming coverage.
- Unknown/unsupported backend enum state.

## Mutation controls

Controls with operational side effects include:

- Strategy start/stop.
- Operator autonomous-control override.
- Governance updates and emergency stop.
- Watchlist/shortlist add/remove.
- Allocation alert acknowledge/resolve.
- Testing history reset.

These controls must show side effects through labels, disabled reasons, confirmation where appropriate, pending state, success state, error state, and refreshed backend truth after completion. Failed mutations must leave the operator with visible failure context and must not optimistically display success unless the backend confirms it.

Passive surfaces must not hide mutation controls inside auto-refresh, passive polling, passive drawer open, page load, or hover/preview behavior.

## Surface-specific requirements

| Spec ID | Surface | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- | --- |
| UI-OPERATE-001 | Operate/dashboard | Must summarize broker, stream, risk, execution, coverage, and control-plane truth without treating fallback, stale, unavailable, simulated, or estimated data as healthy/exact. | Component/e2e tests for healthy, fallback, stale, broker unavailable, allocation degraded, simulated result, and unknown enum states. | P1 | Medium |
| UI-LIVE-001 | Live view | Must label synthesized frontend groupings as frontend-derived and preserve degraded/fallback/stale/unknown/manual-review states from source resources. | Tests or screenshots showing derived fields cannot be mistaken for backend authoritative fields and do not upgrade weak source states. | P1 | Low |
| UI-CONTROL-001 | Control plane | Must separate governance, deployment, runtime, alignment, operator override, emergency stop, open-risk management, and operational-state fields. | Component tests for mismatched deployment/runtime, emergency stop, manual override, unmanaged open risk, and exits-only states. | P1 | Medium |
| UI-RISK-001 | Risk/allocation | Must display risk truth confidence/provenance and distinguish reserved, live, submitted, exact fill-derived, broker-confirmed estimated, partial-fill provisional, simulated, allocation-only, unknown, and degraded risk. | Component tests for each risk confidence/provenance fixture. | P1 | Medium |
| UI-COVERAGE-001 | Coverage/watchlist | Must distinguish desired coverage, active streaming, capped-out instruments, pinned/protective coverage, fallback polling, stale feed, Tier 2 refresh, promotion candidates, and entry eligibility. | Component tests using feed-state and coverage fixtures for each distinction. | P1 | Medium |
| UI-MARKETS-001 | Markets | Must not imply shortlist, strategy watchlist, market tradability, or price availability means streaming coverage, governance approval, risk admission, or trading approval. | Component tests for shortlist-only, watchlist-but-not-streaming, tradable-but-not-approved, and price-present-but-entry-blocked instruments. | P1 | Medium |
| UI-EVENTS-001 | Events | Must preserve event type, category, severity, correlation fields, lifecycle references, timestamps, and degraded/manual-review/recovery context for audit. Testing reset control must be clearly test-only and environment-gated. | Component tests for event filters/detail rendering and test-only reset visibility. | P1 | Medium |
| UI-STRATEGY-001 | Strategies | Manual start/stop must not imply governance approval, autonomous ownership, deployment alignment, or entry eligibility. Runtime mode, control mode, open-risk state, and authorization must remain visible. | Component tests for manual runtime, auto runtime, unauthorized strategy, exits-only runtime, unmanaged/open-risk state, and deployment/runtime mismatch. | P1 | Medium |
| UI-AIMEE-001 | AIMEE | Passive refresh must call read-only endpoints only, avoid mutation controls in passive snapshot, and clearly separate passive explanation from explicit advisory persistence. | API/client tests proving passive refresh calls `/aimee/snapshot` only and advisory persistence requires explicit user action. | P1 | Medium |

## Must-not-cross UI boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| UI-BND-001 | UI vs backend truth | Frontend must not infer or upgrade lifecycle, broker, risk, approval, freshness, or confidence truth beyond backend fields. | Mapping and component fixture tests. | P1 |
| UI-BND-002 | Passive vs mutation | Passive pages, dashboards, drawers, and auto-refresh flows must not call mutation APIs. | API import/call graph tests or review. | P1 |
| UI-BND-003 | Derived vs authoritative | Frontend-derived summaries must be labelled/inspectable and must preserve degraded/unknown source state. | Live/dashboard derivation tests. | P1 |
| UI-BND-004 | Fallback vs healthy | API fallback/default/error objects must not render as healthy backend truth. | API-client and component tests. | P1 |
| UI-BND-005 | Enum parity | Missing or unknown backend enum states must not collapse into healthy/default UI states. | Type/mapping tests. | P1 |
| UI-BND-006 | Test-only controls | Testing/destructive controls must be environment-gated and clearly labelled. | Config/component tests. | P0 |
| UI-BND-007 | AIMEE passive safety | AIMEE passive refresh must remain read-only and separate from advisory persistence. | API-client/component tests. | P1 |
| UI-BND-008 | Broker environment truth | Frontend must not infer broker environment or dealing truth from URL strings, regexes, or hardcoded DEMO/LIVE defaults. | API-client/type/browser tests. | P0 |

## Known unknowns

- Frontend unit-style Node tests and Playwright E2E tests exist, but new operator-critical surfaces must continue adding degraded, unknown, stale, and mutation-failure evidence.
- `ExecutionStatus` currently includes `SUBMISSION_PENDING`, and shared parity tests cover the reviewed backend/frontend vocabulary family. Future enum additions still require parity updates.
- Data provenance is partly implicit; not every displayed metric clearly shows source/freshness/confidence.
- `getBrokerAuthStatus` derives broker status from telemetry rather than `/broker/positions`; this is acceptable only if labeled as derived telemetry.
- Whether passive pages/drawers import mutation API functions indirectly through shared hooks or utility modules.
- Whether all API fallback/default objects are visually marked as unavailable/error/degraded rather than rendered as healthy defaults.
- Whether all backend enum values are represented in frontend types and mapping functions, including lifecycle, execution, runtime, governance, deployment, allocation, alert, event, and coverage states.
- Whether unknown backend enum values render as explicit unknown/unsupported states.
- Whether frontend-derived live/dashboard summaries preserve the weakest relevant backend confidence/provenance.
- Whether testing reset controls are gated away from production-like operation.
- Whether AIMEE passive refresh is technically isolated from review/advisory persistence endpoints.
- Whether all operator-critical fields expose enough timestamp/freshness/provenance for safe interpretation.

## Required tests

- Component tests for loading/error/empty/stale/degraded states on dashboard, control plane, coverage, risk, markets, strategies, and AIMEE.
- API client contract tests for critical response fields.
- Tests proving passive dashboard/AIMEE surfaces do not call mutation functions.
- Status-label tests comparing frontend labels to backend enum semantics.
- Component tests for operator-critical fields proving provenance/freshness/confidence is visible or inspectable.
- API-client tests proving fallback/default/error objects are marked degraded/unavailable and not healthy.
- Import/call graph tests or review checklist proving passive pages and AIMEE passive refresh do not import/call mutation API functions.
- Enum parity tests comparing backend enum values or documented fixtures against `frontend/lib/types.ts` and UI mapping functions.
- Unknown enum rendering tests proving unsupported backend states render as unknown/unsupported rather than healthy/default.
- Derived-summary tests proving live view/dashboard summaries preserve degraded, fallback, stale, manual-review, unknown, and unmanaged-risk states.
- Mutation-control tests for labels, disabled reasons, pending state, success state, backend error display, and refreshed truth after completion.
- Test-only control tests proving testing reset is hidden or disabled outside approved dev/test environments.
- AIMEE tests proving passive snapshot refresh calls `/aimee/snapshot` only and advisory persistence requires explicit user action.
- Accessibility/screenshot tests proving safety-critical states are not communicated by color alone.

## Audit questions for Codex

- Which passive pages, drawers, hooks, or utility modules import mutation API functions?
- Do API fallback/default objects ever render as healthy, connected, exact, approved, or broker-confirmed truth?
- Are all backend enum states represented in `frontend/lib/types.ts` and UI mapping functions?
- What happens when the backend returns an unknown enum value?
- Does any frontend-derived live/dashboard/control-plane/risk summary upgrade stale/fallback/unknown/provisional source data into healthy/exact state?
- Do mutation controls show clear labels, disabled reasons, pending state, error detail, and refreshed backend truth?
- Are backend `HttpError.detail` values preserved and displayed for operator actions?
- Is the testing reset button environment-gated and clearly labelled as test-only?
- Does AIMEE passive refresh call only `/aimee/snapshot`, and are review/advisory persistence calls isolated behind explicit user action?
- Does any component imply shortlist, watchlist, tradability, price availability, streaming coverage, governance approval, or risk admission are equivalent?
- Does any component communicate safety-critical state by color alone?
# Backtesting operator truth

`/backtests` is a simulation surface, not a live trading surface. It must display:

- immutable dataset ID, provider, venue, market type, checksum, coverage, gaps, and components;
- provider credential availability without treating optional credentials as system failure;
- run status and persisted failure reason;
- evaluation boundary, pricing mode, sizing, spread, slippage, fees, and end treatment;
- synthetic-spread and conservative-intracandle warnings;
- Binance spot venue specificity;
- explicit one-minute candle and non-tick-level limitations.

Backtest trades must never be styled or labelled as broker-confirmed executions.
