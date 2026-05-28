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

- simulated-vs-broker-confirmed provenance is still incomplete across broader frontend/browser surfaces, even though dashboard trade truth, dashboard position sync truth, and events-surface simulated-vs-broker-confirmed close wording now have explicit browser coverage
- backend/frontend enum parity is stronger for the covered vocabulary slice (`risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`), but broader operator-surface evidence is still incomplete even after the added events/live/control-plane/strategies/coverage browser slice
- any future operator-critical raw dict/list routes still need explicit contract ownership even though the currently known frontend-consumed route boundary is now modeled
- current backend durable-audit coverage is now inventory-backed for the present mutation, broker-action, and safety-critical background path set; remaining best-effort events are intentional informational paths, and future broker-action/route risk is now handled by guard tests instead of remaining a present-tense backend blocker
- frontend operator truth now has selected browser/e2e coverage for stale, degraded, manual-review, passive-vs-mutation, simulated-vs-broker-confirmed, mutation-failure, events attention, test-only reset gating, and telemetry degradation states across events/dashboard/live/risk/strategies/AIMEE/control-plane/coverage/markets, but broad browser/e2e coverage is still incomplete
- covered backend logging/API-error/domain-event redaction is now in place, covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position payloads now sanitize free-text and detail fields before commit, repo-level secret/history scan guardrails now block common local secret/SQLite/dump/test-artifact commits, dependency lock/audit tooling is now repeatable for Python and npm, and versioned Alembic migrations plus SQLite drift checks now exist. Health and telemetry now expose explicit audit-write, polling-fallback, stale-stream, stream-degraded, and runtime-degraded state, but broader secrets hygiene, supply-chain provenance, non-SQLite migration evidence, functional raw-identifier columns, historical cleanup, and durable multi-process observability remain below readiness grade

The canonical blocker list is in [audit-status.md](audit-status.md).

## Known Risks

- Simulated/local execution and close provenance is not yet proved across broader frontend/browser operator surfaces outside the covered dashboard trade, dashboard position sync, and narrow events wording slices.
- Broader backend/frontend enum-parity proof is still incomplete even though the covered vocabulary slice now includes `risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`.
- Future raw operator-critical routes would make contract drift easier to miss even though the currently known frontend-consumed route boundary is now modeled.
- The remaining backend audit risk is no longer “unknown current mutation/background paths”; it is future-path discipline plus platform observability aggregation.
- Candidate-only strategy events are intentionally best-effort informational, not lifecycle audit proof, even when they remain useful for observability.
- Browser/e2e operator-state coverage is improved, including selected manual-review, control-plane mismatch, events attention/test-only truth, telemetry degradation, and market-data fallback/stale truth, but it is still too narrow for readiness claims.
- Database evolution now uses Alembic plus migration/drift tests, but existing unversioned non-SQLite databases still require explicit manual upgrade and SQLite expression-index drift still depends on targeted checks.
- Python and npm dependency locking plus vulnerability gates are now repeatable, but the repo still lacks stronger supply-chain controls such as hash-verified Python installs, SBOM/provenance generation, and non-Python/Node dependency scanning.
- Covered logs, mirrored domain events, IG adapter failures, and operator-facing API errors now redact tokens, account identifiers, broker references, raw adapter payloads, and tracebacks, and covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position free-text and detail fields now redact the same patterns before commit. Required audit-write failures now also surface in health/telemetry as degraded state, but remaining readiness gaps still include raw identifier columns required for lifecycle authority, broader secrets hygiene, and durable multi-process observability. Intentional best-effort informational events are not counted as durable lifecycle audit proof.
- Repo-local guardrails now make it harder to commit `.env*` secrets, SQLite DBs, broker dumps, captured session tokens, logs, and Playwright/test artifacts, but historical repository cleanup and credential rotation still require manual action outside this repository.
- Secrets hygiene, historical repository scanning follow-through, and multi-process observability still need platform hardening.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- complete modeled/documented contracts for any future operator-critical raw response families
- multi-process/platform observability that aggregates audit-write, polling-fallback, stale-stream, and runtime degradation across workers rather than only within the current process
- browser/e2e evidence for degraded, stale, simulated, unknown, manual-review, and mutation-failure operator states
- browser/e2e evidence for broader events, mutation, provenance, and freshness permutations beyond the current selected slices
- migration, dependency, redaction, identifier-minimization, and secrets controls that are strong enough for broker-connected operation
- stronger supply-chain provenance than the current lock-and-audit baseline, including Python hash verification or an equivalent integrity mechanism plus broader dependency scanning
- regression tests for every fixed P0/P1 behaviour that still lacks route, frontend, or full-stack evidence

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
  - multi-process/platform observability aggregation
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

This does not make the repository demo-safe or live-safe. It fixes `AUDIT-API-008` and `AUDIT-TEST-002` for the current backend path set, and it narrows `AUDIT-OBS-001` to a platform observability gap rather than a current backend durable-audit coverage gap.

## Dependency Hygiene Status

The repository now has repeatable dependency commands:

- `scripts/compile_backend_requirements.sh`
- `./scripts/check_backend_requirements.sh`
- `backend/.venv/bin/pip-audit`
- `cd frontend && npm run audit:lockfile`
- `cd frontend && npm run audit:deps`
- `cd frontend && npm run audit:unused`

Current posture as of 2026-05-21:

- backend runtime/transitive dependencies are pinned in `backend/requirements.txt`
- backend dev/test tooling is separated through `backend/requirements-dev.in` and pinned in `backend/requirements-dev.txt`
- CI now verifies backend lock freshness before install and fails on `pip-audit`
- CI and pre-push now fail on frontend lockfile inconsistency, `npm audit`, and `knip`
- the current Python audit result is `No known vulnerabilities found` apart from the expected local-package skip for `trading-platform-backend`
- the current npm audit result is `found 0 vulnerabilities`
- the current frontend unused-dependency check passes; `tailwindcss` is intentionally retained as a CSS-side dependency and documented in `frontend/knip.json`

Resolved dependency findings in this slice:

- Python `aiohttp` updated from `3.13.3` to `3.13.5` through the `lightstreamer-client-lib` dependency chain
- Python `idna` updated from `3.11` to `3.15`
- Python `urllib3` updated from `2.6.3` to `2.7.0`
- dev-only Python `pytest` updated from `9.0.2` to `9.0.3`
- frontend `next` updated in the lockfile from `15.5.15` to `15.5.18`

Remaining dependency/supply-chain gaps:

- Python installs are pinned but not hash-verified
- there is no SBOM/provenance export or attestation workflow yet
- host/container/system-package dependencies are not audited here
- this does not change the separate database migration/readiness gap

## Database Migration Status

The repository now has repeatable schema commands:

- `cd backend && .venv/bin/alembic current`
- `cd backend && .venv/bin/alembic upgrade head`
- `cd backend && .venv/bin/python -m pytest tests/test_database_migrations.py tests/test_initialize_database.py -q`

Current posture as of 2026-05-21:

- startup no longer treats `create_all()` as the migration system; `backend/app/db/init_db.py` now runs versioned Alembic upgrades through `backend/app/db/migrations.py`
- `backend/alembic/versions/20260521_01_initial_schema.py` captures the current intended SQLModel schema, including the active `TradeIntent` partial unique index
- backend test DB fixtures now start from a migrated SQLite template instead of raw `SQLModel.metadata.create_all()`
- the old SQLite patch helpers were not kept as the normal runtime path; they were moved behind an explicit legacy SQLite compatibility upgrade for pre-migration local databases only
- migration tests now prove empty SQLite upgrade, schema-vs-metadata drift checks, critical index presence, and `StrategyRuntimeState.control_mode` / `runtime_mode` nullability-default normalization
- CI and pre-push now run the migration/drift test file explicitly before the broader backend suite

Remaining database risks:

- existing unversioned non-SQLite databases are intentionally not auto-stamped or auto-rewritten
- SQLite expression/descending index comparison still needs explicit assertions because Alembic autogenerate cannot round-trip those structures cleanly
- this PR does not add a Postgres CI database or production migration rehearsal

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
  - live telemetry degradation truth for audit-write, polling fallback, stale stream, stream degradation, runtime degradation, and per-process telemetry limitation
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
  - `AUDIT-OBS-001`: narrowed for operator visibility, still open as a multi-process/platform gap
- Remaining frontend/browser gaps:
  - broader events route-contract and event-detail breadth
  - strategy start/stop, shortlist/watchlist, and other mutation success/retry/refresh permutations
  - additional simulated/local provenance surfaces beyond the covered dashboard and events slices
  - broader freshness/unknown/manual-review permutations across dashboard, risk, and live summaries
  - complete browser breadth for all operator-critical vocabularies and enum families
