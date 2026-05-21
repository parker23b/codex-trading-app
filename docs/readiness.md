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

- simulated-vs-broker-confirmed provenance is still incomplete across broader frontend/browser surfaces
- the spec coverage matrix still does not comprehensively map every P0/P1 boundary and surface requirement
- `risk_truth_confidence` now has an authoritative backend/frontend contract, but broader enum-parity and operator-surface evidence are still incomplete
- any future operator-critical raw dict/list routes still need explicit contract ownership even though the currently known frontend-consumed route boundary is now modeled
- durable audit preservation is still incomplete for remaining broker-action HTTP authority and background-event paths outside the covered entry/close, runtime-start/control-plane-reconcile scheduler, autonomous deployment-reconcile/runtime-recovery startup-authority, and selected recovery/reconciliation slices
- frontend operator truth now has selected browser/e2e coverage for stale, degraded, manual-review, passive-vs-mutation, simulated-vs-broker-confirmed, and mutation-failure states across dashboard/live/risk/strategies/AIMEE/control-plane/coverage/markets, but broad browser/e2e coverage is still incomplete
- covered backend logging/API-error/domain-event redaction is now in place, covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position payloads now sanitize free-text and detail fields before commit, and repo-level secret/history scan guardrails now block common local secret/SQLite/dump/test-artifact commits, but broader secrets hygiene, dependency locking, migrations, functional raw-identifier columns, historical cleanup, and durable observability remain below readiness grade

The canonical blocker list is in [audit-status.md](audit-status.md).

## Known Risks

- Simulated/local execution and close provenance is not yet proved across broader frontend/browser operator surfaces.
- Broader backend/frontend enum-parity proof is still incomplete even though `risk_truth_confidence` now has a central contract.
- Future raw operator-critical routes would make contract drift easier to miss even though the currently known frontend-consumed route boundary is now modeled.
- Remaining broker-action HTTP authority and mutation/background paths still need durable audit-preservation proof at the route/background boundary beyond the covered runtime-start/control-plane-reconcile scheduler slice, the autonomous deployment-reconcile startup slice, and the runtime-recovery startup slice.
- Browser/e2e operator-state coverage is improved, including selected manual-review, control-plane mismatch, and market-data fallback truth, but it is still too narrow for readiness claims.
- Database evolution currently relies on `create_all()` plus SQLite patch helpers rather than versioned migrations.
- Python dependency locking and dependency-vulnerability gates are not yet production-grade.
- Covered logs, mirrored domain events, IG adapter failures, and operator-facing API errors now redact tokens, account identifiers, broker references, raw adapter payloads, and tracebacks, and covered persisted execution/intent/allocation/reconciliation/runtime-recovery/trade/position free-text and detail fields now redact the same patterns before commit. Remaining readiness gaps still include raw identifier columns required for lifecycle authority, broader secrets hygiene, and durable observability.
- Repo-local guardrails now make it harder to commit `.env*` secrets, SQLite DBs, broker dumps, captured session tokens, logs, and Playwright/test artifacts, but historical repository cleanup and credential rotation still require manual action outside this repository.
- Secrets hygiene, historical repository scanning follow-through, and multi-process observability still need platform hardening.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- complete modeled/documented contracts for any future operator-critical raw response families
- durable audit-preservation proof for remaining mutation, broker-action, and background-event paths beyond the covered entry/close, runtime-start/control-plane-reconcile scheduler, autonomous deployment-reconcile/runtime-recovery startup-authority, and selected recovery/reconciliation slices
- browser/e2e evidence for degraded, stale, simulated, unknown, manual-review, and mutation-failure operator states
- migration, dependency, redaction, identifier-minimization, and secrets controls that are strong enough for broker-connected operation
- regression tests for every fixed P0/P1 behaviour that still lacks route, frontend, or full-stack evidence

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
