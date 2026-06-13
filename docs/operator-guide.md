# Operator Guide

This guide covers local development setup and operator-facing surfaces. It is not a production runbook. InvestMate is not ready for broker-connected demo dealing, unattended autonomy, or live trading.

## Prerequisites

- Python 3.11 or newer.
- Node.js and npm compatible with `frontend/package-lock.json`.
- Network access for dependency installation.
- Optional IG demo credentials for broker-read checks.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -c requirements.txt -e .
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Default backend behavior:

- uses SQLite at `backend/trading_platform.db`
- applies Alembic migrations automatically on startup
- upgrades existing unversioned SQLite dev databases through a legacy compatibility bridge before stamping the baseline revision
- uses the IG broker adapter with `IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal`
- keeps `IG_TRADING_ENABLED=false`
- enables IG streaming by default
- keeps `IG_LIVE_TRADING_ACKNOWLEDGED=false`
- keeps test-only backend routes disabled by default
- keeps AIMEE/AI reviewer LLM augmentation disabled by default

Backend URL: [http://localhost:8000](http://localhost:8000)

Useful startup checks without IG credentials:

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/system/health](http://localhost:8000/system/health)
- [http://localhost:8000/system/broker-environment](http://localhost:8000/system/broker-environment)
- [http://localhost:8000/control-plane/summary](http://localhost:8000/control-plane/summary)
- [http://localhost:8000/coverage/summary](http://localhost:8000/coverage/summary)
- [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- [http://localhost:8000/reviews/operator-summary](http://localhost:8000/reviews/operator-summary)

Expected degraded states with blank IG credentials:

- `/health` should return an app-level health response
- `/system/health` and `/dashboard` can report disconnected broker or stream state
- `/reviews/operator-summary` can include disabled LLM or degraded stream warnings
- `/broker/positions` and `/markets/overview?category=forex` return credential-required errors
- startup can log missing IG settings during recovery

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL: [http://localhost:3000](http://localhost:3000)

## Optional IG Demo Read Connectivity

Update `backend/.env` with demo credentials only when you want broker-read checks:

```env
BROKER_PROVIDER=IG
IG_API_KEY=your-demo-api-key
IG_USERNAME=your-demo-username
IG_PASSWORD=your-demo-password
IG_ACCOUNT_ID=your-demo-account-id
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_TRADING_ENABLED=false
IG_LIVE_TRADING_ACKNOWLEDGED=false
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
TESTING_ROUTES_ENABLED=false
```

Read-only verification progression:

1. Keep `IG_TRADING_ENABLED=false`.
2. Start the backend.
3. Verify `GET /system/broker-environment` returns `DEMO`, `IG_DEMO_GATEWAY`, and the expected dealing state.
4. Verify auth via `GET /broker/positions`.
5. Verify stream or market health via `GET /health/stream` and `GET /system/health`.
6. Verify market inspection via `GET /markets/overview?category=forex`.
7. Verify `POST /testing/reset-history` returns `404`.

Allowed broker gateway values:

- demo: `https://demo-api.ig.com/gateway/deal`
- live: `https://api.ig.com/gateway/deal`

Any other host, path, or non-HTTPS URL is rejected during backend configuration. The frontend must not infer environment from URL strings.

Live-dealing guard:

- `IG_API_BASE_URL=https://api.ig.com/gateway/deal` with `IG_TRADING_ENABLED=false` is allowed for read-only posture.
- `IG_API_BASE_URL=https://api.ig.com/gateway/deal` with `IG_TRADING_ENABLED=true` requires `IG_LIVE_TRADING_ACKNOWLEDGED=true`.
- This acknowledgement only permits startup. It does not imply live-trading readiness.

Do not enable real broker dealing until the pending Postgres concurrency rehearsal and supervised-demo preflight have passed.

## Broker-Connected Demo Posture

Read-only broker connectivity is allowed with `IG_TRADING_ENABLED=false`. The three `2026-06-12` P0 implementation defects are fixed locally, but broker mutation remains operationally blocked until CI runs the committed Postgres allocation-lock and runtime-fence rehearsals and the supervised-demo preflight is repeated.

For read-only broker investigation:

1. Start with a fresh versioned database.
2. Keep `IG_TRADING_ENABLED=false`.
3. Confirm `/system/broker-environment` shows the expected environment and dealing is disabled.
4. Confirm test-only controls remain gated unless you are in an explicit dev/test workflow.

Manual decisions remain outside the repo:

- purge historical SQLite DB blobs before broader sharing or publication
- rotate any local/demo credentials if the repository or workstation state was shared
- do not claim stronger supply-chain attestation than the current hash, audit, and SBOM controls actually provide

## Main Surfaces

- `/` - overview dashboard for positions, executions, broker state, stream health, coverage, and control-plane summary.
- `/live` - live system view with trust rail, anomalies, runtime state, instrument inspection, and operational context.
- `/risk` - allocation exposure, drift, cycles, intents, and alert workflow.
- `/control-plane` - autonomous-control state, governance, deployment alignment, and family detail.
- `/coverage` - Tier 1 streaming, Tier 2 refresh, promotion activity, and operating limits.
- `/markets` - market-category investigation, catalogue data, shortlist, and strategy-watchlist workflows.
- `/events` - domain-event console and local test reset control.
- `/strategies` - strategy registry, runtime state, profile visibility, and manual runtime controls.
- `/reviewer` - persisted reviewer summaries and review history.
- AIMEE drawer - persistent assistant-style operational overview and Q&A surface.

## Identifier Visibility And Retention

Operator-facing APIs and UI surfaces no longer need raw broker/account/request/runtime/correlation identifiers for ordinary investigation.

- What stays raw internally:
  - broker/deal references used for reconciliation and later close authority
  - execution client request ids used for duplicate suppression and retry correlation
  - runtime ids and recovered broker position references used for recovery/lifecycle joins
  - persisted domain-event correlation/runtime ids used for internal traceability
- What operators see:
  - reviewed surfaces now return a masked `display` plus stable `fingerprint`
  - the masked display is for quick recognition without exposing the raw identifier
  - the fingerprint is for cross-surface correlation across dashboard, events, trades, strategies, control-plane, and allocation views
- What is forbidden:
  - `Authorization`, `CST`, `X-SECURITY-TOKEN`, session/header/token/password/api-key fields must not survive persistence or serialization
  - do not treat `NEXT_PUBLIC_*` values as secrets; they are browser-visible transport configuration
- Retention limits:
  - the repository still contains historical cleanup work outside this code change
  - raw internal authority identifiers are intentionally retained in the database where lifecycle correctness still depends on exact values

## Environment Variables

Backend env file: `backend/.env`.

Most important backend variables:

- `DATABASE_URL` - SQLModel connection string. Relative SQLite paths are normalized against `backend/`.
  Supported posture today: clean SQLite development remains the default, versioned Postgres creation/rehearsal is supported for migration proof, and existing unversioned non-SQLite databases are intentionally refused at startup until they are migrated manually.
- `BROKER_PROVIDER` - current allowed value is `IG`.
- `IG_API_BASE_URL` - canonical broker gateway and the single source of truth for environment selection. Allowed values are `https://demo-api.ig.com/gateway/deal` and `https://api.ig.com/gateway/deal`.
- `IG_TRADING_ENABLED` - safety switch for broker dealing. Keep this `false`.
- `IG_LIVE_TRADING_ACKNOWLEDGED` - required before any live gateway plus live dealing configuration may start.
- `IG_STREAMING_ENABLED` - starts the streaming loop when enabled.
- `TESTING_ROUTES_ENABLED` - keep this `false` outside explicit dev/test harnesses.
- `MARKET_DATA_POLL_INTERVAL_SECONDS` - market-data loop cadence.
- `AI_REVIEWER_LLM_ENABLED` - keeps reviewer output deterministic when `false`.
- `STARTING_ACCOUNT_VALUE` - dashboard baseline value.

Frontend env file: `frontend/.env.local`.

Most important frontend variables:

- `NEXT_PUBLIC_API_BASE_URL` - backend URL for frontend requests.
- `NEXT_PUBLIC_ENABLE_DEV_FALLBACK` - present in the env example, but current shared client behavior does not actively branch on it.

## Verification Commands

Backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Backend migration and drift checks:

```bash
cd backend
source .venv/bin/activate
alembic current
alembic upgrade head
pytest tests/test_database_migrations.py tests/test_initialize_database.py -q
POSTGRES_REHEARSAL_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres \
  pytest tests/test_postgres_migration_rehearsal.py -m postgres_rehearsal -q
```

Frontend static checks:

```bash
cd frontend
npm run audit
```

Current evidence gaps are tracked in [audit-status.md](audit-status.md).
