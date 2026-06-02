# Supervised IG Demo-Trading Readiness Audit

## Audit date and inspected commit

- Audit date: `2026-06-02`
- Inspected commit: `ce6d4ddeee3a59c759d0820e40707f43f26cc5c9`
- Working tree at start: `git status --short` returned no output

## Scope and explicit exclusions

This audit assessed whether the repository is safe enough to proceed to one human-supervised, broker-connected IG demo-account smoke test with:

- IG demo account only
- fresh versioned database
- human operator present throughout
- one deliberately limited smoke-test workflow
- minimal controlled exposure
- ability to observe, reconcile, and safely close any demo position

This audit did not:

- set `IG_TRADING_ENABLED=true`
- invoke broker mutation endpoints
- submit, amend, or close any remote broker position
- run an unattended broker-connected autonomous session
- print credential values
- validate live-trading readiness
- validate unattended autonomous-trading readiness

## Previous documented posture

The current top-level posture in [docs/readiness.md](/Users/benparker/Documents/repos/codex-trading-app/docs/readiness.md:1) and [docs/audit-status.md](/Users/benparker/Documents/repos/codex-trading-app/docs/audit-status.md:1) says:

- not ready for live trading
- not automatically ready for a supervised broker-connected demo
- no current code-actionable P0/P1 defect in the reviewed closure slice
- latest successful `Repo Audit` run is `26776683955`

This audit agrees with the overall "not ready for live trading" posture, but it does not agree with the current "no code-actionable P0/P1 defect" claim.

## Final verdict

`NOT_READY_FOR_HUMAN_SUPERVISED_IG_DEMO_SMOKE_TEST`

## Executive summary

### What the codebase currently does

- The backend defaults to `BROKER_MODE=DEMO` and `IG_TRADING_ENABLED=false` in [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:22) and [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:86).
- The IG adapter supports read-only account and position reads, two-phase acknowledgement/confirmation handling, simulated local fills when dealing is disabled, runtime recovery, reconciliation, and a DB-backed runtime leadership lease.
- Fresh SQLite databases are migrated to Alembic head on startup via [backend/app/db/migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/migrations.py:17).
- A safe read-only preflight was possible with a fresh temporary SQLite DB, `IG_TRADING_ENABLED=false`, `IG_STREAMING_ENABLED=false`, `AUTONOMOUS_CONTROL_ENABLED=false`, and `TESTING_ROUTES_ENABLED=false`.

### What is ambiguous or weak

- Demo versus live routing is not fail-closed. `IG_API_BASE_URL` can override the host independently of `BROKER_MODE`, while the adapter still reports the config-derived account type.
- The operator UI does not show trustworthy DEMO/LIVE or dealing-enabled truth. The main nav explicitly renders `Account Env` as `Unknown`.
- Backend test-only routes are fail-open by default because `testing_routes_enabled` defaults to `True`.
- Critical backend readiness evidence is currently red. `backend/.venv/bin/pytest backend/tests -q` failed with `154 failed, 326 passed, 5 skipped, 60 errors`, with a shared root cause in `HealthService` using the module-global DB engine.

### What better industry patterns suggest

- IG documents separate demo and production gateways and separate demo credentials/API keys from live ones. That supports a hard environment boundary, not a soft override.
- IG also documents submission acknowledgement as distinct from trade confirmation. That supports preserving explicit ambiguous/manual-review state instead of implying a fill from an ack.
- Microsoft guidance for circuit breakers recommends failing fast on unstable remote dependencies, surfacing degraded state clearly, and retaining manual override/reset paths.
- OWASP guidance treats extraneous or administrative/test functionality in production-like builds as a real security risk, not a harmless convenience.

External sources used:

- [IG Labs: Getting started](https://labs.ig.com/gettingstarted)
- [IG Labs: FAQ](https://labs.ig.com/faq.html)
- [IG Labs: Trading basics](https://labs.ig.com/trading-basics.html)
- [IG Labs: REST Trading API Reference](https://labs.ig.com/rest-trading-api-reference.html)
- [Microsoft Learn: Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [OWASP: M10 Extraneous Functionality](https://owasp.org/www-project-mobile-top-10/2016-risks/m10-extraneous-functionality)

### What I recommend changing and why

1. Enforce a fail-closed demo/live environment boundary at config and adapter-construction time.
Why: the current design can send authenticated broker traffic to a live host while still labelling the session `DEMO`.

2. Surface verified broker environment, resolved endpoint class, dealing-enabled truth, and account projection in a dedicated backend contract and a blocking UI safety banner.
Why: supervised broker testing depends on operator certainty, not inferred mode.

3. Default-disable backend testing routes and require explicit, non-production-only enablement.
Why: destructive test-only mutation must not be reachable by default in the same app used for a supervised broker demo.

4. Fix the `HealthService` global-engine coupling and re-green the backend audit suites before any broker-connected smoke test.
Why: passive-read safety, runtime authority, recovery, and ambiguity-handling proofs are materially broken right now.

## Verified invariants

| Area | Verified invariant | Evidence |
| --- | --- | --- |
| Config defaults | Safe defaults exist for broker mode and dealing flag | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:22), [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:86) |
| IG default host mapping | Default IG hosts are demo for `DEMO` and live for `LIVE` | [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1400) |
| Dealing-disabled broker behavior | `IG_TRADING_ENABLED=false` prevents remote order/close submission and uses simulated local fills/closes instead | [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:112), [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:255), [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:157) |
| Entry confirmation handling | IG submission acknowledgement and separate confirmation/manual-review states are modeled | [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:76) |
| Duplicate retry suppression design | Execution attempts start at `SUBMISSION_PENDING` and unsafe duplicate retries are suppressed into manual review | [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3616) |
| Runtime leadership | Only the DB lease holder starts background loops | [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:43), [backend/app/services/runtime_leadership_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_leadership_service.py:21) |
| Stopped runtime truth | Stopping a runtime does not imply broker risk is flat | [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:634), [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py:304) |
| Reconciliation provenance | Reconciliation creates explicit adopted/forced-close lifecycle records instead of silently flattening mismatches | [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:25), [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:574), [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:730) |
| Fresh DB path | Fresh SQLite DBs are upgraded to Alembic head automatically | [backend/app/db/migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/migrations.py:17), [backend/tests/test_database_migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_database_migrations.py:27) |
| Non-SQLite legacy refusal | Existing unversioned non-SQLite DBs fail closed instead of being silently stamped | [backend/app/db/migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/migrations.py:32) |
| Operator auth policy | Mutating HTTP routes are covered by operator-auth policy and production-like envs fail if token is missing | [backend/app/api/auth.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/auth.py:24), [backend/tests/test_operator_auth_boundary.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_operator_auth_boundary.py:35) |
| CORS | Exact-origin CORS list is used without permissive regex | [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:174), [backend/tests/test_operator_auth_boundary.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_operator_auth_boundary.py:148) |
| Secret scan | Working-tree secret scan reported no findings | `python3 scripts/repo_secrets_scan.py --mode working-tree` |
| Safe read-only preflight | Required GET surfaces were reachable with dealing disabled and testing routes disabled | Section "Read-only preflight results" below |

## Blockers

| ID | Severity | Area | Finding | Concrete evidence | Why it blocks supervised demo | Required action | Required verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `DEMO-CONFIG-001` | P0 | Demo/live boundary | `IG_API_BASE_URL` can override the actual broker host independently of `BROKER_MODE`, and the adapter then reports `account_type` from config instead of from a verified remote environment. | [backend/app/core/broker_factory.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/broker_factory.py:11) passes both `AccountType(settings.broker_mode)` and `base_url=settings.ig_api_base_url`. [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:93) prefers the override over the account-type default. Requests send the configured API key and session tokens to whatever HTTPS host `base_url` resolves to in [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1239) and [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1306). IG's own FAQ documents separate demo and production base URLs: demo `https://demo-api.ig.com/gateway/deal` and prod `https://api.ig.com/gateway/deal`. | A human can believe the app is in demo mode while the adapter is actually pointed at the live IG host. That is an unsafe live-account reachability path. | Enforce a hard invariant: `BROKER_MODE=DEMO` may only use the demo gateway, `BROKER_MODE=LIVE` may only use the live gateway, and unknown/override hosts must be rejected unless explicitly allowlisted under a non-production test gate. Also surface resolved environment truth in API/UI state. | Add unit/integration tests for demo/live host mismatch rejection, malformed host rejection, safe defaulting, and verified environment exposure in backend/UI state. |
| `DEMO-UI-001` | P1 | Operator truth | The operator UI does not present trustworthy DEMO/LIVE or dealing-enabled truth. The nav explicitly shows `Account Env` as `Unknown`, and there is no surfaced backend `IG_TRADING_ENABLED` truth in the main readiness flow. | [frontend/components/app-nav.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/app-nav.tsx:215) hardcodes `Account Env` to `Unknown`. [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts:331) hardcodes `getBackendMode()` to `"live"`. No meaningful frontend consumption of backend dealing-enabled truth was found. | A supervised broker smoke test requires the human operator to know whether the app is attached to demo or live and whether broker dealing is enabled. Unknown or misleading state creates false operator confidence. | Add a backend truth endpoint for resolved broker environment, account projection, dealing-enabled state, and execution provenance state; render it as a blocking safety banner in the UI. | Add backend route tests and frontend e2e coverage that refuse a broker-connected smoke-test workflow when environment truth or dealing-enabled truth is unavailable or inconsistent. |
| `DEMO-OPS-001` | P1 | Test-only controls | Backend testing routes are enabled by default in code, and in local/development envs operator auth falls back to `local-operator` when no token is configured. | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:112) sets `testing_routes_enabled: bool = True`. [backend/app/api/router.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/router.py:46) registers `/testing` whenever the flag is truthy. [backend/app/api/auth.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/auth.py:49) returns `"local-operator"` when no token is configured outside production-like envs. [backend/tests/test_http_route_harness.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_http_route_harness.py:605) proves `/testing/reset-history` deletes domain-event history when enabled. The inspected `backend/.env` had no `TESTING_ROUTES_ENABLED` entry, so the code default applies. OWASP guidance warns against shipping extraneous/admin functionality in final builds. | A supervised demo should not rely on "hidden in the frontend" as the safety boundary for destructive test-only routes. Default-open history-reset behavior undermines audit integrity on the exact DB the smoke test is meant to observe. | Change the backend default to `False`, require explicit enablement only in test/dev harnesses, and add an environment gate so the testing router cannot register in demo/live postures. | Re-run route inventory and HTTP harness tests and confirm `/testing/reset-history` is `404` unless explicit test gates are set. |
| `DEMO-VERIFY-001` | P1 | Verification evidence | Large parts of the backend readiness evidence are currently red because `HealthService` opens sessions on the global engine instead of the migrated test engine, causing widespread `no such table: position` failures in read-only, runtime, authority, and recovery tests. | Full suite: `backend/.venv/bin/pytest backend/tests -q` -> `154 failed, 326 passed, 5 skipped, 60 errors`. Representative failures: `backend/tests/test_health_routes.py::test_system_telemetry_route_aggregates_multi_worker_observability_state`, `backend/tests/test_runtime_recovery_service.py::test_audit_test_002_runtime_recovery_resumed_runtime_preserves_authority_for_later_close`, `backend/tests/test_broker_action_http_authority.py::test_audit_api_008_strategy_start_http_route_reachable_entry_preserves_authority_and_audit`, and `backend/tests/test_passive_read_routes.py::test_audit_api_002_coverage_summary_get_does_not_sync_watchlist_state`. Root cause is visible in [backend/app/services/health_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/health_service.py:13), [backend/app/services/health_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/health_service.py:297), and [backend/app/services/health_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/health_service.py:309), while tests only patch the observability engine in [backend/tests/conftest.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/conftest.py:118). | The smoke-test decision depends on trustworthy evidence for passive GET safety, runtime leadership, recovery, ambiguity handling, and operator-authorized broker action paths. Those proofs are materially broken right now. | Remove the global-engine coupling from `HealthService` and make health classification session-aware or dependency-injected. Then re-run the full backend suite and the targeted audit suites. | Full backend pytest green, targeted audit suites green, and a fresh audit pass confirming the previously failing passive-read, runtime recovery, and authority-path tests are passing again. |

## Human sign-offs

These remain required human-controlled preconditions. None were completed by this audit.

| Sign-off | Status | Notes |
| --- | --- | --- |
| Intended broker account is an IG demo account | OPEN | Must be verified in the IG portal by a human. |
| Resolved endpoint is the IG demo endpoint | OPEN | Must be verified after `DEMO-CONFIG-001` is fixed because current environment truth is not fail-closed. |
| Fresh versioned database will be used | OPEN | Required for any supervised demo. |
| Repository/workstation sharing requires demo credential rotation | OPEN | Manual security decision outside code. |
| Historical SQLite blobs will be purged before broader sharing/publication | OPEN | Manual repository hygiene item. |
| Backend and frontend test-only controls are disabled | OPEN | Backend default currently blocks sign-off until fixed or explicitly overridden. |
| Operator token is configured appropriately for the supervised session | OPEN | The inspected `backend/.env` did not define `OPERATOR_API_TOKEN`. |
| Minimal valid instrument and size are selected | OPEN | No explicit demo-only smoke-test cap exists in code; this remains a human-controlled precondition. |
| Maximum acceptable demo risk is selected | OPEN | General runtime/allocation caps exist, but no dedicated demo-smoke-test cap was found. |
| IG demo portal is open for independent remote position verification | OPEN | Mandatory for supervised broker smoke testing. |
| Operator understands immediate close, pause, reconcile, and recovery procedure | OPEN | Must be confirmed before enabling dealing. |

## Unverified assumptions

- No broker-connected entry or close was executed during this audit.
- No live-account routing was attempted or validated.
- Some intended lifecycle invariants may still be correct, but current red backend suites make those claims too weak for smoke-test approval.
- Postgres migration rehearsal could not be exercised against a real Postgres instance locally because `POSTGRES_REHEARSAL_ADMIN_URL` was not configured.
- A future "ready after sign-off" verdict would still require code fixes for the blockers above before relying on manual sign-offs alone.

## Demo-versus-live environment trace

| Question | Finding | Evidence |
| --- | --- | --- |
| Which config selects demo vs live? | `BROKER_MODE` selects the default account type; `IG_API_BASE_URL` independently overrides the actual HTTPS host. | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:22), [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:84), [backend/app/core/broker_factory.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/broker_factory.py:11), [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:93) |
| Is the default safe? | Partially. Defaults are `BROKER_MODE=DEMO` and `IG_TRADING_ENABLED=false`, and the example env uses the demo gateway. | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:22), [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:86), [backend/.env.example](/Users/benparker/Documents/repos/codex-trading-app/backend/.env.example:8) |
| Does the app fail closed on missing/malformed environment selection? | It fails closed only for malformed `BROKER_MODE`. It does not fail closed when `BROKER_MODE` and `IG_API_BASE_URL` disagree. | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:182) |
| Can credentials for one environment be sent to the other? | Yes. The adapter sends the configured API key and session tokens to the resolved `base_url` host. | [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1239), [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1306) |
| Does the UI clearly show connected account environment? | No. Current nav shows `Account Env` as `Unknown`. | [frontend/components/app-nav.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/app-nav.tsx:215) |
| Do logs/events/surfaces distinguish simulated-local and broker-confirmed truth? | The backend models do distinguish them, and unit coverage exists for simulated-local broker results. End-to-end operator truth verification is currently weakened by the failing backend suites. | [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:157) |
| Does `IG_TRADING_ENABLED=false` block broker mutations while allowing safe reads? | It blocks remote broker order/close submission, but mutation code paths can still produce local simulated fills/closes if non-read-only paths are invoked. Safe read-only investigation worked in this audit when only GET routes were used and autonomy was disabled. | [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:112), [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:255) |
| Is there a path where enabling dealing could reach live without a separate `BROKER_MODE=LIVE` decision? | Yes. A live `IG_API_BASE_URL` plus `IG_TRADING_ENABLED=true` is sufficient even if `BROKER_MODE=DEMO`, because host routing is independent. | [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:93), [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py:1325) |

Conclusion: the demo/live boundary is not explicit enough for a supervised IG demo smoke test.

## Broker-mutation call graph

### Remote mutation call sites

| Mutation | Route / trigger | Code path | Authority and audit design | Dealing-disabled behavior | Test evidence | Current audit assessment |
| --- | --- | --- | --- | --- | --- | --- |
| Entry order placement | `POST /strategy/start`, `POST /strategies/{name}/start`, autonomous deployment/runtime price processing | [backend/app/api/routes/strategies.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/strategies.py:42), [backend/app/api/routes/strategies.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/strategies.py:173) -> [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:447) -> runtime `process_price_update` -> `_prepare_execution()` -> `_execute_entry_signal()` -> `engine.broker.place_order()` at [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:2576) | HTTP start routes stamp operator authority into `startup_context`; `_prepare_execution()` creates `SUBMISSION_PENDING`; execution and trade-intent transitions are persisted before/after submission. | Remote broker mutation is blocked, but `IG_TRADING_ENABLED=false` returns a simulated local fill. | Intended route-level proof exists in [backend/tests/test_broker_action_http_authority.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_broker_action_http_authority.py:182), but the test is currently failing because of `DEMO-VERIFY-001`. | Design is present, but the readiness proof is currently untrustworthy. |
| Exit order placement | Strategy-generated exit from running runtime; not from HTTP stop | [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3009) -> `engine.broker.close_position()` at [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3063) | Close path transitions intent to `CLOSE_REQUESTED`, records execution attempt, and preserves manual-review state for incomplete/ambiguous outcomes. | Remote broker mutation is blocked, but `IG_TRADING_ENABLED=false` returns a simulated local close. | Intended close/manual-review coverage exists in the strategy-service suite, but current backend regressions block strong approval evidence. | Design exists, but current passing evidence is insufficient. |
| Startup recovery attach/adopt | App startup under leader | [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:47) -> [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py:32) | Broker reads only; recovered/adopted positions are attached via explicit trade intents and domain events. | No remote mutation. | Direct recovery coverage exists in [backend/tests/test_runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_runtime_recovery_service.py:74), but critical tests are currently red because of the health regression. | Good design, currently under-verified. |
| Reconciliation | Market-data loop and explicit broker-position reads | [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py:85) -> `BrokerService().reconcile_positions(session)` -> [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:40) | Reconciliation writes explicit local lifecycle evidence and domain events; it does not issue remote broker closes. | No remote mutation. | Strong intended coverage exists in reconciliation tests, but broader backend readiness proof is currently weakened by `DEMO-VERIFY-001`. | Good design, currently under-verified. |
| Runtime stop | `POST /strategy/stop`, `POST /strategies/{name}/stop`, control-plane pause | [backend/app/api/routes/strategies.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/strategies.py:103), [backend/app/api/routes/strategies.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/strategies.py:241) -> [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:634) | Stop is audited but does not imply flat broker risk. Persisted open broker references are retained in stopped runtime details. | No remote broker close is attempted. | Recovery tests support this design. | Verified design: runtime stop is not a flattening action. |

### Background, polling, startup, and retry paths

- Background leader-only startup recovery runs in [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:67).
- Background leader-only market-data loop performs reconciliation and deployment reconciliation in [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py:78) and [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py:245).
- Autonomous deployment reconciliation can start/restart runtimes in [backend/app/services/strategy_deployment_manager_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_deployment_manager_service.py:49) and [backend/app/services/strategy_deployment_manager_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_deployment_manager_service.py:89).
- Duplicate retry suppression is implemented centrally in [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3616).
- Application-side direct remote mutation calls were only found at [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:2576) and [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3063).

Assessment: the mutation boundary is reasonably centralized in code, but current verification health is not strong enough to approve a broker-connected demo.

## Entry-flow evidence

| Step | Evidence found | Evidence gap / weakness |
| --- | --- | --- |
| 1. Candidate signal | Strategy and decision services implement candidate evaluation and runtime price processing. | The current backend regression prevents relying on many end-to-end service tests as passing evidence. |
| 2. Risk and allocation checks | Execution-time account, market-status, and sizing revalidation happen before submission in [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:2496). | Passing end-to-end service proof for several of these paths is currently blocked. |
| 3. Approved `TradeIntent` | Lifecycle model and transition logic exist in the strategy service. | Current direct readiness evidence is weakened by failing suites. |
| 4. `SUBMISSION_PENDING` execution | `_prepare_execution()` creates a durable execution row at `SUBMISSION_PENDING` before broker submission in [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:3756). | Code proof exists; route/service tests intended to prove it are not all passing. |
| 5. Execution-time broker account revalidation | `_assert_account_and_sizing_allow_execution()` is called before `place_order()`. | Full green verification is currently missing. |
| 6. Market-status refresh | `_assert_market_status_allows_execution()` is called before both entry and exit. | Operational-state adjacency is currently undercut by the health-service regression. |
| 7. Sizing and normalization revalidation | Broker sizing metadata and normalization are rechecked before submission; drift blocks execution. | Intended tests exist, but many broader strategy-service tests are currently blocked. |
| 8. Broker submission | Remote submission only happens via `engine.broker.place_order()`. | Fail-closed environment isolation is missing, so the submission target host is not trustworthy enough. |
| 9. Ack/fill/ambiguity/timeout/rejection/rate-limit result handling | IG adapter and strategy service preserve ambiguity/manual-review states and do not treat ack as fill truth. | Core logic exists, but current route/service evidence is not healthy enough for sign-off. |
| 10. Duplicate retry suppression | Unsafe duplicate entry/close retries are suppressed into manual review. | Design verified in code; passing regression proof is currently blocked. |
| 11. Durable event persistence | Critical paths use `record_required_domain_event()` and required audit writes. | Current red backend state means "fully verified" cannot be claimed. |
| 12. Operator-visible provenance | Backend intent exists for simulated vs broker-confirmed provenance. | The UI still lacks trustworthy environment/dealing truth, which is a blocker. |

Representative positive evidence:

- IG ack/confirmation split and manual-review DTOs: [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:76)
- Simulated-local dealing-disabled broker results: [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:157)

Representative broken evidence:

- [backend/tests/test_broker_action_http_authority.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_broker_action_http_authority.py:182)
- `backend/tests/test_strategy_service.py` scenarios are not reliable readiness proof while the shared health-engine regression remains.

Assessment: the intended entry state machine is sophisticated, but readiness evidence is currently insufficient for a supervised broker smoke test.

## Exit, recovery, and reconciliation evidence

Verified by code and partially by tests:

- Stopping a runtime does not imply flat risk: [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:634)
- Startup recovery preserves stopped-runtime open risk instead of auto-flattening it: [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py:304)
- Remote open positions can be attached or adopted explicitly with `RECOVERED_POSITION_ATTACHED` or `EXTERNAL_POSITION_ADOPTED`: [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py:263), [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py:539), [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:174), [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:574)
- Forced local closure after broker miss preserves explicit provenance and reconciliation events: [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:337), [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py:730)
- Broker-reference matching remains internal while operator-facing routes project identifiers safely: [backend/app/api/routes/broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/broker.py:24)

Positive targeted evidence still present in the suite:

- [backend/tests/test_runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_runtime_recovery_service.py:175)
- [backend/tests/test_reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_reconciliation_service.py:307)

Current blocker:

- `backend/tests/test_runtime_recovery_service.py::test_audit_test_002_runtime_recovery_resumed_runtime_preserves_authority_for_later_close` is currently red because `HealthService` touches the wrong engine during setup.

Assessment: the close/recovery design is directionally strong, but the current verification layer is not healthy enough to approve a broker-connected smoke test.

## Runtime and concurrency evidence

What the code currently does:

- DB-backed runtime leadership lease gates background loops: [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:43), [backend/app/services/runtime_leadership_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_leadership_service.py:21)
- Non-leader workers skip autonomous loops entirely: [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:52)
- Lease loss cancels autonomous loops: [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:104)
- Startup recovery runs only after leadership acquisition: [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:47)
- Runtime mode preserves `EXITS_ONLY` and blocks silent restart to `NORMAL` when open risk is unmanaged: [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py:534)

Weaknesses:

- `autonomous_control_enabled` defaults to `True` in [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:70), so a reused DB with approved governance can still drive runtime behavior unless the operator explicitly disables it or starts from a truly fresh DB.
- The market-data loop also performs reconciliation and deployment reconciliation in [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py:85) and [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py:274), so "read-only" posture depends on both `IG_TRADING_ENABLED=false` and operational discipline around autonomy/startup state.
- This is not a broker-mutation blocker by itself during dealing-disabled preflight, but it is an important operator precondition.

## Risk and allocation evidence

What exists:

- General runtime and allocation caps are configurable in [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:35) through [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:69).
- Execution-time account equity, available funds, market status, and sizing are revalidated in the strategy service before broker submission.
- IG sizing metadata parsing and normalization logic has direct unit coverage in [backend/tests/test_ig_broker_sizing.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_ig_broker_sizing.py:190).

What is weak:

- No dedicated demo-smoke-test risk cap or demo-only "single minimal order" mode was found.
- No dedicated operator-facing truth was found that clearly labels a session as being in a constrained demo-smoke-test posture.
- Current backend test failures prevent confidently claiming that the full entry-risk/revalidation path is green.

Assessment:

- I am treating "minimal valid instrument and size" and "maximum acceptable demo risk" as required human-controlled preconditions.
- I am not adding a separate code blocker for this because stronger blockers already force the verdict to `NOT_READY`, and the repo at least has general risk controls plus broker-side minimum-size normalization.

## Database evidence

What was verified:

- Fresh SQLite migration path applies Alembic head automatically: [backend/app/db/migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/migrations.py:17), [backend/tests/test_database_migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_database_migrations.py:27)
- Existing unversioned non-SQLite DBs are explicitly refused: [backend/app/db/migrations.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/migrations.py:32)
- Fresh safe preflight used a temporary versioned SQLite DB and booted successfully

What remains limited:

- Postgres rehearsal tests are present but were skipped locally because `POSTGRES_REHEARSAL_ADMIN_URL` was not set.
- The previous docs anchor their current-closure claim to an older CI run, while current local backend verification is materially red.

Assessment:

- A fresh versioned database path is available and credible for a supervised demo.
- This audit does not claim broad production-grade DB portability.

## Security evidence

Verified:

- Mutating routes require operator-auth policy and production-like envs reject missing tokens: [backend/app/api/auth.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/auth.py:24), [backend/tests/test_operator_auth_boundary.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_operator_auth_boundary.py:35)
- Exact-origin CORS without regex wildcard: [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py:174), [backend/tests/test_operator_auth_boundary.py](/Users/benparker/Documents/repos/codex-trading-app/backend/tests/test_operator_auth_boundary.py:148)
- Broker-position route projects identifiers instead of returning raw broker refs: [backend/app/api/routes/broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/routes/broker.py:24)
- Working-tree secret scan returned `No findings`
- Frontend env example correctly warns that `NEXT_PUBLIC_*` values are browser-visible: [frontend/.env.example](/Users/benparker/Documents/repos/codex-trading-app/frontend/.env.example:1)

Weak or manual-only:

- The inspected `backend/.env` did not define `OPERATOR_API_TOKEN`
- Backend test-only route exposure defaults open in code
- Historical repository cleanup and any needed credential rotation remain manual actions outside this audit

## Operator UI and observability evidence

What is visible and worked in read-only preflight:

- `/system/telemetry` reports runtime leader, broker connectivity, feed state, entry/exit eligibility, degradation reasons, and open-risk management state
- `/control-plane/summary` exposes governance and runtime/deployment alignment state
- `/health/stream` reflects streaming-disabled state clearly when `IG_STREAMING_ENABLED=false`

What is missing or misleading:

- No trustworthy DEMO/LIVE environment banner
- No trustworthy dealing-enabled/disabled banner
- Main nav explicitly renders `Account Env` as `Unknown`
- `getBackendMode()` is hardcoded to `"live"` even though it is not currently used

Assessment:

- Operator observability for runtime/health is decent.
- Operator observability for the most important supervised-demo safety boundary, demo versus live plus dealing-enabled truth, is currently inadequate.

## Read-only preflight results

Safe startup posture used:

- fresh temporary SQLite DB
- `IG_TRADING_ENABLED=false`
- `IG_STREAMING_ENABLED=false`
- `AUTONOMOUS_CONTROL_ENABLED=false`
- `TESTING_ROUTES_ENABLED=false`

Sanitized startup command pattern used:

```bash
DATABASE_URL=sqlite:////private/tmp/<fresh-demo-db>.sqlite \
IG_TRADING_ENABLED=false \
IG_STREAMING_ENABLED=false \
AUTONOMOUS_CONTROL_ENABLED=false \
TESTING_ROUTES_ENABLED=false \
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Observed read-only results:

| Command | Result | Observation |
| --- | --- | --- |
| `curl -sS http://127.0.0.1:8001/health` | PASS | `{"status":"idle"}` |
| `curl -sS http://127.0.0.1:8001/system/health` | PASS | Returned degraded-but-explicit broker/stream observability payload; no mutation observed. |
| `curl -sS http://127.0.0.1:8001/system/telemetry` | PASS | Initially showed `broker_connected:false`; after safe broker reads it showed `broker_connected:true`, `broker_connectivity_state:"CONNECTED"`, `entry_eligible:false`, `feed_source_state:"DISCONNECTED"`. |
| `curl -sS http://127.0.0.1:8001/dashboard` | PASS | Returned empty/open-risk-zero snapshot with `brokerInfo:null`. |
| `curl -sS http://127.0.0.1:8001/control-plane/summary` | PASS | Returned stopped families with autonomy disabled and no deployments. |
| `curl -sS http://127.0.0.1:8001/events` | PASS | Returned `[]`. |
| `curl -sS http://127.0.0.1:8001/broker/positions` | PASS | Returned `[]`; no remote mutation observed. |
| `curl -sS "http://127.0.0.1:8001/markets/overview?category=forex"` | PASS | Returned forex market overview successfully from safe read-only IG connectivity. |
| `curl -sS http://127.0.0.1:8001/market-data/feed-state` | PASS | Returned an empty instrument list with streaming disabled. |
| `curl -sS http://127.0.0.1:8001/positions` | PASS | Returned `[]`. |
| `curl -sS http://127.0.0.1:8001/executions` | PASS | Returned `[]`. |
| `curl -sS http://127.0.0.1:8001/health/stream` | PASS | Returned `enabled:false`, `connected:false`. |
| `curl -sS -o /tmp/testing_route_probe.out -w %{http_code} http://127.0.0.1:8001/testing/reset-history` | PASS | Returned `404` because backend testing routes were explicitly disabled for the run. |

Important nuance:

- This preflight proved no remote broker mutation occurred in the exercised GET paths.
- It did not prove that all passive GET paths are mutation-free internally; the passive-read suite is currently red, and `/coverage/summary` has a failing no-write test because the health path currently touches the wrong engine.

## Commands run and exact results

### Passed

| Command | Result |
| --- | --- |
| `git status --short` | clean; no output |
| `python3 scripts/check_spec_coverage_matrix.py` | PASS |
| `backend/.venv/bin/python scripts/check_backend_route_inventory.py` | PASS |
| `python3 scripts/repo_secrets_scan.py --mode working-tree` | PASS; `No findings.` |
| `git diff --check` | PASS |
| `cd frontend && npm run typecheck` | PASS |
| `cd frontend && npm run test:frontend` | PASS; `77 passed` |
| `cd frontend && npm run test:e2e -- --grep "AUDIT-|FLOW-"` | PASS; `56 passed` |
| `backend/.venv/bin/pytest backend/tests/test_config.py backend/tests/test_ig_broker_sizing.py backend/tests/test_broker_fake_contract.py backend/tests/test_operator_auth_boundary.py backend/tests/test_testing_routes.py backend/tests/test_database_migrations.py backend/tests/test_initialize_database.py -q` | PASS; `48 passed, 1 warning` |
| `gh run list --workflow "Repo Audit" --limit 5` | PASS; latest relevant success is `26779880629` |
| `gh run view 26779880629 --job 78941182708` | PASS; backend-audit job shows success in CI for that run |
| Safe read-only `curl` commands listed in the preflight section | PASS |

### Failed

| Command | Result |
| --- | --- |
| `./scripts/check_backend_requirements.sh` | FAIL; backend lockfile drift detected (`idna==3.17` vs regenerated `idna==3.18`) |
| `backend/.venv/bin/pytest backend/tests -q` | FAIL; `154 failed, 326 passed, 5 skipped, 60 errors` |
| `backend/.venv/bin/pytest backend/tests/test_runtime_leadership_service.py backend/tests/test_runtime_recovery_service.py backend/tests/test_reconciliation_service.py backend/tests/test_broker_action_http_authority.py -q` | FAIL; `22 failed, 22 passed` |
| `backend/.venv/bin/pytest backend/tests/test_health_routes.py backend/tests/test_http_route_harness.py backend/tests/test_passive_read_routes.py backend/tests/test_market_status_service.py backend/tests/test_operational_state_service.py backend/tests/test_operational_telemetry_service.py -q` | FAIL; `71 failed, 16 passed` |
| `backend/.venv/bin/pytest backend/tests/test_health_routes.py -x -q` | FAIL; first failure `test_system_telemetry_route_aggregates_multi_worker_observability_state` with `sqlite3.OperationalError: no such table: position` |
| `backend/.venv/bin/pytest backend/tests/test_runtime_recovery_service.py -x -q` | FAIL; first failure `test_audit_test_002_runtime_recovery_resumed_runtime_preserves_authority_for_later_close` with the same `HealthService`/global-engine issue |
| `backend/.venv/bin/pytest backend/tests/test_broker_action_http_authority.py -x -q` | FAIL; first failure `test_audit_api_008_strategy_start_http_route_reachable_entry_preserves_authority_and_audit` with the same `HealthService`/global-engine issue |
| `backend/.venv/bin/pytest backend/tests/test_passive_read_routes.py -x -q` | FAIL; first failure `test_audit_api_002_coverage_summary_get_does_not_sync_watchlist_state` with the same `HealthService`/global-engine issue |

### Skipped

| Command | Result |
| --- | --- |
| `backend/.venv/bin/pytest backend/tests/test_postgres_migration_rehearsal.py -q` | `5 skipped`; `POSTGRES_REHEARSAL_ADMIN_URL` not set |

### Unavailable or rerun with alternate tool

| Command | Result |
| --- | --- |
| `python3 scripts/check_backend_route_inventory.py` | Could not run in the host Python environment because `fastapi` was missing; reran successfully with `backend/.venv/bin/python` |

### Warnings

| Command | Result |
| --- | --- |
| `gh run view 26779880629` | Reported a newer successful `Repo Audit` run than the docs cite and included GitHub Actions Node 20 deprecation annotations. |

## Stale or contradictory documentation found

| Document | Stale or contradictory statement | Current evidence |
| --- | --- | --- |
| [docs/readiness.md](/Users/benparker/Documents/repos/codex-trading-app/docs/readiness.md:9) | Claims the newest successful `Repo Audit` run is `26776683955` and that there is no current code-actionable P0/P1 defect. | `gh run list --workflow "Repo Audit" --limit 5` shows newer success `26779880629`. Current local backend evidence is materially red, including passive-read, recovery, and authority-path suites. |
| [docs/audit-status.md](/Users/benparker/Documents/repos/codex-trading-app/docs/audit-status.md:11) | Repeats the same latest-run and no-current-P0/P1 assertions. | Same contradiction as above. |
| [docs/operator-guide.md](/Users/benparker/Documents/repos/codex-trading-app/docs/operator-guide.md:25) | Correctly states demo defaults and `IG_TRADING_ENABLED=false`, but does not document that backend testing routes default to enabled in code unless explicitly overridden. | [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py:112); inspected `backend/.env` had no `TESTING_ROUTES_ENABLED` entry. |

## Human-run supervised demo smoke-test runbook

This runbook is intentionally manual. Do not execute Phase C until the blockers in this report are fixed and the remaining sign-offs are completed.

### Phase A: disabled-dealing preflight

1. Create a fresh versioned database.
Use a fresh SQLite or other reviewed versioned DB only. Do not reuse a personal or legacy non-versioned database.

2. Verify sanitized configuration.
Confirm variable names and presence only: `BROKER_PROVIDER`, `BROKER_MODE`, `IG_API_BASE_URL`, `IG_TRADING_ENABLED`, `IG_STREAMING_ENABLED`, `IG_VERIFY_SSL`, `TESTING_ROUTES_ENABLED`, `DATABASE_URL`, `OPERATOR_API_TOKEN`.

3. Confirm intended environment.
Human operator must confirm the target account is an IG demo account and the resolved endpoint is the IG demo endpoint.

4. Start backend with:

- `IG_TRADING_ENABLED=false`
- `AUTONOMOUS_CONTROL_ENABLED=false`
- `TESTING_ROUTES_ENABLED=false`
- fresh DB path

Suggested safe command pattern:

```bash
DATABASE_URL=sqlite:////private/tmp/<fresh-demo-db>.sqlite \
IG_TRADING_ENABLED=false \
IG_STREAMING_ENABLED=false \
AUTONOMOUS_CONTROL_ENABLED=false \
TESTING_ROUTES_ENABLED=false \
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

5. Verify:

- `GET /health`
- `GET /system/health`
- `GET /system/telemetry`
- `GET /dashboard`
- `GET /control-plane/summary`
- `GET /events`
- `GET /broker/positions`
- `GET /markets/overview?category=forex`
- `GET /health/stream`

6. Confirm:

- no remote mutation occurred
- `/events`, `/positions`, and `/executions` do not unexpectedly populate
- degraded broker-read states are clearly labelled if connectivity is absent
- test-only backend route returns `404`
- audit and telemetry surfaces show leader/runtime state and broker/stream degradations explicitly

### Phase B: explicit human enablement checkpoint

Before any broker-connected entry attempt, the human operator must confirm all of the following:

- IG demo account is visible in the IG portal
- there are no unexpected pre-existing remote demo positions
- minimal valid order size is selected
- maximum acceptable demo risk is selected
- emergency stop, immediate close, reconcile, and recovery procedure is understood
- runtime leadership is healthy
- audit event persistence is healthy
- backend and frontend test-only controls are disabled
- operator token is configured appropriately for the session

### Phase C: one minimal broker-connected demo trade

Do not execute this phase during the audit. When the blockers are fixed and sign-off is complete, capture all of the following evidence:

1. Entry intent
Capture the `TradeIntent`, execution attempt id, operator correlation id, instrument, requested size, and UI safety banners.

2. Execution attempt
Capture the persisted `SUBMISSION_PENDING` execution and the operator action that triggered it.

3. Broker acknowledgement
Capture the broker acknowledgement/deal reference without exposing raw secret headers.

4. Broker-confirmed fill or explicit ambiguous state
Capture either:

- broker-confirmed open position with broker-confirmed provenance, or
- explicit ambiguous/manual-review state that does not imply a confirmed fill

5. Remote portal verification
Confirm the expected open demo position is visible in the IG demo portal.

6. Dashboard/events verification
Confirm the dashboard, events, and positions surfaces reflect the correct provenance and open-risk state.

7. Close request
Capture the close execution attempt and operator action.

8. Broker-confirmed close or explicit manual-review state
Confirm either:

- broker-confirmed close, or
- explicit manual-review state with open risk still visible

9. Final reconciliation
Confirm no unexpected open risk remains locally or in the IG demo portal.

### Phase D: failure-path checks

Use fake-broker or controlled test scenarios, not remote broker mutation, for:

- broker timeout
- acknowledgement without fill confirmation
- rejected order
- stale market
- unavailable account read
- insufficient funds
- duplicate entry retry
- partial close
- rejected close
- ambiguous close
- restart with open remote position
- stopped runtime with open risk

### Phase E: rollback

At the end of the supervised demo session:

1. Return to `IG_TRADING_ENABLED=false`.
2. Pause or stop runtimes deliberately.
3. Confirm there are no remote demo positions left open.
4. Run reconciliation and verify local state matches broker truth.
5. Save event evidence and screenshots needed for the audit trail.
6. Document any unexpected behavior before the next session.

## Recommended next implementation task

Fix the broker-environment safety boundary first.

Recommended task:

`Enforce fail-closed IG environment isolation by binding BROKER_MODE to an allowlisted IG host, rejecting BROKER_MODE/IG_API_BASE_URL mismatches, and exposing a verified broker-environment + dealing-enabled status contract to the UI.`

Why this is first:

- It addresses the only current P0 blocker.
- It removes the possibility of an apparently-demo session reaching a live endpoint.
- It gives the operator a reliable trust anchor for the later smoke-test runbook.
- It creates the right foundation for the next step, which is fixing the `HealthService` test regression and re-running the blocked readiness suites.
