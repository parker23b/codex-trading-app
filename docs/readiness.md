# Readiness And Safe Usage

InvestMate is **not ready for live trading**.

The current repository state is not yet approved for broker-connected demo dealing. The three `2026-06-12` P0 implementation defects are fixed and locally regression-tested, but the new Postgres concurrency rehearsals have not run in this local environment. The allowed posture remains intentionally narrow until CI and preflight evidence are refreshed:

- it does not approve unattended autonomy
- it does not approve live dealing
- it does not approve demo broker mutation
- it permits local/read-only investigation with dealing disabled

## Current posture

The `2026-06-12` remediation:

1. moved periodic broker reconciliation into an independent leader-owned supervisor (`AUDIT-ARCH-001`);
2. serialized allocation and durable intent admission with a process lock on SQLite and a transaction-scoped Postgres advisory lock (`AUDIT-RISK-004`);
3. added monotonic lease generations and an IG mutation fence that holds the lease row against takeover (`AUDIT-RUNTIME-002`).

Local backend evidence is green. Production-dialect proof remains pending because the Postgres rehearsal environment variable is unavailable on this machine.

## Local verification snapshot

The current verification record is captured in [docs/demo-trading-readiness-audit.md](demo-trading-readiness-audit.md).

Highlights:

- `backend/.venv/bin/python -m pytest backend/tests -q` -> `574 passed, 7 skipped`
- the skipped tests are the Postgres migration, allocation-lock, and runtime-fence rehearsals because `POSTGRES_REHEARSAL_ADMIN_URL` is not set locally
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

### Broker-connected demo dealing

Pending. Keep dealing disabled until the committed Postgres cross-connection tests pass in CI and the fresh-database, demo-account preflight is rerun. The prior P0 code paths are fixed locally; this hold is now an evidence gate rather than an unfixed-design gate.

### Live trading

Live trading remains blocked.

Additional production-only work is still required:

1. Define one authoritative open-risk management model (`AUDIT-ARCH-002`).
2. Introduce production-grade operator identity and authorization (`AUDIT-SEC-004`).
3. Complete the broker capability/resilience contract (`AUDIT-BROKER-006`).
4. Establish deterministic replay/live parity (`AUDIT-ARCH-003`).
5. Complete history, migration, supply-chain, and operations hardening.

## Historical Notes

Historical remediation slices remain in [docs/audit-status.md](audit-status.md). Treat them as historical evidence, not the current readiness snapshot.
