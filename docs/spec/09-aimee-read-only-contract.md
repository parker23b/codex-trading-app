# AIMEE read-only contract

AIMEE is a read-only operator companion for passive snapshots. It may explain system state, but passive refresh must not mutate operational state or broker state.

## Current implementation evidence

| Area | Evidence | Current verification confidence |
| --- | --- | --- |
| Passive route | `backend/app/api/routes/aimee.py` exposes `GET /aimee/snapshot`. | High |
| Passive service | `backend/app/services/aimee_read_service.py` explicitly documents side-effect-free intent. | High |
| Review interaction | Passive snapshot calls `AIReviewerService.get_operator_summary(persist=False)`. | High |
| Tests | `backend/tests/test_aimee_read_service.py` checks no review rows, no reconciliation/default seeding/watchlist planning calls, and advisory persistence behavior. | High |
| Frontend | `frontend/components/aimee/*`, `frontend/lib/api.ts:getAimeeSnapshot`. | Medium |

## AIMEE purpose

AIMEE should help the operator understand:

- Current review summary.
- Recent review history.
- Control-plane state.
- Coverage state.
- Operational telemetry.
- Recent events.
- Strategy warnings/status.

AIMEE passive reads are explanation and orientation only. They are not command execution. AIMEE should explain and orient. It must not operate the system through passive reads. Any future operator command capability must be specified separately as explicit user-triggered mutation behavior with route classification, audit evidence, permissions, and UI confirmation. AIMEE explanations should preserve backend confidence/provenance rather than rewriting degraded state as healthy prose.

## AIMEE terminology

- Passive snapshot: the read-only response returned by `GET /aimee/snapshot` for AIMEE orientation and explanation.
- Passive refresh: frontend/API-client action that updates AIMEE passive snapshot state without user-requested advisory persistence.
- Explicit advisory action: a user-triggered question or review request that may persist a requested advisory artifact through an explicit mutation endpoint.
- Mutation: any durable state change or operational side effect, including `session.add`, `session.delete`, `session.commit`, `session.flush`, default seeding, reconciliation, alert refresh, event creation, runtime start/stop, watchlist sync, broker order submission, broker close, or review persistence.
- Passive explanation: AIMEE text or UI that explains backend-provided state without changing that state or implying stronger certainty than backend data supports.
- AIMEE response contract: the backend schema or documented dict shape consumed by frontend AIMEE components.

## Route classification

- `GET /aimee/snapshot` must be classified as `PASSIVE_READ`.
- `POST /reviews/questions` is an explicit `MUTATION` for user-requested advisory persistence.
- `GET /reviews/history` and `GET /reviews/history/{review_id}` are passive review-history reads if they do not write.
- Mutation-like `/reviews/*` GET calls with `persist=true` must not be used by passive AIMEE refresh.

If exact route classification differs in `04-backend-api-contract.md`, that needs audit rather than invented certainty.

## Invariants

| Spec ID | Requirement | Required code evidence | Required test evidence | Severity |
| --- | --- | --- | --- | --- |
| AIMEE-001 | Passive AIMEE snapshot MUST NOT mutate state directly or indirectly. This includes database writes, commits, flushes, default seeding, reconciliation, alert refresh, event creation, watchlist sync, runtime mutation, broker mutation, and review persistence. | `AimeeReadService.get_snapshot` uses read queries and `persist=False` paths only. | Route/service tests comparing before/after operational rows and monkeypatch tests for forbidden side-effect services. | P1 |
| AIMEE-002 | Passive AIMEE reads MUST NOT create `GeneratedReviewRecord` rows or other advisory persistence. Review summaries used in passive snapshot must call reviewer paths with persistence disabled. | `get_operator_summary(persist=False)` or equivalent explicit non-persisting path. | `test_aimee_snapshot_route_is_side_effect_free` and regression tests for review row counts. | P1 |
| AIMEE-003 | Passive AIMEE reads MUST NOT trigger broker/local reconciliation, position adoption, forced-close logic, recovery, or broker truth mutation. | No calls to `BrokerService.reconcile_positions`, `ReconciliationService.reconcile_open_positions`, `RuntimeRecoveryService` recovery workflows, or forced-close paths. | Monkeypatch tests fail if reconciliation/recovery services are called from passive snapshot. | P0 |
| AIMEE-004 | Passive AIMEE reads MUST NOT seed governance defaults or create/update governance, deployment, runtime, watchlist, alert, review, event, trade, intent, execution, or position rows. | No `ensure_defaults` or write-capable service calls in AIMEE read path. | Monkeypatch and row-count tests fail if default seeding or writes occur. | P1 |
| AIMEE-005 | Passive AIMEE reads MUST NOT sync watchlists, recompute streaming plans with side effects, create promotion requests, mutate coverage state, or sync streaming subscriptions. Direct read queries and local read-model computation are allowed. | Uses direct read queries and side-effect-free projections only. | Monkeypatch tests fail if streaming/tier2 plan mutation, watchlist sync, or subscription sync paths are called. | P1 |
| AIMEE-006 | Passive AIMEE reads MUST NOT call broker mutation paths or broker-side order/close functions. Broker reads should also be avoided unless explicitly documented as read-only, freshness-aware, and side-effect-free. | No `place_order`, `close_position`, broker mutation service, or broker reconciliation call in passive snapshot. | Tests fail if broker mutation functions or reconciliation-triggering broker calls are invoked. | P0 |
| AIMEE-007 | Explicit advisory/question endpoints may persist only the user-requested advisory artifact and must not perform broker, runtime, governance, reconciliation, watchlist, alert-refresh, or operational side effects. | `POST /reviews/questions` uses explicit user-triggered mutation path and bounded persistence. | Test proves only the requested review/advisory row is created and forbidden side effects do not occur. | P1 |
| AIMEE-008 | Frontend AIMEE passive refresh MUST call passive read endpoints only. Passive AIMEE components/hooks must not import or call mutation API functions except through visually explicit user-triggered advisory controls. | `getAimeeSnapshot` calls `GET /aimee/snapshot`; passive hooks/components do not call `POST /reviews/questions` or mutation-like `/reviews/*` GET endpoints automatically. | Frontend/API-client tests or import/call graph review. | P1 |
| AIMEE-009 | AIMEE snapshot response fields consumed by the frontend MUST be modeled by a backend response model or documented dict schema, and synchronized with frontend types/API client assumptions. | Pydantic response model, documented schema, OpenAPI contract, or explicit frontend contract tests. | Contract test for AIMEE response fields used by frontend. | P1 |
| AIMEE-010 | AIMEE explanations MUST NOT upgrade backend truth. Stale, fallback, estimated, provisional, unknown, simulated, disconnected, blocked, manual-review, or degraded backend states must remain visible in AIMEE copy and UI. | AIMEE formatter/prompt/read-model code preserves confidence/provenance fields. | Tests or fixtures for degraded/stale/fallback/unknown/manual-review AIMEE responses. | P1 |
| AIMEE-011 | Passive AIMEE refresh MUST NOT call `/reviews/*` GET endpoints with `persist=true`. If review data is needed passively, it must come from non-persisting read methods or passive history endpoints. | API-client and backend service call review proving passive AIMEE uses `GET /aimee/snapshot` and passive history reads only. | Tests fail if passive AIMEE refresh calls mutation-like review GET endpoints or passes `persist=true`. | P1 |
| AIMEE-012 | AIMEE passive snapshot and passive drawer behavior MUST NOT perform command execution, remediation, runtime changes, governance updates, watchlist mutations, alert acknowledge/resolve, broker actions, or testing resets automatically. | Frontend/backend review showing passive AIMEE has no mutation controls or automatic mutation calls. | Component/API tests for passive drawer open, refresh, polling, and snapshot load. | P0 |

## Allowed reads

Passive snapshot may read existing persisted or projection state only when the read path is side-effect free.

Allowed passive reads may include:

- Generated operator summary with persistence disabled.
- Review history through passive read/history endpoints.
- Operator control state.
- Governance, deployment, and runtime rows.
- Watchlist and promotion rows through direct read queries.
- Domain events.
- Executions and trade intents.
- Operational telemetry projection if it does not refresh/persist state.
- Strategy registry metadata.
- Allocation/risk summaries only if they do not refresh alerts or persist derived state.

If any read path can seed defaults, refresh alerts, reconcile broker state, sync watchlists, emit events, or commit/flush, it must be excluded from passive snapshot or classified as mutation-like and tested separately.

## Forbidden mutations

Passive snapshot must not:

- call `session.add`, `session.delete`, `session.commit`, or `session.flush`;
- submit or close broker orders;
- reconcile broker/local positions or perform broker reads that trigger reconciliation or adoption;
- create or persist `GeneratedReviewRecord` rows or other review/advisory records;
- call mutation-like `/reviews/*` GET endpoints;
- create, update, or delete governance, deployment, runtime, watchlist, alert, event, trade, intent, execution, or position rows;
- seed governance defaults;
- create, update, delete, acknowledge, resolve, or refresh alerts;
- emit domain events or create/delete reconciliation events;
- start, stop, restart, retarget, or change runtime mode;
- update operator control state or governance;
- sync streaming subscriptions or watchlists;
- create promotion requests;
- call testing reset endpoints;
- schedule or trigger remediation.

## Allowed persistence

Passive AIMEE snapshot: none expected. A passive snapshot must be safe to call repeatedly, poll, refresh, or open/close from the drawer without changing durable local state or broker state.

Explicit advisory/question endpoints: may persist only the requested review/advisory artifact and must not perform broker, runtime, governance, reconciliation, watchlist, alert-refresh, event, allocation-refresh, or operational side effects.

If future AIMEE features persist conversation state, memory, preferences, or feedback, those must be specified separately as explicit non-trading persistence and must not be mixed with passive operational snapshot refresh.

## Frontend drawer expectations

- Passive drawer open, passive refresh, and passive polling must call `getAimeeSnapshot` only or other explicitly passive read functions.
- Passive AIMEE components/hooks must not import mutation functions unless those functions are isolated behind explicit user-triggered controls.
- Explicit advisory/question actions must be visually separate from passive refresh and must use POST advisory endpoints.
- AIMEE must not auto-submit questions, persist reviews, acknowledge alerts, update governance, mutate watchlists, start/stop runtimes, reconcile broker state, or reset testing history on drawer open/refresh.
- AIMEE copy must preserve degraded/stale/fallback/unknown/manual-review state and must not present explanations as stronger truth than backend fields support.
- Loading/error/fallback states must not render as healthy system truth.

## AIMEE response contract

AIMEE snapshot fields consumed by the frontend should be stable and documented.

The response contract should define:

- top-level sections returned by `GET /aimee/snapshot`;
- field names consumed by `frontend/components/aimee`;
- confidence/provenance fields where state may be degraded, stale, fallback, estimated, unknown, or derived;
- nullable/missing-field behavior;
- error/fallback shape;
- versioning or compatibility expectations if the shape changes.

A backend Pydantic response model is preferred. If the response remains a dict, the dict schema must be documented and covered by contract tests.

## AIMEE side-effect audit checklist

Passive AIMEE snapshot must be audited for absence of:

- database add/delete/commit/flush;
- `GeneratedReviewRecord` creation;
- governance default seeding;
- watchlist sync or streaming plan mutation;
- allocation alert refresh;
- broker reconciliation or recovery;
- broker mutation;
- runtime start/stop/mode changes;
- domain/reconciliation event creation;
- operator control or governance updates;
- mutation-like review GET calls;
- testing reset calls;
- frontend automatic mutation calls on drawer open, refresh, or polling.

## Must-not-cross AIMEE boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| AIMEE-BND-001 | Passive vs mutation | Passive AIMEE snapshot must not write local state or broker state. | Route/service no-write tests. | P1 |
| AIMEE-BND-002 | Passive vs reconciliation | Passive AIMEE snapshot must not reconcile, recover, adopt, or force-close broker/local truth. | Monkeypatch forbidden-call tests. | P0 |
| AIMEE-BND-003 | Passive vs advisory persistence | Passive AIMEE refresh must not create `GeneratedReviewRecord` or call mutation-like review GET endpoints. | Review row-count and API-client tests. | P1 |
| AIMEE-BND-004 | Passive vs broker mutation | Passive AIMEE must not submit orders, close positions, or call broker mutation paths. | Broker mutation forbidden-call tests. | P0 |
| AIMEE-BND-005 | Passive vs runtime/control mutation | Passive AIMEE must not start/stop runtimes, update governance, update operator control, refresh alerts, or sync watchlists. | Forbidden-call tests. | P1 |
| AIMEE-BND-006 | Explanation vs operation | AIMEE passive explanation must not trigger command execution or remediation. | Frontend/backend passive refresh tests. | P0 |
| AIMEE-BND-007 | Explanation vs truth upgrade | AIMEE must not make degraded, stale, fallback, estimated, unknown, simulated, or manual-review states sound healthy/exact. | Fixture tests for degraded snapshot explanations. | P1 |
| AIMEE-BND-008 | Response contract | Frontend-consumed AIMEE fields must be modeled or documented. | Response model or contract tests. | P1 |

## Known unknowns

- Frontend AIMEE tests were not found.
- `/reviews/*` GET endpoints now default to non-persisting previews; future audit should ensure passive AIMEE never opts into `persist=true`.
- AIMEE response shape is a dict and not strongly modeled by a backend Pydantic response model.
- Frontend AIMEE passive refresh import/call boundaries have not been proven by tests.
- Whether AIMEE explanations preserve all degraded/stale/fallback/unknown/manual-review provenance needs fixture coverage.
- Whether passive AIMEE could indirectly call mutation-capable helpers through shared summary/projection services needs route-level audit.
- Whether passive AIMEE uses any `/reviews/*` GET endpoint with `persist=true` needs frontend and backend call-path audit.
- Whether future AIMEE conversation persistence, preferences, or feedback storage could blur the passive operational snapshot boundary needs separate specification.
- Whether operational telemetry projections used by AIMEE are guaranteed side-effect free needs confirmation.
- Whether allocation/risk summaries used by AIMEE can refresh alerts or persist derived state needs confirmation.

## Required tests

- Route-level no-write test for `GET /aimee/snapshot` covering relevant operational tables.
- Regression tests proving passive snapshot does not create `GeneratedReviewRecord` rows.
- Monkeypatch/spy tests proving passive snapshot does not call reconciliation, recovery, governance seeding, watchlist sync, streaming plan mutation, alert refresh, broker mutation, runtime mutation, domain-event creation, or testing reset paths.
- Tests proving explicit `POST /reviews/questions` persists only the requested advisory artifact and performs no forbidden operational side effects.
- Frontend/API-client tests proving passive AIMEE refresh calls `getAimeeSnapshot` and `GET /aimee/snapshot` only.
- Frontend import/call graph review or tests proving passive AIMEE components/hooks do not import/call mutation API functions except behind explicit user-triggered controls.
- Contract tests or schema tests for AIMEE response fields consumed by frontend.
- Fixture tests proving AIMEE explanations preserve degraded, stale, fallback, estimated, unknown, simulated, manual-review, and unavailable states.
- Tests proving passive AIMEE loading/error/fallback states are not rendered as healthy system truth.
- Tests proving mutation-like `/reviews/*?persist=true` GET calls are not used by passive AIMEE refresh.

## Audit questions for Codex

- Did any new AIMEE snapshot field require calling a mutation-capable service?
- Does `GET /aimee/snapshot` call `session.add`, `session.delete`, `session.commit`, `session.flush`, or any service that does?
- Does passive AIMEE snapshot create `GeneratedReviewRecord` rows or call reviewer methods with `persist=True`?
- Does passive AIMEE trigger reconciliation, recovery, adoption, forced close, broker reads with reconciliation side effects, or broker mutation?
- Does passive AIMEE seed governance defaults, sync watchlists, refresh allocation alerts, emit events, or mutate runtime/control state?
- Does any passive AIMEE frontend component, hook, drawer open, refresh, or polling path call `POST /reviews/questions` automatically?
- Does passive AIMEE call mutation-like `/reviews/*` GET endpoints with `persist=true`?
- Is AIMEE response shape modeled by Pydantic or documented dict schema?
- Which AIMEE response fields are consumed by `frontend/components/aimee`?
- Does AIMEE copy preserve degraded, stale, fallback, estimated, unknown, simulated, manual-review, and unavailable states?
- Do AIMEE loading/error/fallback states ever appear as healthy operational truth?
- Should future AIMEE conversation persistence be specified separately from passive operational snapshot reads?
