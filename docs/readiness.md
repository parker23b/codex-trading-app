# Readiness And Safe Usage

InvestMate is **not ready for live or demo broker dealing**.

Use this repository for local development, UI review, strategy research, broker-read investigation, and smoke testing only. Keep `IG_TRADING_ENABLED=false`. Do not enable real broker dealing until the open P1 readiness blockers in [audit-status.md](audit-status.md) are closed with regression evidence proportionate to trading risk.

## Current Safe Posture

Safe local use means:

1. Keep `IG_TRADING_ENABLED=false`.
2. Use IG credentials only for broker-read investigation, such as auth, positions, account state, market metadata, and stream health.
3. Treat `/testing/reset-history` as destructive and enable it only in explicit dev/test workflows.
4. Treat UI nominal, connected, zero, or empty states as operator hints, not final broker truth.
5. Stop all runtimes and inspect broker state directly before and after any local smoke test that exercises strategy runtime controls.

## Readiness Blockers

The current blocking themes are:

- simulated-vs-broker-confirmed provenance is still incomplete across broader frontend/browser surfaces, even though dashboard trade truth, dashboard position sync truth, events-surface simulated-vs-broker-confirmed close wording, and strategy execution-feed simulated/local provenance now have explicit browser coverage
- backend/frontend enum parity is stronger for the covered vocabulary slice (`risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`), but broader operator-surface evidence is still incomplete even after the added events/live/control-plane/strategies/coverage/markets browser slice
- route-inventory and frontend-contract drift are now machine-guarded for the current route set, so this is no longer a present-tense blocker category; remaining route risk is broader broker-action/operator-evidence breadth rather than hypothetical future undocumented or raw routes
- current backend durable-audit coverage is now inventory-backed for the present mutation, broker-action, and safety-critical background path set; remaining best-effort events are intentional informational paths, and future broker-action/route risk is now handled by guard tests instead of remaining a present-tense backend blocker
- frontend operator truth now has selected browser/e2e coverage for stale, degraded, manual-review, passive-vs-mutation, simulated-vs-broker-confirmed, mutation-failure, events attention, test-only reset gating, telemetry degradation, strategy runtime controls, shortlist/watchlist mutation truth, and unknown freshness states across events/dashboard/live/risk/strategies/AIMEE/control-plane/coverage/markets, but broad browser/e2e coverage is still incomplete
- covered backend logging/API-error/domain-event redaction is now in place, covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position payloads now sanitize free-text and detail fields before commit, the current operator/API/events identifier boundary now exposes masked display plus stable fingerprint projections instead of raw broker/account/request/runtime/correlation strings, repo-level secret/history scan guardrails now block common local secret/SQLite/dump/test-artifact commits, dependency lock/audit tooling is now repeatable for Python and npm, and versioned Alembic migrations now have both SQLite drift checks and a CI-wired Postgres rehearsal path. Health and telemetry now aggregate the targeted operator degradation states across workers with explicit staleness and worker identity, while keeping non-target diagnostics clearly labelled as current-process only. Broader secrets hygiene, intentional raw internal authority fields, historical cleanup, and a fresh successful CI Postgres rehearsal run remain below readiness grade

The canonical blocker list is in [audit-status.md](audit-status.md).

## Known Risks

- Simulated/local execution and close provenance is not yet proved across broader frontend/browser operator surfaces outside the covered dashboard trade, dashboard position sync, events wording, and strategy execution-feed slices.
- Broader backend/frontend enum-parity proof is still incomplete even though the covered vocabulary slice now includes `risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`.
- Future route-inventory and contract drift is now guarded mechanically, but broader broker-action and operator-evidence breadth still needs review when new routes appear.
- The remaining backend audit risk is no longer “unknown current mutation/background paths”; it is future-path discipline plus broader operator/frontend breadth.
- Candidate-only strategy events are intentionally best-effort informational, not lifecycle audit proof, even when they remain useful for observability.
- Browser/e2e operator-state coverage is improved, including selected manual-review, control-plane mismatch, events attention/test-only truth, telemetry degradation, strategy runtime mutation truth, shortlist/watchlist mutation truth, and market-data fallback/stale/unknown freshness truth, but it is still too narrow for readiness claims.
- Database evolution now uses Alembic plus SQLite drift checks and a Postgres migration rehearsal, but existing unversioned non-SQLite databases still require explicit manual upgrade and some dialect-specific indexes still depend on targeted assertions rather than generic autogenerate comparison. The latest available CI run failed before the rehearsal step, so DB portability has not been freshly re-verified by the latest CI evidence.
- Python and npm dependency locking plus vulnerability gates are now repeatable, third-party Python dependencies can now be hash-verified, and backend/frontend SBOM generation now exists, but the editable local backend package remains outside hash enforcement and the repo still lacks broader non-Python/Node dependency scanning and stronger provenance attestation.
- Covered logs, mirrored domain events, IG adapter failures, and operator-facing API errors now redact tokens, account identifiers, broker references, raw adapter payloads, and tracebacks; covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position free-text and detail fields now redact the same patterns before commit; and the reviewed operator-facing identifier surfaces now show masked display plus stable fingerprints instead of raw broker/account/request/runtime/correlation strings. Required audit-write failures now also surface in health/telemetry as degraded state, and targeted degradation states now aggregate across workers with stale-expiry handling, but remaining readiness gaps still include raw identifier columns retained for lifecycle authority, broader secrets hygiene, and broader operator/frontend evidence. Intentional best-effort informational events are not counted as durable lifecycle audit proof.
- Repo-local guardrails now make it harder to commit `.env*` secrets, SQLite DBs, broker dumps, captured session tokens, logs, and Playwright/test artifacts, but historical repository cleanup and credential rotation still require manual action outside this repository.
- Secrets hygiene, historical repository scanning follow-through, and multi-process observability still need platform hardening.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- keep the checked-in route manifest and route-contract drift guard current as any new operator-critical routes are added
- browser/e2e evidence for degraded, stale, simulated, unknown, manual-review, and mutation-failure operator states
- browser/e2e evidence for broader events, mutation, provenance, and freshness permutations beyond the current selected slices
- a latest CI run in which the Postgres rehearsal actually executes its five tests with zero skips
- migration, dependency, redaction, identifier-minimization, and secrets controls that are strong enough for broker-connected operation
- stronger supply-chain provenance than the current hash-and-SBOM baseline, including editable-package attestation and broader dependency scanning
- regression tests for every fixed P0/P1 behaviour that still lacks route, frontend, or full-stack evidence

## 2026-06-01 Identifier Boundary Slice

This slice improves identifier minimization and operator-safe correlation, but it does not make the repository demo-safe or live-safe.

- Internal authority that remains raw by design:
  - broker/deal references used by reconciliation and later close authority
  - execution client request ids used by duplicate suppression and retry correlation
  - runtime ids and current broker position references used by recovery and later lifecycle joins
  - persisted domain-event correlation/runtime ids used for internal traceability
- What operators now see instead:
  - reviewed API surfaces return `{ display, fingerprint }` projections for broker account ids, broker references, client request ids, runtime ids, and event correlation/runtime ids
  - `display` is masked for human readability and `fingerprint` is stable for cross-surface correlation without exposing the raw value
  - the events console now filters correlation through `correlation_fingerprint`, not a raw correlation id
- What is forbidden:
  - `Authorization`, `CST`, `X-SECURITY-TOKEN`, session/header/token/password/api-key style fields must not survive persistence or serialization
  - new persisted identifier columns must be classified in the checked-in policy manifest before tests will pass
  - new operator-facing response fields must not serialize DB-only raw broker/account/deal/request/runtime/correlation identifiers without an explicit reviewed exception
- Current limits:
  - raw internal authority fields are intentionally retained in the database because removing or masking them there would break lifecycle correctness
  - current GitHub Actions evidence still does not include a post-fix successful five-test Postgres rehearsal with zero skips
  - repository-history cleanup and any needed credential rotation remain manual actions outside this code change

## 2026-06-01 Backend Lockfile And Lifecycle Guard Slice

This slice improves backend safety posture, but it does not make the repository live-safe or demo-safe.

- Backend lockfile gate:
  - the failing `Verify backend lockfiles` CI step was reproduced locally with `./scripts/check_backend_requirements.sh`
  - root cause was stale generated backend lockfiles caused by `scripts/compile_backend_requirements.sh` preserving existing transitive pins instead of forcing a fresh upgrade pass
  - the helper now compiles with `--upgrade`, and the refreshed runtime/dev plain plus hashed lockfiles now agree with the freshness check
  - after the fix, `./scripts/compile_backend_requirements.sh`, `./scripts/check_backend_requirements.sh`, `./scripts/verify_backend_dependency_integrity.sh`, and `backend/.venv/bin/pip-audit -r backend/requirements-hashed.txt --require-hashes` all passed locally; `pip-audit` reported `No known vulnerabilities found`
- Lifecycle terminal protection:
  - `TradeIntent` and `Execution` now use explicit centralized transition tables in `backend/app/services/lifecycle_rules.py`
  - terminal `TradeIntent` states are now classified as `REJECTED`, `CLOSED`, `FAILED`, `CANCELLED`, and `FORCED_RECONCILIATION_CLOSE`
  - terminal `Execution` statuses are now classified as `POSITION_OPENED`, `CLOSE_CONFIRMED`, `FAILED`, and `CANCELLED`
  - compatibility-only legacy `Execution` statuses are now classified as `SIGNAL_GENERATED`, `RISK_APPROVED`, `RISK_REJECTED`, and `CLOSE_REQUESTED`, and new writes of those values are rejected
  - invalid transitions are now rejected before any row mutation or transition audit event is written
  - same-state/idempotent writes remain allowed only where the existing workflows rely on them
  - failed execution retries now create a new attempt instead of reactivating a terminal failed row
  - incomplete and partial close paths remain close-admissible without writing misleading terminal states first and then reviving them
  - reconciliation now preserves `EXTERNAL_POSITION_ADOPTED` and `RECOVERED_POSITION_ATTACHED` provenance instead of flattening them into ordinary open-position state
- Tests and current result:
  - added `backend/tests/test_trade_lifecycle_transition_guards.py` for allowed transitions, representative invalid transitions, terminal reactivation rejection, same-state idempotence, legacy write rejection, reconciliation/recovery branches, and enum-classification guard coverage
  - local backend suite result after this slice: `backend/.venv/bin/pytest backend/tests -q` -> `533 passed, 5 skipped, 1 warning`
- CI/Postgres honesty:
  - latest available GitHub Actions run is still [26663279789](https://github.com/parker23b/codex-trading-app/actions/runs/26663279789), which failed on 2026-05-29 at `Verify backend lockfiles`
  - that run skipped `Migration and drift tests` and `Pytest`, so the Postgres rehearsal step was not reached there
  - no newer post-fix CI run is available yet from this workspace, so `AUDIT-DB-001` remains open and this repo still cannot claim a successful five-test CI Postgres rehearsal with zero skips

## 2026-05-21 Backend Audit Closure Slice

This remediation closes the current backend durable-audit inventory without pretending platform observability is finished.

- Current inventory classification:
  - `REQUIRED_DURABLE`: current mutation helpers, broker-action HTTP routes, strategy/deployment/recovery/reconciliation/coverage/Tier 2 background lifecycle events, and required broker-action service events
  - `SESSION_BOUND_DURABLE`: TradeIntent create/transition, Execution create/transition, and allocation-cycle completion
  - `BEST_EFFORT_INFORMATIONAL`: `strategy.entry_candidate`, `strategy.exit_candidate`, sessionless polling-health helper calls, and `api.request_failed` error journaling
  - `LEGACY/OBSOLETE`: none found in current app code
- Current-code gap found and fixed:
  - added direct evidence for `control_plane.reconciliation_cycle_completed` from the Tier 2 background loop
- Guardrails added:
  - a machine-checkable AST inventory of current backend audit write paths
  - guard tests blocking new unexpected direct `record_event()` use in audit-critical suites
  - guard tests limiting best-effort strategy and polling-health event families to the current allowlists
  - guard tests requiring the current broker-action HTTP routes to keep the existing authority-plus-audit pattern
- What is no longer a current backend blocker:
  - hypothetical future broker-action HTTP routes
  - hypothetical future background event families
  - intentional candidate-only/best-effort informational events
- What remains open:
  - broader frontend/operator visibility breadth
- New operator-visible observability state remains:
  - `/system/health` includes a `degradations` block for audit-write, polling-fallback, stream, and runtime degradation
  - `/system/telemetry` exposes explicit degradation booleans, counts, and reason codes
- Commands run for this closure slice:
  - `backend/.venv/bin/pytest backend/tests/test_audit_closure_inventory.py backend/tests/test_broker_action_http_authority.py -q` -> `19 passed`
  - `backend/.venv/bin/pytest backend/tests/test_mutation_audit_events.py backend/tests/test_decision_audit_events.py backend/tests/test_lifecycle_audit_events.py backend/tests/test_strategy_service.py backend/tests/test_control_plane_service.py backend/tests/test_runtime_recovery_service.py backend/tests/test_reconciliation_service.py backend/tests/test_coverage_allocator_service.py backend/tests/test_market_data_service.py -q` -> `149 passed`
  - `backend/.venv/bin/pytest backend/tests/test_health_service.py backend/tests/test_operational_telemetry_service.py backend/tests/test_http_route_harness.py -q` -> `71 passed`
  - `backend/.venv/bin/pytest backend/tests -q` -> `445 passed`
  - `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`
  - `git diff --check` -> `PASS`

This does not make the repository demo-safe or live-safe. It fixes `AUDIT-API-008` and `AUDIT-TEST-002` for the current backend path set, and it previously narrowed `AUDIT-OBS-001` to a platform observability gap rather than a current backend durable-audit coverage gap.

## 2026-05-29 Aggregated Observability Slice

This remediation adds a durable observability state model for supervised operation without pretending every telemetry field is now platform-global.

- Aggregated states now covered:
  - audit-write degradation
  - polling fallback
  - stale stream instruments
  - stream degradation
  - runtime degradation
  - runtime leadership / active worker identity
- Storage and aggregation design:
  - new `observabilitystate` table keyed by state kind, scope, and worker identity
  - each worker upserts its own current observation with `worker_id`, `hostname`, `process_id`, `source`, `observed_at`, `expires_at`, and JSON payload
  - `/system/health` keeps `details` as current-process diagnostics, while `degradations` now come from the aggregated observability view
  - `/system/telemetry` now exposes the aggregation mode, leader identity, local-vs-aggregated scope labels, and the current observation set
- Stale and expiry behavior:
  - audit-write degradation expires on the existing 5-minute health window
  - polling fallback, stream stale, stream connection, and runtime-paused observations expire on bounded TTLs derived from the existing heartbeat/polling/staleness settings
  - expired rows remain visible as stale observations and are not counted as current degraded truth
  - if aggregation cannot be loaded, the routes fall back to a clearly labelled `LOCAL_ONLY_FALLBACK` view instead of silently presenting local-only data as platform truth
- Tests added:
  - `backend/tests/test_observability_state_service.py`
  - `backend/tests/test_health_routes.py`
  - targeted updates in `backend/tests/test_health_service.py`, `backend/tests/test_operational_telemetry_service.py`, `backend/tests/test_database_migrations.py`, and `backend/tests/test_initialize_database.py`
- Commands run and results:
  - `backend/.venv/bin/pytest backend/tests/test_observability_state_service.py backend/tests/test_health_routes.py backend/tests/test_health_service.py backend/tests/test_operational_telemetry_service.py backend/tests/test_runtime_leadership_service.py backend/tests/test_market_data_service.py -q` -> `30 passed`
  - `backend/.venv/bin/pytest backend/tests/test_initialize_database.py backend/tests/test_database_migrations.py -q` -> `4 passed`
  - `backend/.venv/bin/pytest backend/tests -q` -> `449 passed`
  - `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`
  - `git diff --check` -> `PASS`
- Finding status after this slice:
  - `AUDIT-OBS-001`: fixed for the targeted backend/platform degradation aggregation scope
  - remaining limitations are explicit local-process diagnostics outside the targeted state set plus broader frontend/operator readiness gaps, not hidden single-process degradation truth

## Dependency Hygiene Status

The repository now has repeatable dependency commands:

- `scripts/compile_backend_requirements.sh`
- `./scripts/check_backend_requirements.sh`
- `./scripts/verify_backend_dependency_integrity.sh`
- `./scripts/generate_sbom.sh backend`
- `./scripts/generate_sbom.sh frontend`
- `backend/.venv/bin/pip-audit -r backend/requirements-hashed.txt --require-hashes`
- `./scripts/check_frontend_dependencies.sh`

Current posture as of 2026-06-01:

- backend runtime/transitive dependencies are pinned in `backend/requirements.txt`
- backend dev/test tooling is separated through `backend/requirements-dev.in` and pinned in `backend/requirements-dev.txt`
- backend also has hash-bearing third-party lockfiles in `backend/requirements-hashed.txt` and `backend/requirements-dev-hashed.txt`
- `scripts/compile_backend_requirements.sh` now compiles with `--upgrade` so the checked-in generator matches the freshness check instead of silently preserving stale transitive pins
- CI now verifies backend lock freshness before install, installs third-party Python packages through `--require-hashes`, uploads backend/frontend SBOM artifacts, and fails on the hashed-lock `pip-audit` command
- CI and pre-push now fail on frontend lockfile inconsistency, `npm audit`, and `knip`
- the current Python audit result is `No known vulnerabilities found`
- the current npm audit result is `found 0 vulnerabilities`
- the current frontend dependency wrapper passes; `knip` still emits one non-failing config hint for `@types/node` ignore housekeeping
- generated SBOMs go to ignored `artifacts/sbom/` files and are uploaded from CI rather than committed
- hash verification intentionally covers only third-party Python dependencies; the editable local backend package is installed separately with `pip install --no-deps -e .`

Resolved dependency findings in this slice:

- Python `aiohttp` updated from `3.13.3` to `3.13.5` through the `lightstreamer-client-lib` dependency chain
- Python `idna` updated from `3.11` to `3.17`
- Python `starlette` updated from `1.0.0` to `1.2.1`, clearing `PYSEC-2026-161`
- Python `fastapi` updated from `0.136.1` to `0.136.3`
- Python `uvicorn` updated from `0.47.0` to `0.48.0`
- Python `httptools` updated from `0.7.1` to `0.8.0`
- Python `sqlalchemy` updated from `2.0.49` to `2.0.50`
- Python `click` updated from `8.4.0` to `8.4.1`
- Python `urllib3` updated from `2.6.3` to `2.7.0`
- dev-only Python `pytest` updated from `9.0.2` to `9.0.3`
- dev-only Python `coverage` updated from `7.14.0` to `7.14.1`
- dev-only Python `ruff` updated from `0.15.14` to `0.15.15`
- dev-only Python `virtualenv` updated from `21.4.1` to `21.4.2`
- frontend `next` updated in the lockfile from `15.5.15` to `15.5.18`

Remaining dependency/supply-chain gaps:

- editable local backend installs cannot be hash-verified under pip and remain intentionally outside the third-party hash boundary
- virtualenv bootstrap tooling (`pip`/`setuptools`) is still outside the repo-managed hash boundary
- there is SBOM export now, but no stronger provenance attestation/signing workflow yet
- host/container/system-package dependencies are not audited here
- this does not change the separate database migration/readiness gap

## Database Migration Status

The repository now has repeatable schema commands:

- `cd backend && .venv/bin/alembic current`
- `cd backend && .venv/bin/alembic upgrade head`
- `cd backend && .venv/bin/python -m pytest tests/test_database_migrations.py tests/test_initialize_database.py -q`
- `cd backend && POSTGRES_REHEARSAL_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres .venv/bin/python -m pytest tests/test_postgres_migration_rehearsal.py -m postgres_rehearsal -q`

Current posture as of 2026-06-01:

- startup no longer treats `create_all()` as the migration system; `backend/app/db/init_db.py` now runs versioned Alembic upgrades through `backend/app/db/migrations.py`
- `backend/alembic/versions/20260521_01_initial_schema.py` and `backend/alembic/versions/20260529_01_observability_state.py` now create schema from model-owned metadata instead of SQLite-oriented raw DDL, so the versioned migration path is portable enough to rehearse on Postgres rather than only infer from SQLite
- backend test DB fixtures now start from a migrated SQLite template instead of raw `SQLModel.metadata.create_all()`
- the old SQLite patch helpers were not kept as the normal runtime path; they were moved behind an explicit legacy SQLite compatibility upgrade for pre-migration local databases only
- migration tests now prove empty SQLite upgrade, schema-vs-metadata drift checks, critical index presence, and `StrategyRuntimeState.control_mode` / `runtime_mode` nullability-default normalization
- Postgres rehearsal tests now prove:
  - empty Postgres upgrade to `head`
  - metadata-aligned schema after migration, with targeted assertions for partial/expression/descending indexes
  - active `TradeIntent` uniqueness protection
  - runtime control/runtime-mode nullability and defaults
  - `runtimelease`
  - `observabilitystate`
  - lifecycle and audit tables including `execution`, `position`, `trade`, `reconciliationevent`, `domain_events`, and `allocationalert`
  - one versioned transition from `20260521_01` to `20260529_01`
  - refusal of existing unversioned non-SQLite databases without auto-stamp
- CI now runs both the fast SQLite migration suite and a Postgres service-container rehearsal; pre-push stays SQLite-only so ordinary local loops do not require Docker or a running Postgres server
- the CI Postgres rehearsal now runs through `scripts/run_postgres_rehearsal.py`, which fails the job if the rehearsal suite skips unexpectedly even though `POSTGRES_REHEARSAL_ADMIN_URL` should be present

Remaining database risks:

- existing unversioned non-SQLite databases are intentionally not auto-stamped or auto-rewritten; the required path is to create a fresh versioned database with Alembic and move data by manual export/import or a reviewed one-off migration
- generic Alembic autogenerate comparison still does not fully prove partial/expression/descending indexes across dialects, so those structures remain covered by targeted assertions rather than by a pure metadata diff
- this improves schema portability evidence materially, but it does not claim full production-grade database portability, historical data migration tooling, or live/demo readiness

Commands run for this slice on 2026-06-01:

- `cd backend && .venv/bin/python -m pytest tests/test_database_migrations.py tests/test_initialize_database.py -q` -> `4 passed`
- `cd backend && .venv/bin/python -m pytest tests/test_postgres_migration_rehearsal.py -q` -> `5 skipped` locally because `POSTGRES_REHEARSAL_ADMIN_URL` was not set and no supported local Postgres server was available in this environment
- `cd backend && .venv/bin/python -m pytest tests -q` -> `533 passed, 5 skipped, 1 warning`
- `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`
- `git diff --check` -> passed
- Latest available CI result checked on 2026-06-01: [Repo Audit run 26663279789](https://github.com/parker23b/codex-trading-app/actions/runs/26663279789) failed in `backend-audit` at `Verify backend lockfiles`, and the later `Migration and drift tests` plus `Pytest` steps were skipped. No newer post-fix CI run is available yet from this workspace. The latest available CI evidence therefore still did not execute the five Postgres rehearsal tests with zero skips, so this repo should not claim fresh CI verification for the DB portability slice.

## Secrets Hygiene Status

The repository now has two repeatable scan commands:

- `python3 scripts/repo_secrets_scan.py --mode working-tree`
- `python3 scripts/repo_secrets_scan.py --mode history --allow-history-findings`

Current posture as of 2026-05-21:

- working-tree scan returned `No findings.`
- history scan still reports `backend/trading_platform.db` and `trading_platform.db`
- local backend env files can still contain real IG/API/operator credentials and must remain unshared
- frontend `NEXT_PUBLIC_*` values are browser-visible transport/config values and must not be treated as secret storage

Manual actions still required:

- rotate any exposed local or demo credentials if this repo or workstation state was shared
- purge historical DB blobs and any other sensitive commits before publishing or broadly sharing the repository
- do not claim the repository history is clean until a full history rewrite or equivalent cleanup has actually been completed and verified

Track progress in [audit-status.md](audit-status.md).

## 2026-05-21 Enum And Provenance Parity Slice

This remediation covered the authoritative vocabulary slice for:

- `risk_truth_confidence`
- `BrokerExecutionSource`
- `broker_sync_status`
- `ExecutionStatus`
- `TradeIntentState`
- frontend unknown/degraded/manual-review labels for those surfaces

Mismatches fixed in this slice:

- backend `broker_sync_status` is now an explicit enum instead of an undocumented string field
- frontend trade close provenance mapping is now centralized instead of duplicated across tables
- frontend execution and allocation intent lifecycle fields now use explicit shared unions before widening to `string` for unsupported backend values
- unsupported backend provenance/status values now fall back to explicit unknown/degraded labels instead of nominal, exact, or broker-confirmed-looking UI
- dashboard positions now expose simulated local fill provenance explicitly rather than leaving the sync state implicit

Tests added or updated in this slice:

- `backend/tests/test_operator_vocabulary.py`
- `frontend/tests/operator-vocabulary-parity.test.mjs`
- `frontend/tests/trades-contract-parity.test.mjs`
- `frontend/e2e/operator-truth.spec.mjs`
- `frontend/e2e/support/scenarios.mjs`

Commands run on 2026-05-21:

- `backend/.venv/bin/pytest backend/tests/test_operator_vocabulary.py backend/tests/test_trade_route_contracts.py backend/tests/test_execution_routes.py backend/tests/test_strategy_service.py -q` -> `66 passed`
- `cd frontend && npm run typecheck` -> passed
- `cd frontend && npm run test:frontend` -> `70 passed`
- `cd frontend && node --test --test-name-pattern "AUDIT-005|AUDIT-UI-002|UI-005|BROKER-014|AUDIT-LIFE-005|API-003|API-004|ARCH-009" tests/*.test.mjs` -> `21 passed`, `49 skipped`
- `cd frontend && npm run test:e2e -- --grep "AUDIT-LIFE-005|AUDIT-UI-006 dashboard shows stale feed truth and keeps simulated closes distinct from broker-confirmed closes|AUDIT-UI-002 risk view keeps unavailable and provisional truth from collapsing into exact risk"` -> `3 passed`
- `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`

Finding status after this slice:

- `AUDIT-005`: narrowed, not fixed globally
- `AUDIT-UI-002`: narrowed, not fixed globally
- `AUDIT-LIFE-005`: narrowed with one additional browser-covered simulated/local provenance surface

Remaining enum/provenance gaps:

- broader browser coverage across control-plane, events, markets, and additional simulated/local surfaces
- additional operator-facing vocabularies outside this slice
- any future frontend-consumed route family that bypasses the shared vocabulary helpers and parity tests

## 2026-05-21 Browser Operator Truth Expansion

This slice expands browser-level operator truth coverage without claiming full frontend readiness.

- Scenarios added:
  - events attention state for audit-write degradation
  - hidden-by-default test-only destructive reset, plus explicit enable path with visible destructive/test-only copy
  - live telemetry degradation truth for audit-write, polling fallback, stale stream, stream degradation, runtime degradation, and explicit local-vs-aggregated telemetry scope
  - control-plane governance mutation pending/error truth with backend `detail` preservation
  - strategies execution-feed blocked-entry/no-order-attempt truth
  - coverage stale-stream truth distinct from polling fallback and healthy streaming
- Surfaces covered:
  - `events`
  - `live`
  - `control-plane`
  - `strategies`
  - `coverage`
- Fixtures used:
  - explicit Playwright scenario fixtures in `frontend/e2e/support/scenarios.mjs`
  - event fixtures with severity, correlation, lifecycle references, audit degradation payloads, and simulated-vs-broker-confirmed wording
  - telemetry fixtures with explicit degradation booleans, counts, reason codes, and per-process limitation copy
  - delayed mutation responses for pending-plus-error control-plane flows
  - stale vs polling-fallback feed-state fixtures with no healthy default fallback objects
- Finding status after this slice:
  - `AUDIT-UI-006`: narrowed, still open
  - `AUDIT-UI-004`: narrowed, still open
  - `AUDIT-UI-002`: narrowed, still open
  - `AUDIT-LIFE-005`: narrowed, still open
  - `AUDIT-005`: narrowed, still open
  - `AUDIT-OBS-001`: fixed for the targeted backend aggregation slice; broader operator/frontend readiness work remains elsewhere
- Remaining frontend/browser gaps:
  - broader events route-contract and event-detail breadth
  - strategy start/stop, shortlist/watchlist, and other mutation success/retry/refresh permutations
  - additional simulated/local provenance surfaces beyond the covered dashboard and events slices
  - broader freshness/unknown/manual-review permutations across dashboard, risk, and live summaries
  - complete browser breadth for all operator-critical vocabularies and enum families

## 2026-06-01 Operator Control Truth Slice

This slice expands operator-control and truthfulness evidence without claiming frontend readiness.

- Controls covered:
  - strategy runtime start
  - strategy runtime stop with open-risk disclosure
  - shortlist add/remove
  - strategy-watchlist add/remove
  - strategy execution-feed source/status labels
  - coverage freshness downgrade for missing tick timestamps
- Scenarios added:
  - strategy start pending failure with backend `detail`
  - strategy start success-followed-by-refresh-failure
  - explicit strategy start disabled reason when launch truth is unavailable
  - strategy stop open-risk confirmation and side-effect disclosure
  - strategy stop failure with backend `detail`
  - strategy execution simulated/local provenance beyond dashboard and events
  - shortlist mutation failure plus retry
  - strategy-watchlist add success-followed-by-refresh-failure
  - strategy-watchlist remove success only after refreshed backend truth
  - coverage unknown timestamp freshness downgrade
- Fixtures used:
  - explicit Playwright scenarios in `frontend/e2e/support/scenarios.mjs`
  - no healthy default fallback objects
  - delayed mutation responses for pending-state assertions
  - sequential mutation-plus-refresh outcomes for retry and refresh-failure truth
  - strategy execution fixtures with explicit `execution_source` / `close_execution_source`
  - coverage feed-state fixtures that separate stale, polling fallback, and timestamp-unknown stream truth
- Backend-detail and refresh-truth evidence:
  - operator-visible mutation errors preserve backend `detail` for strategy start, strategy stop, and shortlist failure paths
  - strategy start, strategy stop, shortlist, and strategy-watchlist mutations now avoid clean success copy until refreshed backend truth returns
  - refresh failures remain visible as warnings instead of success
  - stop runtime now explicitly states that stopping a runtime does not imply broker-confirmed open risk is flat
  - watchlist/shortlist state stays framed as operator interest/coverage truth, not trading approval or autonomous deployment approval
- Provenance and freshness states covered:
  - strategy execution feed now uses shared vocabulary helpers on a browser-covered surface
  - simulated/local provenance is now browser-covered on strategy execution rows as well as earlier dashboard/events slices
  - coverage with missing tick freshness now renders `Unknown` / `Stream state unknown` rather than healthy live truth
- Commands run and results:
  - `cd frontend && npm run test:e2e -- --grep "AUDIT-|FLOW-"` -> `30 passed`
  - `cd frontend && npm run test:frontend` -> `72 passed`
  - `cd frontend && npm run typecheck` -> passed
  - `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`
  - `git diff --check` -> `PASS`
- Finding status after this slice:
  - `AUDIT-UI-004`: narrowed, still open
  - `AUDIT-UI-006`: narrowed, still open
  - `AUDIT-UI-002`: narrowed, still open
  - `AUDIT-LIFE-005`: narrowed, still open
  - `AUDIT-005`: narrowed, still open
  - `AUDIT-UI-005`: narrowed, still open
