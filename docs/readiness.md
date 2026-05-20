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
- durable audit preservation is still incomplete for broader broker-action HTTP authority and remaining background-event paths outside the covered entry/close/recovery/reconciliation slices
- frontend operator truth is still missing broad browser/e2e coverage for degraded, unknown, passive-vs-mutation, and mutation-failure states
- logging redaction, secrets hygiene, dependency locking, migrations, and durable observability remain below readiness grade

The canonical blocker list is in [audit-status.md](audit-status.md).

## Known Risks

- Simulated/local execution and close provenance is not yet proved across broader frontend/browser operator surfaces.
- Broader backend/frontend enum-parity proof is still incomplete even though `risk_truth_confidence` now has a central contract.
- Future raw operator-critical routes would make contract drift easier to miss even though the currently known frontend-consumed route boundary is now modeled.
- Broader broker-action HTTP authority and remaining mutation/background paths still need durable audit-preservation proof at the route/background boundary.
- Browser/e2e operator-state coverage is still too narrow for readiness claims.
- Database evolution currently relies on `create_all()` plus SQLite patch helpers rather than versioned migrations.
- Python dependency locking and dependency-vulnerability gates are not yet production-grade.
- Logs and domain events need a stronger redaction boundary before broker/account payloads are safe to persist broadly.
- Secrets hygiene, historical repository scanning, and multi-process observability still need platform hardening.

## What Must Change Before Broker Dealing

Before live or demo broker dealing, the app needs at least:

- complete modeled/documented contracts for any future operator-critical raw response families
- durable audit-preservation proof for remaining mutation, broker-action, reconciliation, recovery, and background-event paths
- browser/e2e evidence for degraded, stale, simulated, unknown, manual-review, and mutation-failure operator states
- migration, dependency, redaction, and secrets controls that are strong enough for broker-connected operation
- regression tests for every fixed P0/P1 behaviour that still lacks route, frontend, or full-stack evidence

Track progress in [audit-status.md](audit-status.md).
