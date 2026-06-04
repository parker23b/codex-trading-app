# Testing contract

Critical trading behavior must be proven by behavioral tests. Tests should verify state transitions, failure handling, broker boundaries, read-only guarantees, and operator-visible degraded states.

## Current test evidence

The backend has broad pytest coverage under `backend/tests`, including decision lifecycle, strategy execution, control plane, runtime recovery, reconciliation, risk/allocation, market data, streaming watchlist, health, coverage, dashboard, and AIMEE read-only behavior.

The frontend also has active static and browser coverage through `npm run test:frontend` and `npm run test:e2e`, including operator-truth, mutation-control, degraded-state, and environment-banner scenarios.

## Testing terminology

- Behavioural test: a test that drives real service, route, component, or flow behaviour and asserts state transitions, side effects, errors, emitted events, read models, or operator-visible output.
- Construction test: a test that only verifies an object can be created, configured, or imported. Construction tests are not sufficient for P0/P1 trading invariants.
- Contract test: a test that proves an interface boundary behaves as specified, such as broker DTOs, API response shapes, route classification, frontend type mappings, or fake broker semantics.
- Flow test: a test that verifies a complete lifecycle path across multiple services, routes, persistence records, broker fakes, or frontend surfaces.
- Regression test: a test added to prove a fixed bug cannot return. For P0/P1 bugs, it should fail against the original broken behaviour.
- Operator-visible test: a frontend or read-model test proving the operator can see the relevant success, degraded, blocked, error, manual-review, stale, fallback, unknown, or recovery state.
- Spec evidence matrix: a table mapping spec IDs and flow IDs to concrete test files, test names, verification level, and known gaps.

## Test verification levels

Use these labels when auditing test evidence:

- `NOT_TESTED`: no meaningful automated test evidence identified.
- `CONSTRUCTION_ONLY`: tests only object construction/import/configuration and do not prove behaviour.
- `UNIT_VERIFIED`: isolated function/class behaviour is tested without persistence, route, or lifecycle integration.
- `SERVICE_VERIFIED`: service behaviour is tested with meaningful fakes/session state and persisted outcomes.
- `ROUTE_VERIFIED`: API route behaviour, response shape, status/error handling, and side effects are tested.
- `FRONTEND_VERIFIED`: frontend component/API-client behaviour is tested for operator-visible states.
- `FULL_STACK_VERIFIED`: backend route/service/persistence behaviour and frontend consumption are tested together through realistic fixtures or integration tests.
- `E2E_VERIFIED`: browser-level or true end-to-end tests verify operator-visible behaviour through the UI.

P0/P1 trading invariants should not remain at `CONSTRUCTION_ONLY`.

## Test invariants

| Spec ID | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- |
| TEST-001 | Critical P0/P1 trading invariants MUST have behavioural test evidence. Tests must assert state transitions, side effects, persistence, broker calls or non-calls, emitted events, read models, or operator-visible state. | Spec evidence matrix mapping P0/P1 invariant IDs to concrete test files and test names. | P1 | Medium |
| TEST-002 | Read-only boundaries MUST have tests proving no writes or forbidden side effects, including indirect writes through helper services. | Before/after DB assertions, row-count checks, monkeypatch forbidden service calls, and no commit/add/delete/flush verification where practical. | P1 | Medium |
| TEST-003 | Broker boundary tests MUST include failure, stale-data, sizing, normalization, timeout, rate-limit, partial-fill, partial-close, ambiguous confirmation, and close-failure cases where relevant. | Broker fake contract tests and adapter tests covering read failures, order failures, stale data, unsupported sizing, partial outcomes, and reconciliation inputs. | P1 | Medium |
| TEST-004 | Frontend operator UI MUST test loading, error, empty, stale, degraded, fallback, unknown, manual-review, simulated, and partial/provisional states for critical surfaces. | Component/API-client/e2e tests for dashboard, live view, control plane, risk, coverage, markets, strategies, events, and AIMEE. | P1 | Low |
| TEST-005 | Construction-only tests are insufficient for critical services, routes, broker boundaries, state machines, or UI safety states. Critical tests must drive behaviour and inspect resulting state, events, errors, broker interactions, or rendered output. | Test review showing critical tests assert behavioural outcomes rather than only object construction. | P2 | Medium |
| TEST-006 | Fakes MUST preserve meaningful broker/service semantics and must not make unsafe paths look safe. Fake broker behaviour must be contract-tested against the broker contract. | Fake broker contract tests for account, market metadata, sizing, normalization, order/close success/failure, partial outcomes, ambiguous confirmation, and positions for reconciliation. | P1 | Medium |
| TEST-007 | Line/branch coverage reports MUST be interpreted alongside spec and flow coverage. High line coverage must not be treated as proof of trading safety if P0/P1 behaviours, failure modes, routes, or frontend states lack direct evidence. | Coverage matrix mapping specs, flows, routes, and frontend surfaces to test evidence and verification level. | P2 | Low |
| TEST-008 | Every fixed P0/P1 trading bug MUST receive a regression test that names the behaviour/failure mode and would fail against the original bug. | Regression tests linked to bug/finding IDs, behaviour names, and affected spec IDs. | P1 | Medium |
| TEST-009 | Every P0/P1 spec invariant and critical flow should map to at least one concrete test file/test name or an explicit Needs test gap. | Maintained spec evidence matrix or audit checklist. | P1 | Low |
| TEST-010 | Backend routes MUST be tested according to their API classification: passive reads prove no writes, active read/refresh proves documented side effects, mutations prove intended side effects/errors/audit, and broker actions prove lifecycle authority. | Route tests aligned with `04-backend-api-contract.md`. | P1 | Medium |
| TEST-011 | Frontend tests MUST prove backend enum/status states render correctly, and unknown states render as unknown/unsupported rather than healthy/default. | Type/mapping tests and component fixtures for `TradeIntent`, `Execution`, governance, deployment, runtime, risk, coverage, event, alert, and health states. | P1 | Low |
| TEST-012 | Tests or import/call graph audits MUST prove passive dashboard, passive AIMEE, and passive read surfaces do not call mutation APIs automatically. | Frontend API-client tests, component tests, or import/call graph review. | P1 | Medium |
| TEST-013 | P0/P1 failure-mode tests MUST assert operator-visible evidence such as status fields, alerts, events, manual-review state, degraded UI, or preserved open-risk state. | Backend read-model tests and frontend component tests for failure/degraded states. | P1 | Medium |
| TEST-014 | Test-only or destructive routes/controls MUST have tests or config review proving they are environment-gated and unavailable in production-like operation. | Tests/config review for `/testing/*` routes and frontend testing reset controls. | P0 | Medium |
| TEST-015 | Broker and service fakes used in critical tests MUST be protected against drift from production interface semantics. | Contract tests shared across fake and adapter DTO semantics, or explicit fake capability matrix. | P1 | Medium |
| TEST-016 | Mutation and broker-action tests MUST cover error responses and prove audit state is preserved where practical before errors are surfaced. | Route/service tests for broker failure, reconciliation failure, runtime failure, alert mutation failure, and review/advisory mutation failure. | P1 | Medium |
| TEST-017 | Environment-boundary and health-context regressions MUST prove the backend fails closed for broker-environment selection and uses the active database context for passive health/telemetry reads. | Config/adapter tests for canonical IG gateway validation plus regression tests proving health reads use the injected or active session rather than a module-global engine. | P0 | High |

## Spec and flow evidence matrix

Maintain a matrix mapping critical requirements to tests.

Recommended columns:

- Spec or flow ID.
- Criticality.
- Expected behaviour.
- Required verification level.
- Current verification level.
- Test files.
- Key test names.
- Frontend evidence.
- Route evidence.
- Known gaps.

Rules:

- P0 items require direct behavioural evidence or an explicit Needs test gap.
- P1 items require direct behavioural evidence where practical, especially for read-only boundaries, UI truthfulness, broker boundaries, risk, and state transitions.
- A test file name alone is not enough; key test names or behaviours should be listed where possible.
- Coverage percentage alone is not evidence that a spec invariant is tested.

## Test categories

| Category | Expectations | Evidence/examples |
| --- | --- | --- |
| Unit tests | Suitable for pure strategy logic, formatting helpers, deterministic calculation, enum mapping, and isolated sizing helpers. Not sufficient alone for P0 lifecycle safety. | Strategy tests and broker sizing tests. |
| Service tests | Should drive domain services with real sessions/fakes and assert persisted state, lifecycle transitions, events, alerts, and broker calls/non-calls. | `test_strategy_service.py`, `test_trade_decision_service.py`, `test_control_plane_service.py`. |
| Integration tests | Should validate multi-service lifecycle flows, especially `TradeIntent` to `Execution`, recovery/reconciliation, allocation/risk, control-plane/runtime, and broker-fake paths. | `test_intent_lifecycle_integration.py`, recovery/reconciliation tests. |
| Route tests | Should validate route classification, status codes, response fields, error details, side effects, read-only guarantees, and audit persistence. | Present for some features; needs expansion. |
| Frontend tests | Should validate critical operator surfaces in loading, error, empty, stale, degraded, fallback, unknown, manual-review, simulated, and partial/provisional states. | Missing/Needs confirmation. |
| Full-stack/e2e tests | Should validate that backend truth appears correctly in frontend operator surfaces and that UI controls call the correct mutation endpoints with correct pending/error/success states. | Missing/Needs confirmation. |

## Broker fake requirements

Broker fakes used in critical tests must model:

- account equity unavailable, invalid, stale, or restricted;
- market metadata unavailable, stale, closed, suspended, dealing-restricted, or untradable;
- live stream unavailable vs fallback polling where relevant;
- exact, approximate, unsupported, and degraded sizing quote modes;
- min deal size, size step, precision, and normalization drift;
- order submission pending, acknowledgement, fill, rejection, timeout, rate limit, unknown/ambiguous confirmation, and failure;
- partial fill and manual review;
- close success, close failure, close timeout, partial close, and ambiguous close confirmation;
- broker positions for reconciliation, including unmatched remote position and broker-missing local position;
- simulated/local fills and closes distinct from broker-confirmed truth;
- client request id/deal reference correlation where supported.

Fake broker defaults must not always return safe/healthy values. Tests should deliberately configure fake failure and degraded states.

## Frontend test requirements

Critical frontend tests should cover:

- backend unavailable/loading/error states;
- empty data states;
- stale/fallback/disconnected market-data states;
- estimated/provisional/simulated/unknown risk truth;
- manual-review and unmanaged-open-risk states;
- governance/deployment/runtime mismatch;
- missing or unknown enum values;
- passive surface does not call mutation APIs;
- mutation controls show labels, disabled reasons, pending state, success state, error detail, and refreshed backend truth;
- backend `HttpError.detail` is preserved and displayed for operator actions;
- fallback/default API objects do not render as healthy backend truth;
- test-only controls are hidden or disabled outside approved dev/test environments;
- AIMEE passive refresh calls only passive snapshot APIs.

## Route test requirements

Route tests should cover:

- classification from `04-backend-api-contract.md`;
- passive read no-write behaviour;
- active read/refresh documented side effects;
- mutation side effects and audit evidence;
- broker mutation lifecycle authority;
- HTTP status codes and structured error detail;
- response model or documented dict schema fields consumed by frontend;
- route compatibility/deprecation behaviour where applicable;
- environment gating for test-only routes.
- backend-owned environment-status routes such as `/system/broker-environment`, including secret-redaction and fail-closed truth.

GET routes classified as passive reads must be tested against accidental `session.add`, `session.delete`, `session.commit`, `session.flush`, default seeding, reconciliation, watchlist sync, alert refresh, review persistence, runtime mutation, broker mutation, and event creation where applicable.

## Regression test rules

For every fixed P0/P1 trading bug:

- add a regression test in the same change or explicitly document why it is not possible;
- name the test after the behaviour/failure mode, not the implementation detail only;
- assert the previous unsafe outcome cannot happen;
- include the relevant spec ID or finding reference in the test name, docstring, or nearby comment where useful;
- prefer the narrowest test that would have failed before the fix and passes after the fix;
- include frontend/operator-visible evidence when the bug affected operator interpretation.

## Test anti-patterns

Avoid treating these as sufficient evidence for critical behaviour:

- only asserting object construction;
- only asserting a function was called without checking persisted outcome;
- mocking away the broker/service failure mode being tested;
- asserting happy path only for P0/P1 flows;
- using fake defaults that always represent healthy broker/market state;
- checking line coverage without mapping to spec/flow behaviour;
- testing frontend happy render without loading/error/degraded/unknown fixtures;
- testing API status code only without side-effect or response-contract assertions;
- snapshot tests that hide semantic changes in large diffs;
- frontend fallback objects that look healthy in tests.

## Coverage interpretation

Coverage reports are useful for finding unexecuted code, but they are not proof of trading safety.

Coverage review should answer:

- Which P0/P1 spec IDs are directly tested?
- Which critical flows have success and failure-path coverage?
- Which routes have read/mutation classification tests?
- Which frontend critical surfaces have degraded-state coverage?
- Which broker fake behaviours are contract-tested?
- Which known bugs have regression tests?

A lower line coverage suite with strong behavioural coverage of P0/P1 invariants is more valuable than high line coverage that misses critical failure modes.

## Critical flows requiring tests

- `FLOW-ENTRY-001`: approved intent success; rejected/stale/budget-blocked/broker-metadata-failed candidates create no broker order; broker failure/partial/ambiguous outcome preserves audit/operator visibility.
- `FLOW-EXIT-001`: successful close; close failure; partial close; ambiguous close; open risk remains visible and managed/manual-review.
- `FLOW-RECOVERY-001`: startup recovery; unmatched broker position adoption; broker-missing local position reconciliation; recovery state distinguishable from normal strategy-owned state.
- `FLOW-GOVERNANCE-001`: approval vs autonomy vs deployment vs runtime separation; emergency stop; mismatch; open-risk preservation.
- `FLOW-RISK-001`: budgets; stale/broker failure; sizing normalization; risk confidence; alert persistence; reservation/live-risk transitions.
- `FLOW-MARKET-DATA-001`: stream healthy; fallback polling; stale stream; disconnected broker/feed; UI degraded display.
- `FLOW-AIMEE-001`: passive snapshot no writes; forbidden services not called; frontend passive refresh uses only `/aimee/snapshot`.
- `FLOW-COVERAGE-001`: watchlist/shortlist vs streaming vs entry eligibility; cap/cooldown; protective pins; stale stream display.
- `FLOW-BROKER-ENV-001`: canonical demo/live IG gateway classification, live-dealing acknowledgement, backend-owned environment status contract, frontend banner truth, and no credentialed request before URL validation.

## Must-not-cross testing boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| TEST-BND-001 | Behaviour vs construction | P0/P1 invariants must not rely on construction-only tests. | Behavioural test evidence matrix. | P1 |
| TEST-BND-002 | Passive read proof | Read-only guarantees must prove no writes or forbidden side effects. | Before/after DB and monkeypatch tests. | P1 |
| TEST-BND-003 | Fake fidelity | Broker fakes must not make unsafe broker states impossible to test. | Fake contract tests. | P1 |
| TEST-BND-004 | Frontend truth | Operator UI must test degraded/unknown/fallback states, not just happy states. | Component/e2e tests. | P1 |
| TEST-BND-005 | Route classification | API routes must be tested according to read/mutation/broker/test-only classification. | Route tests. | P1 |
| TEST-BND-006 | Regression coverage | Fixed P0/P1 bugs must not ship without a behaviour-focused regression test or explicit documented exception. | Regression tests. | P1 |
| TEST-BND-007 | Test-only safety | Test-only routes and controls must be gated away from production-like operation. | Config/route/frontend tests. | P0 |
| TEST-BND-008 | Coverage interpretation | Line coverage must not be used as a substitute for spec/flow evidence. | Coverage matrix. | P2 |

## Known unknowns

- Frontend test runner and coverage are not identifiable.
- Route-level read-only tests are incomplete for all GET endpoints.
- OpenAPI contract testing is not identifiable.
- Live IG behavior is represented through fakes and adapter unit tests, but not through recorded integration fixtures.
- P0/P1 spec IDs are not yet mapped to concrete test files and test names in a maintained evidence matrix.
- Active read/refresh routes that write state may not have explicit side-effect tests.
- Frontend component tests and e2e coverage are not identifiable.
- Response-contract testing is not identifiable.
- Broker fake behaviour may not cover timeout, rate-limit, ambiguous confirmation, partial close, client request id correlation, or simulated-vs-live truth.
- Some tests may rely on fake defaults that represent healthy broker/market state and do not exercise degraded paths.
- Operator-visible failure evidence may not be asserted for every P0/P1 failure mode.
- Test-only route/frontend controls may not have production-gating tests.
- Coverage reporting may exist but not be tied to spec/flow evidence.

## Required tests

- Spec evidence matrix or review checklist mapping every P0/P1 spec ID to test files, test names, verification level, and gaps.
- Behavioural tests for all P0/P1 invariants across product intent, broker contract, API contract, frontend UI, end-to-end flows, state machines, risk/allocation, and AIMEE.
- Route tests for every endpoint classified in `04-backend-api-contract.md`, including passive reads, active read/refresh, mutations, broker reads/actions, and test-only routes.
- Read-only route tests proving no database writes, default seeding, reconciliation, alert refresh, review persistence, watchlist sync, runtime mutation, broker mutation, or event creation.
- Broker fake contract tests for account, market, sizing, normalization, order, fill, partial fill, close, partial close, timeout, rate limit, ambiguous confirmation, simulated result, and reconciliation positions.
- Frontend tests for critical operator displays and mutation controls across loading, error, empty, stale, degraded, fallback, unknown, manual-review, simulated, and partial/provisional states.
- Enum parity tests for frontend/backend state values and unknown-state rendering.
- Regression tests for every fixed P0/P1 trading bug.
- Tests proving test-only routes and controls are unavailable in production-like operation.
- Coverage matrix maintenance check or review checklist.

## Audit questions for Codex

- Which P0/P1 spec IDs have no direct behavioural test evidence?
- Which tests are construction-only for critical behaviour?
- Which tests mock away the failure mode they claim to validate?
- Which critical flows have happy-path tests but no failure-path tests?
- Which passive GET routes lack no-write tests?
- Which active read/refresh routes write state and lack explicit side-effect tests?
- Which mutation routes lack error/audit preservation tests?
- Which frontend critical surfaces lack loading/error/empty/stale/degraded/unknown fixtures?
- Which frontend mutation controls lack pending/error/success/refreshed-truth tests?
- Which backend enum states are not covered by frontend type/mapping tests?
- Which fake broker behaviours differ from the broker contract or make unsafe states impossible to test?
- Do broker fakes cover timeout, rate limit, ambiguous confirmation, partial close, client request id, and simulated-vs-live truth?
- Do any tests rely on fake defaults that always return healthy broker/market state?
- Are test-only routes and frontend testing controls gated away from production-like operation?
- Is coverage percentage being used without spec/flow evidence mapping?
- Does every fixed P0/P1 bug have a regression test that would fail against the original bug?
