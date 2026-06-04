# Supervised IG Demo-Trading Readiness Audit

## Audit date

- Updated: `2026-06-04`

## Final verdict

`READY_FOR_HUMAN_SUPERVISED_IG_DEMO_SMOKE_TEST_AFTER_SIGN_OFF`

This verdict is deliberately narrow:

- it does **not** claim live-trading readiness
- it does **not** approve unattended autonomy
- it still requires human sign-off, a fresh versioned database, and the documented manual security posture

## What the codebase currently does

- Broker environment is now derived solely from `IG_API_BASE_URL`.
- The only accepted IG gateways are:
  - demo: `https://demo-api.ig.com/gateway/deal`
  - live: `https://api.ig.com/gateway/deal`
- The backend rejects malformed URLs, non-HTTPS URLs, altered paths, unknown hosts, and lookalike hosts before any credentialed IG request is attempted.
- Live dealing now fails closed unless `IG_LIVE_TRADING_ACKNOWLEDGED=true`.
- `GET /system/broker-environment` returns backend-owned truth for provider, environment, endpoint classification, dealing enabled, streaming enabled, live-dealing acknowledgement, configuration validity, and blocking reason.
- The frontend global shell now renders broker environment and dealing truth from that backend contract only.
- Test-only backend routes default to disabled and cannot register in production-like or live-dealing posture.
- `HealthService` now reads through the injected or active database context instead of a hidden module-global engine.

## What was ambiguous or weak and is now fixed

- The legacy demo/live toggle and `IG_API_BASE_URL` could disagree.
  Current status: fixed by deriving runtime environment only from `IG_API_BASE_URL`.
- The UI could show `Unknown` or fall back toward misleading environment truth.
  Current status: fixed by using `/system/broker-environment` and failing closed visibly on unknown or invalid status.
- Test-only reset routes could be reachable by default.
  Current status: fixed by default-disabling registration and adding a second posture gate.
- Backend tests were not trustworthy because health reads used the wrong database engine.
  Current status: fixed by injecting the active session/session factory into `HealthService`.
- Backend lockfile freshness was red.
  Current status: fixed by regenerating the committed lockfiles through the supported scripts.

## What better operational patterns suggest

- Broker environment should be a hard backend-owned boundary, not a UI inference or a soft override.
- Live dealing needs a second explicit acknowledgement beyond selecting a live endpoint.
- Operators need visible environment and dealing truth in the global shell before any smoke workflow begins.
- Test-only destructive routes must be unavailable by backend registration policy, not merely hidden in the UI.
- Passive health and telemetry reads must use the active app database context so verification evidence remains trustworthy.

## What I recommend changing next

- Do not broaden this supervised-demo closure into a live-readiness claim.
- Keep using `/system/broker-environment` as the required preflight truth source before broker-connected sessions.
- Preserve the current canonical-gateway validation if broker code evolves.
- Keep test-only routes disabled outside explicit harnesses.
- Expand production runbooks and live-trading controls separately from this demo-readiness slice.

## Verification results

### Lockfiles

- `./scripts/compile_backend_requirements.sh` -> passed
- `./scripts/check_backend_requirements.sh` -> passed

### Targeted backend tests

- `backend/.venv/bin/pytest backend/tests/test_config.py -q` -> `16 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_ig_broker_sizing.py -q` -> `8 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_testing_routes.py -q` -> `4 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_health_routes.py -q` -> `4 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_passive_read_routes.py -q` -> `8 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_runtime_leadership_service.py -q` -> `4 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_runtime_recovery_service.py -q` -> `14 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_reconciliation_service.py -q` -> `12 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_broker_action_http_authority.py -q` -> `14 passed, 1 warning`
- `backend/.venv/bin/pytest backend/tests/test_operator_auth_boundary.py -q` -> `7 passed, 1 warning`

### Full backend suite

- `backend/.venv/bin/pytest backend/tests -q` -> `562 passed, 5 skipped, 1 warning`

Skipped:

- `backend/tests/test_postgres_migration_rehearsal.py` skipped because `POSTGRES_REHEARSAL_ADMIN_URL` is not set in this local environment

### Frontend verification

- `cd frontend && npm run typecheck` -> passed
- `cd frontend && npm run test:frontend` -> `78 passed`
- `cd frontend && npm run test:e2e -- --grep "DEMO|environment|dealing|AUDIT-|FLOW-"` -> `61 passed`

### Repo-wide guards

- `python3 scripts/check_spec_coverage_matrix.py` -> `PASS`
- `backend/.venv/bin/python scripts/check_backend_route_inventory.py` -> passed
- `python3 scripts/repo_secrets_scan.py --mode working-tree` -> `No findings.`
- `git diff --check` -> passed

## Read-only preflight results

Backend startup used:

- fresh SQLite database under `/private/tmp`
- `IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal`
- `IG_TRADING_ENABLED=false`
- `IG_STREAMING_ENABLED=false`
- `AUTONOMOUS_CONTROL_ENABLED=false`
- `TESTING_ROUTES_ENABLED=false`

Observed results:

- `GET /health` -> `200`, body `{"status":"idle"}`
- `GET /system/health` -> `200`, degraded for disconnected broker/stream as expected
- `GET /system/telemetry` -> `200`, `feed_source_state="DISCONNECTED"`, `entry_eligible=false`, `exit_eligible=false`
- `GET /system/broker-environment` -> `200`, body reported `DEMO`, `IG_DEMO_GATEWAY`, `dealing_enabled=false`, `streaming_enabled=false`, `configuration_valid=true`
- `GET /dashboard` -> `200`
- `GET /control-plane/summary` -> `200`
- `GET /events` -> `200`
- `POST /testing/reset-history` -> `404`

## Remaining supervised-demo blockers

No remaining code blockers were found in this remediation slice.

Required non-code sign-offs remain:

1. Use a fresh versioned database for the supervised demo.
2. Confirm the intended IG account is a demo account.
3. Verify `/system/broker-environment` before the smoke workflow.
4. Keep test-only controls disabled.
5. Complete or explicitly accept the manual security actions in `AUDIT-SEC-003`.

## Live-trading posture

Live trading remains blocked.

This audit does not claim:

- production readiness
- live dealing readiness
- unattended autonomous trading readiness
