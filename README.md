# Investmate Trading Platform

Personal algorithmic trading monorepo with a FastAPI backend, a Next.js operator console, IG broker integration, a governed autonomous control plane, bounded market-data coverage, runtime persistence and recovery, and an AI reviewer for operational summaries and audit history.

## Short Version

This system is an operator console for supervised autonomous trading.

- Strategy code generates signals.
- A control plane decides which strategy families are allowed to run, where they should be deployed, and which approved profile they should use.
- A coverage layer decides which instruments deserve scarce streaming attention.
- A trade allocator and risk controls decide which signals are allowed to take risk.
- The broker adapter handles market reads and order execution.
- The frontend is primarily a live operations UI for supervision, investigation, review, and intervention.

The platform is best understood as:

`governed autonomy -> bounded market coverage -> risk-filtered execution -> broker reconciliation -> operator supervision`

## What The System Does

The current app exposes these main operator surfaces:

1. Operate
   Dashboard for PnL, open risk, executions, positions, broker state, stream health, coverage summary, and control-plane summary.
2. Control Plane
   Governance, autonomous-control state, deployment alignment, and family-level deployment detail.
3. Coverage
   Tier 1 streaming coverage, Tier 2 refresh activity, promotion requests, allocator output, and operating limits.
4. Investigate
   Market-category overview for deployability, tradability, and strategy fit.
5. Events
   Domain-event timeline with filters for operational, risk, reconciliation, and health events.
6. AI Reviewer
   Deterministic operator summary plus persisted review history, with optional future LLM augmentation.
7. Strategies
   Strategy registry, deployment/runtime state, warnings, executions, and manual runtime start or stop actions.

## Overall Architecture

The codebase is organized around a few boundaries:

- Strategies are pure trading or screening logic.
- The trading engine connects strategy decisions to broker actions.
- Services own orchestration, persistence, governance, recovery, reconciliation, and derived summaries.
- Routes stay thin and expose service results over HTTP.
- Broker-specific behavior stays behind the normalized broker interface.

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

## Trade Decision Architecture

This backend now uses an intent-first ownership model:

- `TradeIntent` is the sole decision-lifecycle authority.
- `Execution` is broker-attempt and execution-audit only.
- `Position` is live exposure.
- `Trade` is the closed realised outcome.

### End-To-End Ownership Chain

1. Raw strategy signal generation
   Strategy logic decides raw alpha intent inside [backend/app/core/trading_engine.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/trading_engine.py), which creates `EntrySignal` and `ExitSignal` objects from strategy conditions.
2. TradeIntent proposal and admission
   [backend/app/services/trade_decision_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_decision_service.py) converts raw entry candidates into durable `TradeIntent` records, resolves same-instrument conflicts, applies market/risk/sizing/broker-size gates, and transitions intents to `APPROVED` or `REJECTED`.
3. Execution creation and broker-attempt lifecycle
   [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py) only creates an `Execution` after an admitted intent is ready to enter broker orchestration. New execution rows begin at `SUBMISSION_PENDING`, then progress through broker-attempt states such as `ORDER_SUBMITTED`, `ORDER_ACKNOWLEDGED`, `FILL_PARTIAL` / `FILL_FULL`, `FAILED`, `CANCELLED`, `NEEDS_MANUAL_REVIEW`, and terminal execution outcomes like `POSITION_OPENED` / `CLOSE_CONFIRMED`.
4. Position as live exposure
   [backend/app/services/trade_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_service.py) persists `Position` when a filled execution opens live exposure. `Position` remains the source of truth for current open exposure.
5. Trade as closed realised outcome
   On close completion, [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py) persists a `Trade`, closes the `Position`, and transitions the linked `TradeIntent` to `CLOSED`.

### File And Service Boundaries

- Raw strategy signals are created in [backend/app/core/trading_engine.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/trading_engine.py).
- Strategy candidate collection and runtime orchestration live in [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py).
- `TradeIntent` creation plus proposal/admission/rejection live in [backend/app/services/trade_decision_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_decision_service.py).
- `TradeIntent`, `Execution`, `Position`, and `Trade` models live in [backend/app/models/trade.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/models/trade.py).
- Persistence helpers for intents, executions, positions, trades, and reconciliation events live in [backend/app/services/trade_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_service.py).
- Recovery attaches broker-confirmed positions to explicit intents in [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py).
- Reconciliation adopts external positions and records forced reconciliation closes in [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py).

### Authoritative Ownership

- `TradeIntent` owns decision lifecycle only:
  proposal, approval, rejection, close intent, recovery/adoption states, and final close outcome.
- `Execution` owns execution-attempt lifecycle only:
  creation of a broker attempt, submission, acknowledgment, fill/failure/cancel/manual review, and execution terminal audit milestones.
- Rejected trade decisions do not create `Execution` rows.
- No order submission is allowed without a linked authoritative `TradeIntent`.

### Same-Instrument Exclusivity

The backend enforces one active instrument owner at a time.

- Application-level conflict resolution happens first in [backend/app/services/trade_decision_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_decision_service.py).
- Persistence-level enforcement lives in [backend/app/models/trade.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/models/trade.py) as the partial unique index `uq_trade_intent_active_instrument`.
- The index applies to active ownership states:
  `PROPOSED`, `APPROVED`, `SUBMITTED`, `ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `POSITION_OPENED`, `CLOSE_REQUESTED`, `EXTERNAL_POSITION_ADOPTED`, `RECOVERED_POSITION_ATTACHED`.
- If two concurrent workers race to admit the same instrument, the database rejects the second active owner and [backend/app/services/trade_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_service.py) raises `ActiveTradeIntentConflictError`, which [backend/app/services/trade_decision_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/trade_decision_service.py) converts into a structured `instrument_already_allocated` rejection.

### Recovery And Reconciliation

- Runtime recovery in [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py) never resumes or persists a live recovered `Position` without first creating or linking a `TradeIntent`. Recovered broker-confirmed positions use `RECOVERED_POSITION_ATTACHED`.
- Reconciliation in [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py) never silently mutates exposure:
  unmatched broker positions create explicit adopted lifecycle records such as `EXTERNAL_POSITION_ADOPTED`, and broker-missing local positions create explicit forced-close lifecycle records such as `FORCED_RECONCILIATION_CLOSE`.

### Core Invariants

- No order submission without an authoritative `TradeIntent`.
- No exit without a linked close-valid intent.
- No recovered live position without a linked `TradeIntent`.
- One active instrument owner at a time.

### Compatibility Notes

- `ExecutionStatus` still retains a small set of deprecated legacy values in [backend/app/models/trade.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/models/trade.py):
  `SIGNAL_GENERATED`, `RISK_APPROVED`, `RISK_REJECTED`, and `CLOSE_REQUESTED`.
- Those values remain only for compatibility with older persisted rows. New code paths do not write them.
- New execution rows start at `SUBMISSION_PENDING`.
- At this stage the developer SQLite database can be safely recreated instead of migrated. The codebase is still moving quickly enough that dropping and recreating the dev DB is the simpler path.

## Autonomous Operating Model

The product is built around supervised autonomy rather than a purely manual "pick a strategy and launch it" workflow.

The intended control flow is:

1. Governance defines what each strategy family is allowed to do.
2. Operator controls decide whether global autonomous control is enabled.
3. The deployment manager selects approved instruments and profiles for governed families.
4. Coverage allocation decides which instruments receive scarce Tier 1 streaming capacity.
5. Price updates and screening refreshes create candidate opportunities.
6. Risk controls and the trade allocator decide which signals deserve capital.
7. The execution path places or simulates orders through the broker adapter.
8. Reconciliation and recovery keep local state aligned with broker truth.

### Control Plane Layers

- Governance layer
  Family approvals, asset-class limits, approved instruments, approved profiles, emergency stop, and concurrency limits.
- Operator control layer
  Global autonomous-control enablement plus temporary override state and reason.
- Strategy deployment manager
  Chooses deployment state such as `AUTO_DEPLOYED`, `AUTO_PAUSED`, `DEGRADED`, `BLOCKED`, or `EMERGENCY_STOPPED`.
- Coverage allocator
  Manages bounded Tier 1 streaming slots and Tier 2 promotion flow.
- Trade allocator
  Filters competing signals and limits simultaneous risk concentration.

### Current Operator Posture

The app currently defaults toward allowed autonomy unless explicitly disabled.

- Global autonomous control is enabled by default.
- Strategy governance can still disallow autonomous operation per family.
- Emergency stop still overrides the autonomy default.
- Manual runtime controls remain available for supervised intervention, smoke runs, and debugging.

## Repository Layout

```text
backend/
  app/
    api/
      router.py
      routes/
    core/
      broker.py
      broker_factory.py
      config.py
      ig_broker.py
      instrument_catalog.py
      runtime.py
      trading_engine.py
      websocket_manager.py
      BROKER_INTEGRATION.md
    db/
      init_db.py
      session.py
    models/
      domain_event.py
      operator_control.py
      promotion_request.py
      review.py
      runtime.py
      strategy_deployment.py
      strategy_governance.py
      trade.py
      watchlist.py
    reviewer/
    services/
    strategies/
    main.py
  pyproject.toml
  .env.example

frontend/
  app/
    page.tsx
    control-plane/page.tsx
    coverage/page.tsx
    events/page.tsx
    markets/page.tsx
    reviewer/page.tsx
    strategies/page.tsx
    layout.tsx
  components/
  lib/
    api.ts
    types.ts
    format.ts
  package.json
  .env.example
```

## Backend Startup

On startup, [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py) currently:

1. configures logging
2. initializes database tables
3. runs runtime recovery against persisted runtime state
4. starts the market-data loop
5. starts the system health heartbeat loop
6. starts the IG streaming loop if streaming is enabled

This means the backend is stateful on boot:

- it restores persisted runtime state where possible
- it immediately begins health tracking
- it may start polling or streaming based on configuration

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

Default backend behavior from the current code and env example:

- uses SQLite at `backend/trading_platform.db`
- creates tables automatically on startup
- uses the IG broker adapter in `DEMO` mode
- keeps `IG_TRADING_ENABLED=false` by default
- enables IG streaming by default
- keeps AI reviewer LLM augmentation disabled by default

Backend URL: [http://localhost:8000](http://localhost:8000)

Useful endpoints to sanity-check startup:

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/system/health](http://localhost:8000/system/health)
- [http://localhost:8000/control-plane/summary](http://localhost:8000/control-plane/summary)
- [http://localhost:8000/coverage/summary](http://localhost:8000/coverage/summary)
- [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- [http://localhost:8000/reviews/operator-summary](http://localhost:8000/reviews/operator-summary)

### 2. Start The Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL: [http://localhost:3000](http://localhost:3000)

### 3. Configure IG Demo Connectivity

Update `backend/.env` with your IG demo credentials:

```env
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
4. Verify stream or market health via `GET /health/stream` and `GET /system/health`.
5. Verify market inspection via `GET /markets/overview?category=forex`.
6. Only then consider enabling real dealing behavior.

Important current behavior:

- The backend always uses the IG broker adapter.
- When `IG_TRADING_ENABLED=false`, order placement and close requests are simulated locally inside the IG adapter.
- Market reads, auth, account state, and positions are still broker-oriented.

## Environment Variables

The backend loads from `backend/.env`. The frontend loads from `frontend/.env.local`.

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
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_ID=
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_REQUEST_TIMEOUT_SECONDS=10
IG_TRADING_ENABLED=false
IG_STREAMING_ENABLED=true
IG_STREAMING_WATCH_INTERVAL_SECONDS=1
IG_MARKET_CACHE_TTL_SECONDS=30
IG_MARKET_CACHE_STALE_TTL_SECONDS=300
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
AI_REVIEWER_LLM_ENABLED=false
AI_REVIEWER_LLM_PROVIDER=disabled
AI_REVIEWER_LLM_MODEL=unconfigured
```

### Backend Variables That Matter Most

- `DATABASE_URL`
  SQLModel connection string. Relative SQLite paths are normalized against `backend/`.
- `BROKER_PROVIDER`
  Current allowed value is `IG`.
- `BROKER_MODE`
  `DEMO` or `LIVE`.
- `IG_TRADING_ENABLED`
  Safety switch for live dealing endpoints.
- `IG_STREAMING_ENABLED`
  Enables the streaming loop and affects whether the market-data service relies on polling fallback.
- `MARKET_DATA_POLL_INTERVAL_SECONDS`
  Main market-data loop cadence.
- `AI_REVIEWER_LLM_ENABLED`
  Keeps the reviewer deterministic by default when `false`.
- `STARTING_ACCOUNT_VALUE`
  Baseline account value used in dashboard calculations.

### Frontend Example

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_ENABLE_DEV_FALLBACK=true
```

### Frontend Variables

- `NEXT_PUBLIC_API_BASE_URL`
  Base URL used for backend requests.
- `NEXT_PUBLIC_ENABLE_DEV_FALLBACK`
  Present in the frontend env example, but the current frontend code does not actively branch on this variable. Request failures fall back to empty placeholder data through the shared loader helpers.

## Persistence And State Ownership

The backend treats state ownership as an explicit boundary:

- Broker state is authoritative for actual open positions and confirmed closes.
- The local database is authoritative for app metadata, governance, deployments, runtime snapshots, executions, review history, and event history.
- In-memory runtime state is active process state and cached pricing, not long-term source of truth.

Key tables:

- `Trade`
  Closed trade history with PnL, `r_multiple`, outcome, and broker references.
- `Position`
  Open-position record plus local metadata such as `risk_percent`, `reason`, `manual_override`, and reconciliation markers.
- `Execution`
  Auditable entry and close lifecycle with status transitions and rejection details.
- `StrategyRuntimeState`
  Persisted runtime assignment, profile, parameters, recovery state, cached price, and serialized strategy snapshot.
- `ReconciliationEvent`
  Audit trail for broker-vs-local drift detection and recovery.
- `DomainEvent`
  Operational event stream across strategy, health, reconciliation, coverage, and operator actions.
- `GeneratedReviewRecord`
  Persisted AI reviewer outputs and review history.
- `StrategyGovernance`
  Per-family approval and autonomy rules.
- `StrategyDeployment`
  Current autonomous deployment selection and state.
- `PromotionRequest` and `WatchlistEntry`
  Coverage allocation and streaming/watchlist state.

### Runtime Persistence And Recovery

Runtime assignments do survive restarts now.

The current lifecycle is:

1. running engines are mirrored into `StrategyRuntimeState`
2. the backend starts
3. `RuntimeRecoveryService` loads active persisted runtimes
4. broker positions are queried
5. runtimes are resumed, paused, or marked `RECOVERY_REQUIRED`

That makes persisted runtime state a real architectural feature, not a future idea.

## Strategies

Strategies live in [backend/app/strategies](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies). The registry in [backend/app/strategies/registry.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/registry.py) is the source of truth for:

- registered strategy names
- descriptions
- default instruments
- parameter definitions
- parameter profiles
- supported asset classes
- trade sizing and risk metadata

Currently registered trading strategies include:

- `mean_reversion`
- `breakout_guard`
- `carry_drift`
- `fx_micro_pullback`
- `volatility_adjusted_pullback_continuation`
- `smoke_test_hold`
- `bad_trade_flow`

The system also includes a screening strategy:

- `activity_surveillance_scanner`

## Service Layer

Important backend services:

- [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py)
  Strategy listing, runtime control, price processing, risk gating, execution progression, and persistence updates.
- [backend/app/services/strategy_deployment_manager_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_deployment_manager_service.py)
  Autonomous deployment reconciliation and state transitions.
- [backend/app/services/control_plane_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/control_plane_service.py)
  Control-plane summary and family detail serialization.
- [backend/app/services/coverage_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/coverage_service.py)
  Streaming coverage, promotion, and allocator summary.
- [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py)
  Tier 1 polling fallback, Tier 2 refresh, promotion generation, and deployment reconciliation triggers.
- [backend/app/services/reconciliation_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/reconciliation_service.py)
  Local and broker position reconciliation.
- [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py)
  Restart recovery for persisted runtimes.
- [backend/app/services/health_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/health_service.py)
  System health and status aggregation.
- [backend/app/services/operational_telemetry_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/operational_telemetry_service.py)
  Telemetry summary for health, broker, stream, runtimes, and failures.
- [backend/app/services/dashboard_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/dashboard_service.py)
  Dashboard aggregates.
- [backend/app/services/market_overview_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_overview_service.py)
  Market-category investigation views.

## API Surface

Routes are registered in [backend/app/api/router.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/api/router.py).

Key endpoints:

- `GET /health`
  Basic health status.
- `GET /health/stream`
  Streaming health and subscription state.
- `GET /system/health`
  Detailed system-health report.
- `GET /system/telemetry`
  Operational telemetry summary.
- `GET /system/limits`
  Runtime, execution, and coverage operating limits.
- `GET /dashboard`
  Dashboard snapshot.
- `GET /charts/equity`
  Equity series.
- `GET /charts/drawdown`
  Drawdown series.
- `GET /charts/risk-allocation`
  Risk-allocation chart data.
- `GET /positions`
  Enriched open positions.
- `GET /trades`
  Closed trades.
- `GET /trades/positions`
  Compatibility positions endpoint used by the frontend.
- `GET /executions`
  Recent execution records.
- `GET /strategies`
  Strategy registry plus runtime, governance, deployment, and warning state.
- `POST /strategy/start`
  Manual start for a specific strategy and instrument.
- `POST /strategy/stop`
  Manual stop by strategy and/or instrument.
- `POST /strategies/{name}/start`
  Convenience start by strategy name.
- `POST /strategies/{name}/stop`
  Convenience stop by strategy name.
- `GET /control-plane/summary`
  Global control-plane summary.
- `GET /control-plane/operator-state`
  Operator autonomy state.
- `PUT /control-plane/operator-state`
  Update global autonomy override.
- `GET /control-plane/strategies/{strategy_name}`
  Family-level control-plane detail.
- `PUT /control-plane/governance/{strategy_name}`
  Update strategy governance.
- `POST /control-plane/reconcile`
  Trigger deployment reconciliation.
- `GET /coverage/summary`
  Coverage, promotions, and trade allocator summary.
- `GET /markets/overview?category=forex`
  Market investigation overview.
- `GET /events`
  Domain-event list with filters.
- `GET /events/{event_id}`
  Single event detail.
- `GET /reviews/operator-summary`
  Deterministic reviewer summary.
- `GET /reviews/history`
  Review history.
- `GET /reviews/history/{review_id}`
  Review record detail.
- `GET /reviews/daily`
  Daily review.
- `GET /reviews/runtime-health`
  Runtime-health review.
- `GET /reviews/strategies/{strategy_name}`
  Strategy review.
- `GET /reviews/trades/{trade_id}/postmortem`
  Trade postmortem review.
- `POST /reviews/questions`
  Operational question answering.
- `POST /testing/reset-history`
  Test/dev reset endpoint used by the Events page.

## Frontend Architecture

The frontend is a Next.js App Router application under [frontend](/Users/benparker/Documents/repos/codex-trading-app/frontend).

The main pattern is:

- server-render a page
- load backend data through [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts)
- pass typed initial data into focused client or presentational components

### Current Routes

- `/`
  Operate dashboard
- `/control-plane`
  Autonomous control-plane view
- `/coverage`
  Coverage and allocator view
- `/markets`
  Investigation view
- `/events`
  Domain-event console
- `/reviewer`
  AI reviewer console
- `/strategies`
  Strategy operations view

Navigation lives in [frontend/components/app-nav.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/app-nav.tsx).

### Frontend Data Behavior

The current frontend data layer:

- uses `no-store` fetches
- uses short request timeouts for most backend calls
- uses a longer timeout for market-overview requests
- falls back to empty placeholder data through `loadWithMeta()` when a request fails
- returns an error string alongside fallback data so pages can surface degraded state

Important current caveat:

- `NEXT_PUBLIC_ENABLE_DEV_FALLBACK` exists in the env example, but the shared client code does not currently gate behavior on it.
- `getBackendMode()` is currently hardcoded to `"live"`.

## Frontend Pages

### Operate Dashboard

[frontend/app/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/page.tsx) loads:

- positions
- trades
- executions
- broker auth
- dashboard snapshot
- stream health
- coverage summary
- control-plane summary
- system operating limits

It is the main supervision surface rather than a simple PnL page.

### Control Plane

[frontend/app/control-plane/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/control-plane/page.tsx) renders the autonomous-control summary and family-level alignment state.

### Coverage

[frontend/app/coverage/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/coverage/page.tsx) focuses on:

- Tier 1 streaming state
- Tier 2 refresh activity
- promotion lifecycle
- operational telemetry
- operating limits

### Investigate

[frontend/app/markets/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/markets/page.tsx) loads a market-category overview and supports interactive market inspection.

### Events

[frontend/app/events/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/events/page.tsx) exposes filtered operational history for strategy, execution, health, reconciliation, and operator events.

### AI Reviewer

[frontend/app/reviewer/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/reviewer/page.tsx) shows:

- lead observation
- supporting metrics
- warnings
- recent review history

### Strategies

[frontend/app/strategies/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/strategies/page.tsx) is the manual runtime operations view.

It currently supports:

- start and stop actions
- runtime and deployment visibility
- execution warnings
- profile and parameter visibility

## Trade And Runtime Flow

Current high-level execution flow:

1. A runtime is started manually or by the deployment manager.
2. `runtime_manager` creates a `TradingEngine` for one strategy and one instrument.
3. Price updates arrive from streaming-backed health, polling fallback, or Tier 2 refresh context.
4. The engine calls strategy logic.
5. Entry signals create `Execution` records.
6. Risk checks and trade allocation determine whether the entry may proceed.
7. Orders move through execution statuses such as `SIGNAL_GENERATED`, `RISK_APPROVED`, `ORDER_SUBMITTED`, `ORDER_ACKNOWLEDGED`, `FILL_PARTIAL`, `FILL_FULL`, and `POSITION_OPENED`.
8. Exits create close-side execution records.
9. Confirmed closes become `Trade` records.
10. Reconciliation and recovery maintain consistency with broker truth.

## Health, Coverage, And Streaming

The market-data and health model is now centered on bounded streaming plus fallback behavior.

- IG streaming can be enabled for Tier 1 instruments.
- The market-data loop can poll when streaming is disabled or stale.
- Tier 2 refresh scans a wider set of instruments at a lower cadence.
- Promotion requests can move instruments from Tier 2 into Tier 1.
- Domain events record stale-stream, fallback, promotion, allocation, and deployment-cycle activity.

This is a better description of the current system than the older "simulation mode" model.

## Testing

The repo does have automated backend tests under [backend/tests](/Users/benparker/Documents/repos/codex-trading-app/backend/tests).

Current coverage includes tests for:

- config parsing
- market data
- dashboard behavior
- strategy services
- broker services
- control plane
- coverage allocation
- watchlists
- health and telemetry
- reconciliation
- risk allocation
- strategy implementations

## Working On The Codebase

### Adding A New Strategy

1. Create the strategy in [backend/app/strategies](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies).
2. Implement the abstract contract from [backend/app/strategies/base.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/base.py).
3. Register metadata and profiles in [backend/app/strategies/registry.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/strategies/registry.py).
4. Verify it appears in `GET /strategies` and the Strategies page.

### Adding A New Broker

Follow [backend/app/core/BROKER_INTEGRATION.md](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/BROKER_INTEGRATION.md).

Current expectation:

1. implement the `Broker` interface
2. add provider config and validation
3. wire it through `broker_factory.py`
4. keep translation, auth, and provider quirks inside the adapter
5. keep services and engines dependent only on normalized broker contracts

### Extending The Frontend

Good entry points:

- new route in [frontend/app](/Users/benparker/Documents/repos/codex-trading-app/frontend/app)
- new typed request in [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts)
- new types in [frontend/lib/types.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/types.ts)
- focused UI components in [frontend/components](/Users/benparker/Documents/repos/codex-trading-app/frontend/components)

## Current Caveats

- The backend is effectively single-broker today: IG only.
- `IG_TRADING_ENABLED=false` still simulates fills locally inside the IG adapter, so not every execution is a real broker deal.
- The frontend fallback behavior is coarse: request failures degrade to placeholder data rather than a strongly modeled offline mode.
- The env example still includes `NEXT_PUBLIC_ENABLE_DEV_FALLBACK`, but the current client code does not actively use it.
- Reviewer LLM settings exist, but the default and safest mode is still deterministic-only review output.
- Local development defaults to SQLite; larger deployments would likely want a different database and clearer worker/process separation.

## Reference Files

- [backend/app/main.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/main.py)
- [backend/app/core/config.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/config.py)
- [backend/app/core/broker_factory.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/broker_factory.py)
- [backend/app/core/ig_broker.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/ig_broker.py)
- [backend/app/core/runtime.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/core/runtime.py)
- [backend/app/services/runtime_recovery_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/runtime_recovery_service.py)
- [backend/app/services/strategy_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_service.py)
- [backend/app/services/strategy_deployment_manager_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/strategy_deployment_manager_service.py)
- [backend/app/services/market_data_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/market_data_service.py)
- [backend/app/services/control_plane_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/control_plane_service.py)
- [backend/app/services/coverage_service.py](/Users/benparker/Documents/repos/codex-trading-app/backend/app/services/coverage_service.py)
- [frontend/lib/api.ts](/Users/benparker/Documents/repos/codex-trading-app/frontend/lib/api.ts)
- [frontend/components/app-nav.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/components/app-nav.tsx)
- [frontend/app/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/page.tsx)
- [frontend/app/control-plane/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/control-plane/page.tsx)
- [frontend/app/coverage/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/coverage/page.tsx)
- [frontend/app/events/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/events/page.tsx)
- [frontend/app/markets/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/markets/page.tsx)
- [frontend/app/reviewer/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/reviewer/page.tsx)
- [frontend/app/strategies/page.tsx](/Users/benparker/Documents/repos/codex-trading-app/frontend/app/strategies/page.tsx)
