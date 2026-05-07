# Readiness And Safe Usage

InvestMate is **not ready for live or demo broker dealing**.

Use this repository for local development, UI review, strategy research, broker-read investigation, and smoke testing only. Keep `IG_TRADING_ENABLED=false`. Do not enable real broker dealing until the P0 readiness blockers in [audit-status.md](audit-status.md) are fixed and verified.

## Current Safe Posture

Safe local use means:

1. Keep `IG_TRADING_ENABLED=false`.
2. Use IG credentials only for broker-read investigation, such as auth, positions, account state, market metadata, and stream health.
3. Run one local backend process for smoke testing.
4. Avoid multi-worker or repeated reload scenarios when exercising runtime controls.
5. Treat `/testing/reset-history` as destructive.
6. Treat UI zero, nominal, connected, or empty states as operator hints, not final broker truth.
7. Stop all runtimes and inspect broker state directly before and after any local smoke test that exercises strategy runtime controls.

## Readiness Blockers

The blocking themes are:

- broker acknowledgement, timeout, or confirmation ambiguity can be represented too strongly as exact success or failure
- failed or ambiguous close paths can strand still-open risk behind a terminal intent state
- stopped-runtime recovery can skip adoption evidence for broker-confirmed open exposure
- unknown broker market status can fail open in some paths
- `/testing/reset-history` and other mutation routes do not yet have a production-grade backend auth boundary
- reload or multi-worker startup can duplicate runtime, market-data, streaming, or strategy-processing loops
- route, frontend, broker-fake, domain-event, dependency, database, and observability evidence is still incomplete for P0/P1 behaviour

The canonical list is in [audit-status.md](audit-status.md).

## Known Risks

- Backend mutation and broker-adjacent routes do not yet have a production-grade authentication and authorization boundary.
- CORS is permissive for credentialed localhost origins.
- `/testing/reset-history` is always registered and can delete trading, review, runtime, reconciliation, and domain-event history.
- Broker acknowledgement, timeout, partial-fill, and confirmation ambiguity are not fully modeled as separate reconciliation/manual-review states.
- Startup recovery can miss broker-confirmed open risk when persisted runtime mode is `STOPPED`.
- Market-status handling and fake defaults still need stronger fail-closed coverage for unknown or unrecognized broker states.
- Runtime, market-data, streaming, and strategy loops are guarded in-process, but not by a cross-process leader lock.
- Database evolution currently relies on `create_all()` plus SQLite patch helpers rather than versioned migrations.
- Python dependency locking and dependency-vulnerability gates are not yet production-grade.
- Logs and domain events need a stronger redaction boundary before broker/account payloads are safe to persist broadly.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- explicit broker-neutral pending, timeout, and ambiguous execution states
- close retry/recovery paths that preserve open-risk authority
- startup recovery that records broker-confirmed open exposure even when persisted runtime state is stopped
- fail-closed market-status behavior for missing or unknown broker states
- backend authentication and production gating for mutation and test-only routes
- cross-process runtime leadership or durable leases
- regression tests for the fixed P0/P1 behaviours
- operator UI evidence for degraded, unknown, stale, fallback, simulated, and manual-review states

Track progress in [audit-status.md](audit-status.md).
