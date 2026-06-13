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
- Services own persistence, governance, deployment, recovery, reconciliation, coverage, allocation, open-risk authority, and derived read models.
- Routes stay thin and expose service results over HTTP.
- Broker-specific behavior stays behind normalized broker interfaces.
- Frontend surfaces render backend truth and should not upgrade degraded, fallback, or estimated data into broker-confirmed certainty.

## Backend Startup

On startup, [../backend/app/main.py](../backend/app/main.py):

1. configures logging
2. initializes database tables
3. acquires the database-backed runtime lease and activates its monotonic generation
4. runs runtime recovery against persisted runtime state
5. starts the market-data loop
6. starts the independent broker-reconciliation supervisor
7. starts the system health and leadership heartbeat loop
8. starts the IG streaming loop when streaming is enabled

This makes backend startup stateful: it restores runtime state where possible, begins health tracking and reconciliation, and may start polling or streaming. The lease generation is checked at every real IG order/close boundary. The broker mutation holds the lease row until the operation finishes, so an expired leader cannot overlap a takeover and then continue mutating broker state.

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

Open-risk ownership:

- `Position` represents local exposure and broker linkage.
- `StrategyRuntimeState` represents persisted runtime exit authority and mode.
- `StrategyDeployment.open_risk_management_state` remains a family-level compatibility projection.
- `OpenRiskAuthority` is the versioned risk-book aggregate. Its snapshot records each open position's local/broker sync state, runtime owner, runtime mode/recovery state, deployment relationship, reconciliation freshness, and manual-review requirement.
- `OpenRiskAuthorityService` is the sole writer of the aggregate. Position, runtime, deployment, recovery, and reconciliation transitions refresh it after their durable lifecycle changes.
- `OperationalStateService` and operator telemetry read the aggregate rather than independently applying state precedence.

Important tables:

- `TradeIntent` - pre-trade decision lifecycle and close/recovery ownership.
- `Execution` - broker attempt and execution audit.
- `Position` - live local exposure.
- `Trade` - closed realized outcome.
- `StrategyRuntimeState` - persisted runtime assignment, profile, mode, recovery state, cached price, and serialized strategy snapshot.
- `OpenRiskAuthority` - versioned risk-book ownership, freshness, and per-position exit-authority snapshot.
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
- [../backend/app/services/broker_reconciliation_supervisor.py](../backend/app/services/broker_reconciliation_supervisor.py) - fixed-cadence broker reconciliation independent of watchlist and strategy coverage.
- [../backend/app/services/allocation_admission_lock.py](../backend/app/services/allocation_admission_lock.py) - process-local or Postgres transaction-level serialization of allocation and durable intent admission.
- [../backend/app/services/reconciliation_service.py](../backend/app/services/reconciliation_service.py) - local and broker position reconciliation.
- [../backend/app/services/runtime_leadership_service.py](../backend/app/services/runtime_leadership_service.py) - lease acquisition, monotonic generations, heartbeat/release checks, and broker-mutation fencing.
- [../backend/app/services/runtime_recovery_service.py](../backend/app/services/runtime_recovery_service.py) - restart recovery for persisted runtimes.
- [../backend/app/services/open_risk_authority_service.py](../backend/app/services/open_risk_authority_service.py) - versioned open-risk ownership and reconciliation-freshness authority.
- [../backend/app/services/health_service.py](../backend/app/services/health_service.py) - system health and status aggregation.
- [../backend/app/services/operational_telemetry_service.py](../backend/app/services/operational_telemetry_service.py) - telemetry summary for health, broker, stream, runtimes, and failures.
- [../backend/app/services/dashboard_service.py](../backend/app/services/dashboard_service.py) - dashboard aggregates.
- [../backend/app/services/market_overview_service.py](../backend/app/services/market_overview_service.py) - market-category investigation views.

## Current Architecture Gaps

- There is no deterministic event-replay/backtest architecture sharing the complete live strategy, allocation, risk, and lifecycle pipeline (`AUDIT-ARCH-003`).

The `2026-06-12` P0 remediation serializes one current account/risk book globally. Future account sharding must use a stable account-scoped lock key rather than weakening that boundary. The Postgres cross-connection allocation and leadership-fence rehearsals are committed but still require CI execution before broker-connected demo readiness is restored.

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
