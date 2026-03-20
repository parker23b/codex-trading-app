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
- `services/dashboard_service.py` is the read-model aggregation layer for dashboard KPIs and charts.
- `services/simulation_service.py` drives simulated market data through the trading engine when `SIMULATION_MODE=true`.
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

The default development configuration now uses a local SQLite database so `uvicorn app.main:app --reload` boots immediately. Production should still point `DATABASE_URL` at PostgreSQL.

## IG Demo API Setup

The project currently ships with a stub `IGBroker` in [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py). That means the backend architecture is ready for IG, but authenticated HTTP calls to IG have not been implemented yet.

To prepare an IG demo account for this codebase:

1. Create or log into your IG account.
2. Create a demo account from the IG platform account switcher.
3. Generate a demo API key while switched into the demo environment.
4. Keep the following values ready for backend configuration:
   - API key
   - Username
   - Password
   - Account identifier
   - Demo REST base URL
5. Add those values to `backend/.env` once the authenticated broker implementation is added.

Suggested environment variables for the future IG adapter:

```env
BROKER_PROVIDER=IG
BROKER_MODE=DEMO
IG_API_KEY=your-demo-api-key
IG_USERNAME=your-demo-username
IG_PASSWORD=your-demo-password
IG_ACCOUNT_ID=your-demo-account-id
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
```

Recommended implementation order for the real IG integration:

1. Add login/session creation in `IGBroker` using IG's session endpoint.
2. Store and refresh the returned auth tokens before they expire.
3. Implement account lookup and position sync via the broker interface.
4. Replace stub `place_order`, `close_position`, and `get_positions` with real REST calls.
5. Add streaming price support separately so the engine keeps using the same broker abstraction.

Current status:

- IG session authentication is implemented in the broker adapter.
- `GET /broker/positions` is the safest way to verify your IG demo credentials through the API.
- Real order placement remains intentionally disabled unless `IG_TRADING_ENABLED=true`, and the code still requires the dealing endpoints to be implemented before enabling that.
- If your local Python install fails certificate validation, prefer fixing the local trust store first. For local demo-only testing you can temporarily set `IG_VERIFY_SSL=false`, or point `IG_CA_BUNDLE_PATH` at a trusted CA bundle.

See [backend/app/core/BROKER_INTEGRATION.md](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/BROKER_INTEGRATION.md) for the adapter checklist.

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
- New broker adapters should implement the shared interface in `backend/app/core/broker.py` and be selected via the broker factory.

## Next Steps

- Replace the `IGBroker` stub with authenticated IG API calls.
- Add market data ingestion and event distribution for live price updates.
- Add background workers and persistent strategy runtime state if strategies need to survive process restarts.
- Add automated tests around strategies, services, and broker adapters.

## References

- IG Labs getting started: [labs.ig.com/gettingstarted](https://labs.ig.com/gettingstarted)
- IG Labs REST trading guide: [labs.ig.com/rest-trading-api-guide.html](https://labs.ig.com/rest-trading-api-guide.html)
- IG Labs streaming guide: [labs.ig.com/streaming-api-guide.html](https://labs.ig.com/streaming-api-guide.html)
