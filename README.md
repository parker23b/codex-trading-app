# Algorithmic Trading Platform

Production-oriented monorepo scaffold for a personal algorithmic trading platform with a clean separation between strategy logic, execution logic, API orchestration, and UI consumption.

## Monorepo Structure

```text
backend/
  app/
    api/          # FastAPI routes and request/response schemas
    core/         # Config, logging, broker abstractions, trading engine
    db/           # Database engine, session, startup helpers
    models/       # Persistence models
    services/     # Application services used by the API layer
    strategies/   # Pluggable trading strategies and registry
    main.py
frontend/
  app/            # Next.js App Router pages
  components/     # UI building blocks
  lib/            # API client and shared frontend types
```

## Architecture

### Backend

- `strategies/` contains pure trading logic. Strategies do not know about FastAPI, brokers, or the database.
- `core/broker.py` defines the execution contract. The trading engine only depends on the `Broker` interface.
- `core/trading_engine.py` coordinates strategy evaluation and broker execution without importing FastAPI.
- `services/` sits between the API and domain/runtime logic so the HTTP layer stays thin and testable.
- `db/` and `models/` encapsulate persistence concerns.

### Frontend

- Next.js consumes backend APIs only.
- The UI does not own business state; the backend remains the source of truth.
- API access is centralized in `frontend/lib/api.ts` to keep components simple.

## Running the Backend

1. Create a virtual environment in `backend/`.
2. Install dependencies:

```bash
cd backend
pip install -e .
```

3. Copy `.env.example` to `.env` and update values if needed.
4. Start the API:

```bash
cd backend
uvicorn app.main:app --reload
```

The default database URL points to PostgreSQL. For quick local bootstrapping, you can temporarily set a SQLite URL in `DATABASE_URL`, but production should use PostgreSQL.

## Running the Frontend

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Copy `.env.example` to `.env.local`.
3. Start the dev server:

```bash
cd frontend
npm run dev
```

## Key Design Decisions

- Broker integrations are isolated behind an interface so IG can be swapped out later.
- The trading engine is a reusable application core and can be driven by APIs, jobs, workers, or WebSockets.
- Strategy lifecycle is managed by services, not routes.
- Real-time support is prepared with a stub WebSocket manager that can be expanded later without reworking the engine.

## Next Steps

- Replace the `IGBroker` stub with authenticated IG API calls.
- Add market data ingestion and event distribution for live price updates.
- Add background workers and persistent strategy runtime state if strategies need to survive process restarts.
- Add automated tests around strategies, services, and broker adapters.

