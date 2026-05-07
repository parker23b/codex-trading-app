# Architecture

InvestMate is organized around a FastAPI backend, a Next.js operator console, SQLModel persistence, and an IG broker adapter. It is built for supervised autonomy rather than manual point-and-click trading.

## High-Level Flow

```text
Frontend operator console
  -> FastAPI routes
    -> application services
      -> runtime manager / control plane / coverage allocator / trade allocator
        -> trading engine
          -> strategies + broker adapter
            -> SQLModel persistence + broker state
```

## Core Boundaries

- Strategies own trading or screening logic.
- The trading engine connects strategy decisions to broker-facing orchestration.
- Services own persistence, governance, deployment, recovery, reconciliation, coverage, allocation, and derived read models.
- Routes stay thin and expose service results over HTTP.
- Broker-specific behavior stays behind normalized broker interfaces.
- Frontend surfaces render backend truth and should not upgrade degraded, fallback, or estimated data into broker-confirmed certainty.

## Backend Startup

On startup, [../backend/app/main.py](../backend/app/main.py):

1. configures logging
2. initializes database tables
3. runs runtime recovery against persisted runtime state
4. starts the market-data loop
5. starts the system health heartbeat loop
6. starts the IG streaming loop when streaming is enabled

This makes backend startup stateful: it restores runtime state where possible, begins health tracking, and may start polling or streaming. Current audit findings still track duplicate-loop risk across reloads or multiple workers.

## Autonomy Layers

The intended control flow is:

1. Governance defines what each strategy family may do.
2. Operator control enables or overrides global autonomy.
3. Deployment chooses system-owned autonomous lifecycle state.
4. Runtime is a running strategy instance with `MANUAL` or `AUTO` control and `NORMAL`, `EXITS_ONLY`, or `STOPPED` runtime mode.
5. Coverage and market data determine which instruments can be evaluated.
6. Risk and allocation controls admit or reject entry candidates.
7. Broker execution happens only after the decision boundary is satisfied.
8. Reconciliation and recovery preserve evidence for broker/local drift.

## State Ownership

- Broker state is authoritative for actual open positions and confirmed closes.
- The local database is authoritative for app metadata, governance, deployments, runtime snapshots, executions, review history, and event history.
- In-memory runtime state is active process state and cached pricing, not long-term source of truth.

Important tables:

- `TradeIntent` - pre-trade decision lifecycle and close/recovery ownership.
- `Execution` - broker attempt and execution audit.
- `Position` - live local exposure.
- `Trade` - closed realized outcome.
- `StrategyRuntimeState` - persisted runtime assignment, profile, mode, recovery state, cached price, and serialized strategy snapshot.
- `ReconciliationEvent` - broker-vs-local drift detection and recovery audit.
- `DomainEvent` - operational events across strategy, health, reconciliation, coverage, and operator actions.
- `GeneratedReviewRecord` - persisted reviewer outputs and history.
- `StrategyGovernance` - per-family approval and autonomy rules.
- `StrategyDeployment` - autonomous deployment selection and state.
- `PromotionRequest` and `WatchlistEntry` - coverage allocation and streaming/watchlist state.

## Service Map

- [../backend/app/services/strategy_service.py](../backend/app/services/strategy_service.py) - strategy listing, runtime control, price processing, risk gating, execution progression, and persistence updates.
- [../backend/app/services/trade_decision_service.py](../backend/app/services/trade_decision_service.py) - entry proposal, risk/allocation gates, same-instrument conflict handling, and `TradeIntent` admission/rejection.
- [../backend/app/services/trade_service.py](../backend/app/services/trade_service.py) - persistence helpers for intents, executions, positions, trades, alerts, and reconciliation evidence.
- [../backend/app/services/strategy_deployment_manager_service.py](../backend/app/services/strategy_deployment_manager_service.py) - autonomous deployment reconciliation.
- [../backend/app/services/control_plane_service.py](../backend/app/services/control_plane_service.py) - control-plane summary and family detail serialization.
- [../backend/app/services/coverage_service.py](../backend/app/services/coverage_service.py) - streaming coverage, promotion, and allocator summary.
- [../backend/app/services/market_data_service.py](../backend/app/services/market_data_service.py) - Tier 1 polling fallback, Tier 2 refresh, promotion generation, and deployment reconciliation triggers.
- [../backend/app/services/reconciliation_service.py](../backend/app/services/reconciliation_service.py) - local and broker position reconciliation.
- [../backend/app/services/runtime_recovery_service.py](../backend/app/services/runtime_recovery_service.py) - restart recovery for persisted runtimes.
- [../backend/app/services/health_service.py](../backend/app/services/health_service.py) - system health and status aggregation.
- [../backend/app/services/operational_telemetry_service.py](../backend/app/services/operational_telemetry_service.py) - telemetry summary for health, broker, stream, runtimes, and failures.
- [../backend/app/services/dashboard_service.py](../backend/app/services/dashboard_service.py) - dashboard aggregates.
- [../backend/app/services/market_overview_service.py](../backend/app/services/market_overview_service.py) - market-category investigation views.

## Frontend Shape

The frontend is a Next.js App Router application under [../frontend](../frontend). Server pages load backend data through [../frontend/lib/api.ts](../frontend/lib/api.ts), then pass typed initial data into focused client components.

Primary routes:

- `/`
- `/live`
- `/risk`
- `/control-plane`
- `/coverage`
- `/markets`
- `/events`
- `/strategies`
- `/reviewer`

Navigation lives in [../frontend/components/app-nav.tsx](../frontend/components/app-nav.tsx). AIMEE drawer components live under [../frontend/components/aimee](../frontend/components/aimee).

## Related Docs

- [trade-lifecycle.md](trade-lifecycle.md)
- [backend-api-routes.md](backend-api-routes.md)
- [readiness.md](readiness.md)
- [audit-status.md](audit-status.md)
