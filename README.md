# Investmate Trading Platform

Monorepo for a personal algorithmic trading platform with:

- a FastAPI backend for strategy runtime, broker access, market snapshots, and portfolio data
- a Next.js frontend for dashboard, market readiness, and strategy controls
- frontend-only demo fallback data when the backend is unavailable

The codebase is structured so strategy logic stays isolated from HTTP, persistence, and broker-specific code. That separation is the main architectural idea in this repo.

## What The App Does

Today the product exposes three main operator workflows:

1. Dashboard
   View account KPIs, equity trend, open positions, risk concentration, and recent trades.
2. Markets
   Inspect market categories such as forex or indices, see whether instruments are tradable, and understand which instruments are active or strategy-compatible.
3. Strategies
   Start and stop registered strategies, review current PnL and win rate, and inspect editable strategy settings in the UI.

There are two practical frontend states:

- Backend connected: pages render backend-backed data.
- Backend unavailable: frontend enters demo mode and renders local sample data for UI development and demos.

## Repository Layout

```text
backend/
  app/
    api/
      router.py                # Top-level API router
      routes/                  # HTTP endpoints
    core/
      broker.py                # Shared broker contract and domain dataclasses
      broker_factory.py        # Concrete broker selection
      config.py                # Environment-driven settings
      ig_broker.py             # IG adapter
      instrument_catalog.py    # Supported instruments and metadata
      runtime.py               # In-memory runtime manager
      trading_engine.py        # Strategy-to-broker coordinator
      websocket_manager.py     # Stub for future streaming
      BROKER_INTEGRATION.md    # Adapter design notes
    db/
      session.py               # SQLModel engine and sessions
      init_db.py               # Table creation
    models/
      trade.py                 # Trade and Position tables
    services/                  # Application service layer
    strategies/                # Pure strategy implementations and registry
    main.py                    # FastAPI app entrypoint
  pyproject.toml
  .env.example
  trading_platform.db          # Local SQLite DB used by default

frontend/
  app/
    layout.tsx                 # Shell, nav, theme bootstrapping
    page.tsx                   # Dashboard page
    markets/page.tsx           # Markets page
    strategies/page.tsx        # Strategies page
  components/                  # Dashboard, market, strategy, and shared UI
  lib/
    api.ts                     # Backend client and dev fallback behavior
    types.ts                   # Frontend domain types
    format.ts                  # Display formatters
  package.json
  .env.example
```

## Quick Start

### 1. Start The Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

Default backend behavior:

- uses SQLite at `backend/trading_platform.db`
- creates tables automatically on startup
- runs in simulation mode
- starts with no seeded runtime activity

Backend URL: [http://localhost:8000](http://localhost:8000)

Useful endpoints to sanity-check startup:

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- [http://localhost:8000/strategies](http://localhost:8000/strategies)

### 2. Start The Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL: [http://localhost:3000](http://localhost:3000)

### 3. Run With Live IG Connectivity

Update `backend/.env`:

```env
SIMULATION_MODE=false
BROKER_PROVIDER=IG
BROKER_MODE=DEMO
IG_API_KEY=your-demo-api-key
IG_USERNAME=your-demo-username
IG_PASSWORD=your-demo-password
IG_ACCOUNT_ID=your-demo-account-id
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_TRADING_ENABLED=false
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
```

Recommended progression:

1. Keep `IG_TRADING_ENABLED=false`.
2. Start the backend.
3. Verify auth via `GET /broker/positions`.
4. Verify market snapshots via `GET /markets/overview?category=forex`.
5. Only then consider implementing or enabling real order placement.

`IG_TRADING_ENABLED=true` and `SIMULATION_MODE=true` cannot be used together.

## Environment Variables

The backend loads variables from `backend/.env`. The frontend loads variables from `frontend/.env.local`.

Reference files:

- [backend/.env.example](/Users/benparker/Documents/repos/codex-trading-app/backend/.env.example)
- [frontend/.env.example](/Users/benparker/Documents/repos/codex-trading-app/frontend/.env.example)

### Backend Example

```env
APP_NAME=Algo Trading Platform API
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./trading_platform.db
BROKER_PROVIDER=IG
BROKER_MODE=DEMO
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
STARTING_ACCOUNT_VALUE=100000
DASHBOARD_RECENT_TRADE_WINDOW=30
MARKET_DATA_POLL_INTERVAL_SECONDS=2
API_AUTH_TOKEN=
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_ID=
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_REQUEST_TIMEOUT_SECONDS=10
IG_TRADING_ENABLED=false
IG_MARKET_CACHE_TTL_SECONDS=30
IG_MARKET_CACHE_STALE_TTL_SECONDS=300
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
```

### Backend Variable Reference

- `APP_NAME`
  Example: `Algo Trading Platform API`
  Meaning: Human-readable app name used by FastAPI metadata and logs.
  Change it when: You want the API title or deployment branding to differ.

- `APP_ENV`
  Example: `development`
  Meaning: General environment label for the app. It is not heavily branched on yet, but it is useful for deployment conventions and logging.
  Common values: `development`, `staging`, `production`.

- `APP_HOST`
  Example: `0.0.0.0`
  Meaning: Intended bind host for the backend process.
  Change it when: Running the app behind a specific host binding. Note that `uvicorn app.main:app --reload` still needs matching CLI flags if you want to bind somewhere else.

- `APP_PORT`
  Example: `8000`
  Meaning: Intended backend port.
  Change it when: You want the API on a different port. As with `APP_HOST`, your process launcher must actually use that port.

- `LOG_LEVEL`
  Example: `INFO`
  Meaning: Root log verbosity used by [backend/app/core/logging.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/logging.py).
  Common values: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

- `DATABASE_URL`
  Example: `sqlite:///./trading_platform.db`
  Meaning: SQLModel/SQLAlchemy connection string.
  Local default: SQLite file inside `backend/`.
  Production-style example: `postgresql+psycopg://user:password@localhost:5432/trading_platform`
  Change it when: Moving from local development to a real database.

- `BROKER_PROVIDER`
  Example: `IG`
  Meaning: Broker implementation selected by the broker factory.
  Allowed values today: `IG`
  Change it when: Only if a new broker adapter is added.

- `BROKER_MODE`
  Example: `DEMO`
  Meaning: Tells the broker adapter whether it should behave as demo or live account infrastructure.
  Allowed values: `DEMO`, `LIVE`
  Change it when: Switching from paper/demo usage to a real account environment.

- `CORS_ORIGINS`
  Example: `http://localhost:3000,http://127.0.0.1:3000`
  Meaning: Comma-separated list of browser origins allowed to call the backend.
  Change it when: Adding deployed frontend URLs or alternate local ports.

- `STARTING_ACCOUNT_VALUE`
  Example: `100000`
  Meaning: Baseline account value used by dashboard calculations in simulation mode and as a reference for account change percentages.
  Change it when: You want the demo account to represent a different starting capital base.

- `DASHBOARD_RECENT_TRADE_WINDOW`
  Example: `30`
  Meaning: Number of recent trades used for dashboard metrics such as win rate and risk/reward.
  Change it when: You want a shorter or longer rolling performance window.

- `MARKET_DATA_POLL_INTERVAL_SECONDS`
  Example: `2`
  Meaning: Interval for live broker price polling when simulation mode is off.
  Change it when: Tuning responsiveness versus broker/API load.
  Constraint: Must be greater than `0`.

- `API_AUTH_TOKEN`
  Example: `dev-investmate-token-9f4c3a2b`
  Meaning: Bearer token required for protected control and broker endpoints (`/strategy/*`, `/strategies/*/{start|stop}`, `/broker/*`).
  Change it when: Rotating API access credentials between environments.
  Note: If unset, protected routes reject requests with `401 Unauthorized`.

- `IG_API_KEY`
  Example: `abc123demoapikey`
  Meaning: IG REST API key used during authentication.
  Change it when: Rotating credentials or switching accounts/environments.
  Note: Leave blank in pure simulation mode.

- `IG_USERNAME`
  Example: `demo.user@example.com`
  Meaning: IG account username used for session creation.
  Change it when: Using a different IG account.

- `IG_PASSWORD`
  Example: `super-secret-password`
  Meaning: IG account password used for session creation.
  Change it when: Rotating or replacing IG credentials.
  Note: Treat this as a secret and do not commit real values.

- `IG_ACCOUNT_ID`
  Example: `ABC123`
  Meaning: IG account identifier selected after login.
  Change it when: Switching between demo/live or between different IG sub-accounts.

- `IG_API_BASE_URL`
  Example: `https://demo-api.ig.com/gateway/deal`
  Meaning: Base URL for IG REST calls.
  Demo example: `https://demo-api.ig.com/gateway/deal`
  Live example: IG live dealing endpoint for your live environment.
  Change it when: Switching between demo and live APIs or when IG changes endpoints.

- `IG_REQUEST_TIMEOUT_SECONDS`
  Example: `10`
  Meaning: Timeout used for IG HTTP requests.
  Change it when: Your network is slow or you want faster failure on upstream issues.

- `IG_TRADING_ENABLED`
  Example: `false`
  Meaning: Safety switch for real order placement and close requests.
  `false`: order actions are simulated locally in the IG adapter.
  `true`: the adapter is allowed to hit live IG dealing endpoints.
  Recommended default: keep this `false` until you have verified auth, positions, and market reads.

- `IG_MARKET_CACHE_TTL_SECONDS`
  Example: `30`
  Meaning: Fresh-cache lifetime for IG market detail responses.
  Change it when: You want fewer upstream calls or fresher market snapshots.
  Constraint: Must be greater than `0`.

- `IG_MARKET_CACHE_STALE_TTL_SECONDS`
  Example: `300`
  Meaning: Maximum age for stale IG market data that can still be reused after an upstream failure.
  Change it when: You want a shorter stale window for stricter freshness, or a longer one for resilience.
  Constraint: Must be greater than `0`.

- `IG_VERIFY_SSL`
  Example: `true`
  Meaning: Controls SSL certificate verification for IG HTTPS requests.
  Recommended value: `true`
  Change it when: Only for local troubleshooting if your Python trust store is broken.

- `IG_CA_BUNDLE_PATH`
  Example: `/etc/ssl/certs/ca-certificates.crt`
  Meaning: Optional path to a custom CA bundle for IG HTTPS verification.
  Change it when: Your environment requires a non-default trust store.

### Frontend Example

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_AUTH_TOKEN=
NEXT_PUBLIC_ENABLE_DEV_FALLBACK=true
```

### Frontend Variable Reference

- `NEXT_PUBLIC_API_BASE_URL`
  Example: `http://localhost:8000`
  Meaning: Base URL used by [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts) for all backend requests.
  Change it when: The backend runs on another host, port, or deployed domain.

- `NEXT_PUBLIC_ENABLE_DEV_FALLBACK`
  Example: `true`
  Meaning: Enables development-only fallback data when the backend cannot be reached.
  `true`: dashboard, strategies, and markets can render with mock data in development.
  `false`: frontend fails fast instead of falling back.
  Change it when: You want to force the UI to use the real backend during local development.

- `NEXT_PUBLIC_API_AUTH_TOKEN`
  Example: `dev-investmate-token-9f4c3a2b`
  Meaning: Bearer token sent by `frontend/lib/api.ts` as `Authorization: Bearer <token>` on backend requests.
  Change it when: Rotating the backend API token.
  Important: This value is exposed to browser code because it is a `NEXT_PUBLIC_*` variable; use this setup for local/dev environments only.

### Recommended Config Sets

Backend local baseline:

```env
DATABASE_URL=sqlite:///./trading_platform.db
BROKER_MODE=DEMO
API_AUTH_TOKEN=dev-investmate-token-9f4c3a2b
IG_TRADING_ENABLED=false
```

Local IG demo connectivity without real dealing:

```env
SIMULATION_MODE=false
BROKER_MODE=DEMO
IG_API_KEY=your-demo-api-key
IG_USERNAME=your-demo-username
IG_PASSWORD=your-demo-password
IG_ACCOUNT_ID=your-demo-account-id
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_TRADING_ENABLED=false
IG_VERIFY_SSL=true
```

Frontend strict real-backend mode:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_AUTH_TOKEN=dev-investmate-token-9f4c3a2b
NEXT_PUBLIC_ENABLE_DEV_FALLBACK=false
```

## Codebase Tour

### Backend Architecture

The backend follows a layered flow:

```text
FastAPI route
  -> service
    -> runtime manager / trade service / broker service
      -> trading engine
        -> strategy + broker adapter
          -> database persistence
```

Core rules the codebase tries to preserve:

- strategies are pure signal generators
- the trading engine coordinates decisions and broker actions
- services own orchestration and persistence concerns
- routes stay thin
- broker-specific behavior stays behind the shared broker interface

### App Startup

[backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py) does four important things:

1. configures logging
2. initializes database tables
3. bootstraps simulation state
4. starts the live market polling loop when simulation is off

That means the backend is stateful even in development: startup changes runtime state and may populate the database.

### Core Modules

- [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py)
  Central settings model loaded from `.env`.
- [backend/app/core/broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/broker.py)
  Abstract broker contract plus normalized dataclasses such as `OrderRequest`, `BrokerPosition`, and `BrokerMarketDetails`.
- [backend/app/core/broker_factory.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/broker_factory.py)
  Creates the current broker implementation.
- [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py)
  Handles IG auth, positions lookup, account summary, and market details. Real order endpoints exist in the adapter, but trading is guarded by `IG_TRADING_ENABLED`.
- [backend/app/core/runtime.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/runtime.py)
  In-memory registry of running engines, strategy-to-instrument assignments, and last seen prices.
- [backend/app/core/trading_engine.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/trading_engine.py)
  Feeds price updates into a strategy, opens positions through the broker, and creates closed `Trade` records when exits fire.
- [backend/app/core/instrument_catalog.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/instrument_catalog.py)
  Static catalog for instrument metadata, categories, symbols, and compatible strategies.

### Persistence Layer

The database is intentionally small right now.

[backend/app/models/trade.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/models/trade.py) defines:

- `Trade`
  Closed trade history with PnL, `r_multiple`, outcome, and reason.
- `Position`
  Open position state with unrealized PnL, risk %, current price, and manual override flag.

[backend/app/db/session.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/session.py) configures SQLModel sessions, including SQLite thread options for local development.

[backend/app/db/init_db.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/db/init_db.py) creates tables on startup.

### Strategy System

Strategies live in [backend/app/strategies](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies) and implement the abstract contract in [backend/app/strategies/base.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/base.py).

Current strategies:

- `mean_reversion`
  Enters when price deviates materially from a rolling mean and exits when it normalizes.
- `breakout_guard`
  Trades directional breaks only after a volatility filter passes.
- `carry_drift`
  Follows directional drift and exits on mean re-entry.

[backend/app/strategies/registry.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/registry.py) is the source of truth for:

- registered strategies
- descriptions
- default instruments
- UI-exposed parameters
- position size and risk metadata

### Service Layer

Important services:

- [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py)
  Lists strategies, starts and stops runtimes, processes price updates, persists positions, and records trades.
- [backend/app/services/trade_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_service.py)
  CRUD-style persistence access for trades and positions.
- [backend/app/services/dashboard_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/dashboard_service.py)
  Aggregates KPIs, running strategy summaries, equity curve, drawdown, and exposure breakdowns.
- [backend/app/services/simulation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/simulation_service.py)
  Generates synthetic prices, starts default strategies, and advances the market when endpoints are hit.
- [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py)
  In live mode, polls prices from the broker and pushes them through active strategy runtimes.
- [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py)
  Syncs local open positions against remote broker positions.
- [backend/app/services/market_overview_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_overview_service.py)
  Builds category-level market readiness summaries and per-instrument rows.
- [backend/app/services/broker_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/broker_service.py)
  Thin façade for broker reads and reconciliation.

### Request Flow In Simulation Mode

Simulation mode is intentionally interactive. Many read endpoints advance the market by one tick before responding.

That means:

- refreshing the dashboard can change positions and trades
- loading positions can update unrealized PnL
- repeated local API calls are not idempotent from a data perspective

This is by design for a live-feeling demo environment.

### API Surface

Registered in [backend/app/api/router.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/router.py).

Main endpoints:

- `GET /health`
  Basic health check.
- `GET /dashboard`
  Dashboard KPIs and running strategy summary.
- `GET /charts/equity`
  Equity series.
- `GET /charts/drawdown`
  Drawdown series.
- `GET /charts/risk-allocation`
  Open-exposure allocation.
- `GET /positions`
  Open positions with enriched timing and PnL fields.
- `GET /trades`
  Closed trades, optionally filtered by strategy or date range.
- `GET /trades/positions`
  Compatibility endpoint for positions.
- `GET /strategies`
  Strategy metadata and runtime state.
- `POST /strategy/start`
  Start a strategy for a specific instrument.
- `POST /strategy/stop`
  Stop a strategy by instrument.
- `POST /strategies/{name}/start`
  Convenience start endpoint by strategy name.
- `POST /strategies/{name}/stop`
  Convenience stop endpoint by strategy name.
- `GET /markets/overview?category=forex`
  Market readiness snapshot for a category.
- `GET /broker/positions`
  Remote broker positions, useful as a broker-auth sanity check.

### Frontend Architecture

The frontend is a Next.js App Router app in [frontend](/Users/benparker/Documents/repos/codex-trading-app/frontend).

The main pattern is:

- server-render page
- fetch backend data via `frontend/lib/api.ts`
- pass typed data into focused presentational/client components

### Frontend Routing

- `/`
  Dashboard
- `/markets`
  Market readiness and instrument exploration
- `/strategies`
  Strategy control surface

Navigation lives in [frontend/components/app-nav.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/app-nav.tsx).

### Frontend Data Layer

[frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts) is the central API client.

Important behavior:

- all requests are no-store fetches
- health checks determine whether the frontend is in live mode or dev fallback mode
- if the backend is unreachable during development, many views fall back to local mock data
- market overview requests get a longer timeout than the rest of the app

This is why the UI still works when the backend is down, but not every feature is truly backed by the server in that state.

### Dashboard Page

[frontend/app/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/page.tsx) composes:

- `ModeIndicator`
- `KpiBar`
- `EquityPanel`
- `RiskPanel`
- `RiskAllocationPanel`
- `StrategyTapePanel`
- `OpenPositionsTable`
- `RecentTradesTable`

What it shows:

- account value and daily PnL
- win rate and risk/reward
- open book risk and exposure concentration
- running strategies and last seen prices
- open positions and recent trades

Notable implementation detail:

- some analytics are calculated in the backend and some are recomputed in the page from returned data

### Markets Page

[frontend/app/markets/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/markets/page.tsx) loads the default forex overview, then delegates richer interactions to [frontend/components/markets/market-overview-dashboard.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/markets/market-overview-dashboard.tsx).

What it supports:

- category switching
- lazy loading other market categories
- local watchlist starring stored in browser local storage
- tradable-only and active-only filters
- search across name, symbol, and compatible strategies
- countdown messaging for the next session transition

### Strategies Page

[frontend/app/strategies/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/strategies/page.tsx) renders a control surface for registered strategies.

What it supports:

- start/stop actions against backend endpoints
- instrument override selection before strategy start
- display of trade count, win rate, PnL, and last price
- side drawer for editable strategy settings

Important limitation:

- the settings drawer edits are currently UI-only and are not persisted to the backend

## Real Functionality Vs Simulated UX

This repo mixes real backend behavior with deliberately simulated UI affordances. That is useful for development, but it is worth calling out clearly.

Backed by real backend state:

- strategy registry and runtime state
- start/stop strategy endpoints
- persisted trades and positions
- dashboard aggregates
- IG authentication checks
- live broker position reconciliation
- market overview generation

Currently simulated or local-only in the frontend:

- dashboard position row drift animation
- "Sim Close" actions in the open positions table
- manual override toggles in the open positions table
- strategy settings drawer save action
- all fallback data shown when the backend is unavailable in development

## How A Trade Flows Through The System

1. A strategy runtime is started through `StrategyService`.
2. The runtime manager creates a `TradingEngine` bound to one strategy and one instrument.
3. A price update arrives from simulation or broker polling.
4. The engine calls `strategy.on_price_update(...)`.
5. If `should_enter_trade()` returns true, the engine places an order through the broker adapter.
6. The resulting position is reflected into persistence by `StrategyService`.
7. On later price updates, unrealized PnL is recalculated for the open position.
8. If `should_exit_trade()` returns true, the engine closes the broker position and returns a `Trade`.
9. `StrategyService` records the closed trade and closes the persisted position.

This flow is the core of the codebase. Everything else is mostly presentation, orchestration, or broker integration around it.

## Working On The Codebase

### Adding A New Strategy

1. Create a new strategy in [backend/app/strategies](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies).
2. Implement the abstract methods from `Strategy`.
3. Register it in [backend/app/strategies/registry.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/registry.py) with metadata for description, parameters, risk, and default instrument.
4. Confirm it appears in `GET /strategies` and on the Strategies page.

### Adding A New Broker

Follow [backend/app/core/BROKER_INTEGRATION.md](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/BROKER_INTEGRATION.md).

The short version:

1. implement the `Broker` interface
2. add provider config
3. wire it into `broker_factory.py`
4. keep translation and auth inside the adapter
5. let services and the engine continue to depend only on the normalized broker contract

### Extending The Frontend

Good places to start:

- new page route in [frontend/app](/Users/benparker/Documents/repos/codex-trading-app/frontend/app)
- new typed request in [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts)
- new view model types in [frontend/lib/types.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/types.ts)
- focused UI in [frontend/components](/Users/benparker/Documents/repos/codex-trading-app/frontend/components)

## Known Gaps And Caveats

- No automated test suite is present yet.
- Runtime state is in-memory, so active strategy assignments do not survive process restarts.
- Simulation mode advances on many read requests, which is great for demos but surprising if you expect static reads.
- The frontend strategy settings drawer does not persist configuration changes.
- The open positions table exposes simulated controls that do not send backend actions.
- Broker support is effectively single-provider today, via IG.
- The backend uses a local SQLite file by default; production would likely need PostgreSQL and background workers.

## Suggested Next Improvements

1. Add tests around strategies, services, and the IG adapter boundary.
2. Persist runtime assignments so strategies survive backend restarts.
3. Turn UI-only controls into real backend mutations or label them even more explicitly.
4. Split simulation advancement from read endpoints if deterministic reads become important.
5. Add streaming price updates instead of relying only on polling and page refreshes.

## Reference Files

- [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py)
- [backend/app/core/trading_engine.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/trading_engine.py)
- [backend/app/core/runtime.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/runtime.py)
- [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py)
- [backend/app/services/simulation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/simulation_service.py)
- [backend/app/services/market_overview_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_overview_service.py)
- [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts)
- [frontend/app/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/page.tsx)
- [frontend/app/markets/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/markets/page.tsx)
- [frontend/app/strategies/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/strategies/page.tsx)
