# Readiness And Safe Usage

InvestMate is **not ready for live trading**.

The current repository state is **ready for a human-supervised IG demo smoke test after sign-off**. That readiness claim is intentionally narrow:

- it does not approve unattended autonomy
- it does not approve live dealing
- it does not remove manual security and operations sign-offs

## Current verified supervised-demo posture

The 2026-06-04 remediation pass closed the current code blockers for a supervised IG demo smoke test:

1. `IG_API_BASE_URL` is the single source of truth for broker environment.
2. Only these canonical gateways are accepted:
   - demo: `https://demo-api.ig.com/gateway/deal`
   - live: `https://api.ig.com/gateway/deal`
3. Live dealing now fails closed unless `IG_LIVE_TRADING_ACKNOWLEDGED=true`.
4. `/system/broker-environment` exposes backend-owned environment, endpoint classification, and dealing truth.
5. Test-only backend routes default to disabled and cannot register in production-like or live-dealing posture.
6. `HealthService` now uses the active injected database context instead of a hidden module-global engine.
7. Backend lockfile regeneration and freshness checks are green again.

## Local verification snapshot

The current local verification record is captured in [docs/demo-trading-readiness-audit.md](demo-trading-readiness-audit.md).

Highlights from the 2026-06-04 run:

- `backend/.venv/bin/pytest backend/tests -q` -> `562 passed, 5 skipped`
- `cd frontend && npm run typecheck` -> passed
- `cd frontend && npm run test:frontend` -> `78 passed`
- `cd frontend && npm run test:e2e -- --grep "DEMO|environment|dealing|AUDIT-|FLOW-"` -> `61 passed`
- read-only preflight with `IG_TRADING_ENABLED=false`, `IG_STREAMING_ENABLED=false`, `AUTONOMOUS_CONTROL_ENABLED=false`, and `TESTING_ROUTES_ENABLED=false` returned `200` for `/health`, `/system/health`, `/system/telemetry`, `/system/broker-environment`, `/dashboard`, `/control-plane/summary`, `/events`, and `404` for `POST /testing/reset-history`

## Allowed local postures

### Local UI, research, and read-only smoke testing

This is acceptable when all of the following stay true:

1. `IG_TRADING_ENABLED=false`
2. `TESTING_ROUTES_ENABLED=false` unless you are in an explicit dev/test harness
3. No broker mutation is attempted
4. The session is treated as UI review, operator research, broker-read investigation, or smoke testing only

### Human-supervised IG demo smoke test

This is acceptable only after human sign-off on these conditions:

1. Use a fresh versioned database.
2. Use the demo gateway: `IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal`.
3. Verify `/system/broker-environment` reports `DEMO` and the expected dealing state before any smoke workflow.
4. Keep test-only controls disabled.
5. Resolve or explicitly accept the manual security posture in `AUDIT-SEC-003`:
   - purge historical SQLite DB blobs before broader sharing or publication
   - rotate any local or demo credentials if repository or workstation state was shared

### Live trading

Live trading remains blocked.

Additional production-only work is still required:

1. Verified manual history cleanup and any required credential rotation.
2. A reviewed production migration story beyond the fresh-database demo posture.
3. Stronger supply-chain provenance, attestation, and broader dependency/runtime hardening.
4. Continued operator/browser evidence and runbook expansion as the surface area evolves.

## Historical Notes

Historical remediation slices remain in [docs/audit-status.md](audit-status.md). Treat them as historical evidence, not the current readiness snapshot.
