# InvestMate

InvestMate is a FastAPI and Next.js trading-operations workspace for supervised autonomous trading research. It combines strategy runtimes, bounded market-data coverage, risk allocation, IG broker integration, recovery/reconciliation, operator dashboards, and AIMEE reviewer surfaces.

## Status: Not Ready For Live Trading

InvestMate is **not ready for live trading**.

The current codebase is ready only for a **human-supervised IG demo smoke test after sign-off**. That supervised-demo posture is narrower than live-trading readiness:

- the backend now derives broker environment solely from `IG_API_BASE_URL`
- only the canonical IG demo and live gateways are accepted
- live dealing requires `IG_LIVE_TRADING_ACKNOWLEDGED=true`
- `/system/broker-environment` exposes backend-owned environment and dealing truth
- test-only backend routes are disabled by default and blocked in production-like or live-dealing posture

Keep `IG_TRADING_ENABLED=false` for normal local use. Live trading remains blocked. Read the current posture in [docs/readiness.md](docs/readiness.md) and the verification record in [docs/demo-trading-readiness-audit.md](docs/demo-trading-readiness-audit.md).

## What This Is

InvestMate is an operator console and backend control system for supervised autonomy:

- strategies generate raw signals
- governance decides which strategy families and profiles are allowed
- coverage decides which instruments receive streaming attention
- allocation and risk controls decide which signals may take risk
- broker adapters handle market/account reads and order execution
- reconciliation, recovery, events, and AIMEE help operators inspect what happened

It is not a profit promise, retail manual trading terminal, or safe broker-dealing system in its current state.

## Quick Start

Prerequisites:

- Python 3.11 or newer
- Node.js and npm compatible with `frontend/package-lock.json`
- network access for Python and Node dependency installation
- optional IG demo credentials for broker-read checks

Start the backend:

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

Start the frontend:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Local URLs:

- Backend: [http://localhost:8000](http://localhost:8000)
- Frontend: [http://localhost:3000](http://localhost:3000)

Without IG credentials, the app can still start. Broker-read routes such as `/broker/positions` and `/markets/overview?category=forex` return credential-required errors until IG settings are provided.

Full setup notes are in [docs/operator-guide.md](docs/operator-guide.md).

Optional stricter backend dependency verification:

```bash
./scripts/check_backend_requirements.sh
./scripts/verify_backend_dependency_integrity.sh
./scripts/generate_sbom.sh backend
```

Optional frontend dependency verification:

```bash
./scripts/check_frontend_dependencies.sh
./scripts/generate_sbom.sh frontend
```

## Main App Surfaces

- `/` - overview dashboard
- `/live` - live system view, trust rail, instrument inspection, and operational state
- `/risk` - allocation exposure, cycles, drift, intents, and alerts
- `/control-plane` - autonomous-control state, governance, and deployment alignment
- `/coverage` - Tier 1/Tier 2 coverage and promotion activity
- `/markets` - market investigation and watchlist workflows
- `/events` - domain-event history and local test reset control
- `/strategies` - strategy registry and manual runtime controls
- `/reviewer` - persisted reviewer summaries and review history
- AIMEE drawer - persistent assistant-style operational summary and Q&A surface

## Architecture Summary

High-level flow:

```text
Frontend operator console
  -> FastAPI routes
    -> application services
      -> runtime manager / control plane / coverage allocator / trade allocator
        -> trading engine
          -> strategies + broker adapter
            -> SQLModel persistence + broker state
```

Core boundaries:

- `TradeIntent` owns pre-trade decision authority.
- `Execution` records broker attempts and execution audit.
- `Position` records live local exposure.
- `Trade` records closed realized outcomes.
- Broker-specific behavior belongs behind broker adapter interfaces.
- Passive reads, active reads, mutations, broker reads, and test-only mutations are tracked in the API route reference.

Read more in [docs/architecture.md](docs/architecture.md), [docs/trade-lifecycle.md](docs/trade-lifecycle.md), and [docs/backend-api-routes.md](docs/backend-api-routes.md).

## Safety Model

Target invariants:

- no order submission without an authoritative `TradeIntent`
- no exit without a linked open position, close-valid intent, or explicit recovery/reconciliation authority
- no recovered broker-confirmed open position without visible local lifecycle evidence
- one active instrument owner at a time
- unknown, stale, degraded, simulated, or fallback data must not be rendered as exact broker truth

Current gaps against these targets are tracked in [docs/audit-status.md](docs/audit-status.md).

## Development Commands

Backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Backend migration commands:

```bash
cd backend
source .venv/bin/activate
alembic current
alembic upgrade head
pytest tests/test_database_migrations.py -q
POSTGRES_REHEARSAL_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres \
  pytest tests/test_postgres_migration_rehearsal.py -m postgres_rehearsal -q
```

Frontend checks:

```bash
cd frontend
npm run audit
```

Useful backend startup checks:

- `GET /health`
- `GET /system/health`
- `GET /system/broker-environment`
- `GET /control-plane/summary`
- `GET /coverage/summary`
- `GET /dashboard`
- `GET /reviews/operator-summary`

## Documentation Map

- [docs/readiness.md](docs/readiness.md) - current safety posture, blockers, and safe local usage
- [docs/operator-guide.md](docs/operator-guide.md) - setup, environment, app surfaces, and smoke checks
- [docs/architecture.md](docs/architecture.md) - backend/frontend/service boundaries and state ownership
- [docs/trade-lifecycle.md](docs/trade-lifecycle.md) - intent-first trade lifecycle and recovery/reconciliation model
- [docs/backend-api-routes.md](docs/backend-api-routes.md) - generated implementation route reference and classification notes
- [docs/audit-status.md](docs/audit-status.md) - audit findings, readiness blockers, and remediation backlog
- [docs/spec/](docs/spec/) - spec-driven development contracts
- [docs/BROKER_INTEGRATION.md](docs/BROKER_INTEGRATION.md) - broker integration notes

## Known Risks

The short version:

- a supervised broker-connected demo is not automatic; use a fresh versioned database and resolve the manual security posture in [docs/readiness.md](docs/readiness.md) first
- repository-history cleanup and any required credential rotation remain manual actions
- unversioned legacy non-SQLite databases still require manual upgrade or a reviewed one-off migration path
- stronger supply-chain provenance and broader host/container dependency scanning remain future production hardening
- broader evidence breadth will still need to grow as new operator surfaces and broker-connected workflows evolve

The source of truth is [docs/audit-status.md](docs/audit-status.md).

## Reference Links

- Backend entry point: [backend/app/main.py](backend/app/main.py)
- API router: [backend/app/api/router.py](backend/app/api/router.py)
- Runtime manager: [backend/app/core/runtime.py](backend/app/core/runtime.py)
- Broker interface: [backend/app/core/broker.py](backend/app/core/broker.py)
- IG adapter: [backend/app/core/ig_broker.py](backend/app/core/ig_broker.py)
- Strategy service: [backend/app/services/strategy_service.py](backend/app/services/strategy_service.py)
- Trade decision service: [backend/app/services/trade_decision_service.py](backend/app/services/trade_decision_service.py)
- Frontend app: [frontend/app](frontend/app)
- Frontend API client: [frontend/lib/api.ts](frontend/lib/api.ts)
