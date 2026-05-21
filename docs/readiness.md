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

- simulated-vs-broker-confirmed provenance is still incomplete across broader frontend/browser surfaces, even though dashboard trade truth and dashboard position sync truth now have explicit simulated/local browser coverage
- backend/frontend enum parity is stronger for the covered vocabulary slice (`risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`), but broader operator-surface evidence is still incomplete
- any future operator-critical raw dict/list routes still need explicit contract ownership even though the currently known frontend-consumed route boundary is now modeled
- durable audit preservation is still incomplete for remaining broker-action HTTP authority and background-event paths outside the covered entry/close, runtime-start/control-plane-reconcile scheduler, autonomous deployment-reconcile/runtime-recovery startup-authority, and selected recovery/reconciliation slices
- frontend operator truth now has selected browser/e2e coverage for stale, degraded, manual-review, passive-vs-mutation, simulated-vs-broker-confirmed, and mutation-failure states across dashboard/live/risk/strategies/AIMEE/control-plane/coverage/markets, but broad browser/e2e coverage is still incomplete
- covered backend logging/API-error/domain-event redaction is now in place, covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position payloads now sanitize free-text and detail fields before commit, repo-level secret/history scan guardrails now block common local secret/SQLite/dump/test-artifact commits, dependency lock/audit tooling is now repeatable for Python and npm, and versioned Alembic migrations plus SQLite drift checks now exist, but broader secrets hygiene, supply-chain provenance, non-SQLite migration evidence, functional raw-identifier columns, historical cleanup, and durable observability remain below readiness grade

The canonical blocker list is in [audit-status.md](audit-status.md).

## Known Risks

- Simulated/local execution and close provenance is not yet proved across broader frontend/browser operator surfaces outside the covered dashboard trade and dashboard position sync slices.
- Broader backend/frontend enum-parity proof is still incomplete even though the covered vocabulary slice now includes `risk_truth_confidence`, `BrokerExecutionSource`, `broker_sync_status`, `ExecutionStatus`, and `TradeIntentState`.
- Future raw operator-critical routes would make contract drift easier to miss even though the currently known frontend-consumed route boundary is now modeled.
- Remaining broker-action HTTP authority and mutation/background paths still need durable audit-preservation proof at the route/background boundary beyond the covered runtime-start/control-plane-reconcile scheduler slice, the autonomous deployment-reconcile startup slice, and the runtime-recovery startup slice.
- Browser/e2e operator-state coverage is improved, including selected manual-review, control-plane mismatch, and market-data fallback truth, but it is still too narrow for readiness claims.
- Database evolution now uses Alembic plus migration/drift tests, but existing unversioned non-SQLite databases still require explicit manual upgrade and SQLite expression-index drift still depends on targeted checks.
- Python and npm dependency locking plus vulnerability gates are now repeatable, but the repo still lacks stronger supply-chain controls such as hash-verified Python installs, SBOM/provenance generation, and non-Python/Node dependency scanning.
- Covered logs, mirrored domain events, IG adapter failures, and operator-facing API errors now redact tokens, account identifiers, broker references, raw adapter payloads, and tracebacks, and covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position free-text and detail fields now redact the same patterns before commit. Remaining readiness gaps still include raw identifier columns required for lifecycle authority, broader secrets hygiene, and durable observability.
- Repo-local guardrails now make it harder to commit `.env*` secrets, SQLite DBs, broker dumps, captured session tokens, logs, and Playwright/test artifacts, but historical repository cleanup and credential rotation still require manual action outside this repository.
- Secrets hygiene, historical repository scanning follow-through, and multi-process observability still need platform hardening.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- complete modeled/documented contracts for any future operator-critical raw response families
- durable audit-preservation proof for remaining mutation, broker-action, and background-event paths beyond the covered entry/close, runtime-start/control-plane-reconcile scheduler, autonomous deployment-reconcile/runtime-recovery startup-authority, and selected recovery/reconciliation slices
- browser/e2e evidence for degraded, stale, simulated, unknown, manual-review, and mutation-failure operator states
- migration, dependency, redaction, identifier-minimization, and secrets controls that are strong enough for broker-connected operation
- stronger supply-chain provenance than the current lock-and-audit baseline, including Python hash verification or an equivalent integrity mechanism plus broader dependency scanning
- regression tests for every fixed P0/P1 behaviour that still lacks route, frontend, or full-stack evidence

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
