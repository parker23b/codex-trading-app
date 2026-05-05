# Domain glossary

These terms are the shared vocabulary for code reviews and future specs. Where the authority is not fully identifiable, the term is marked `Needs confirmation`.

Glossary IDs are definitions, not behavioral invariants. Severity, required evidence, and test requirements belong to the requirement specs that reference these terms.

## Core autonomy layers

- Governance: operator-approved permission and constraints.
- Deployment: system-owned autonomous lifecycle choice.
- Runtime: actual running strategy instance and mode.
- Alignment: comparison between deployment intent and runtime reality.

## Lifecycle terms

| Spec ID | Term | Definition | Current authority / evidence | Common confusion to avoid | Related files |
| --- | --- | --- | --- | --- | --- |
| TERM-TRADEINTENT | TradeIntent | Durable authoritative record for a trade decision lifecycle. Raw strategy entry candidates become `PROPOSED`; approved entries may become execution attempts. Exit, recovery, and reconciliation activity should link to the relevant lifecycle when known, or create explicit auditable lifecycle evidence when the original intent is unavailable. | `TradeIntent` table and `TradeDecisionService`. | Do not use `Execution` as pre-trade approval truth. | `backend/app/models/trade.py`, `backend/app/services/trade_decision_service.py`, `backend/app/services/trade_service.py` |
| TERM-EXECUTION | Execution | Durable broker-attempt audit record linked to a `TradeIntent`. It starts at `SUBMISSION_PENDING` for new attempts and tracks submission, acknowledgement, fill/failure/cancel/manual-review states. Execution is evidence of an attempted broker action, not evidence that the broker action succeeded. | `Execution` table and strategy execution service. | Do not create execution rows for rejected entry decisions; do not treat submitted/acknowledged as filled. | `backend/app/models/trade.py`, `backend/app/services/strategy_service.py` |
| TERM-POSITION | Position | Local exposure record for broker or system-known market exposure. Open positions have `is_open=True`; closed or historical positions may remain for audit/reconciliation. | `Position` table plus broker reconciliation. | Local position truth may be provisional until broker-confirmed. | `backend/app/models/trade.py`, `backend/app/services/reconciliation_service.py` |
| TERM-TRADE | Trade | Closed realized outcome evidence, including close price/time and PnL. Trade is outcome evidence, not live-risk authority or intent state. | `Trade` table. | Do not treat an open position as a closed trade or use trades as the source for current exposure. | `backend/app/models/trade.py`, `backend/app/services/trade_service.py` |
| TERM-DOMAIN-EVENT | Domain event | Durable event describing a material lifecycle decision, transition, degraded condition, broker/reconciliation fact, or operator-relevant state change. | `DomainEvent` table and `DomainEventService`. | Logs are not a substitute for durable domain events where auditability is required. | `backend/app/models/domain_event.py`, `backend/app/services/domain_event_service.py` |
| TERM-RECONCILIATION | Reconciliation | Process that compares local lifecycle state with broker-confirmed truth and records differences, recoveries, drifts, or manual-review needs. | `ReconciliationService`, broker positions, `ReconciliationEvent`. | Reconciliation must not silently rewrite history without auditable evidence. | `backend/app/services/reconciliation_service.py`, `backend/app/models/trade.py` |
| TERM-RECOVERY | Recovery | Auditable process for bringing broker-discovered or out-of-band open risk back under local lifecycle management. | `RuntimeRecoveryService`, reconciliation tests. | Recovery is not permission to bypass lifecycle state; it reconstructs or explicitly marks missing lifecycle state. | `backend/app/services/runtime_recovery_service.py`, `backend/tests/test_runtime_recovery_service.py` |
| TERM-MANUAL-REVIEW | Manual review | State indicating the system cannot safely or confidently continue autonomous handling without operator attention. | `Execution.requires_manual_review`, `NEEDS_MANUAL_REVIEW` status, strategy-service tests. | Manual review is a controlled degraded state, not an unhandled exception. | `backend/app/models/trade.py`, `backend/app/services/strategy_service.py` |

## Autonomy/control terms

| Spec ID | Term | Definition | Current authority / evidence | Common confusion to avoid | Related files |
| --- | --- | --- | --- | --- | --- |
| TERM-STRATEGY | Strategy | Trading or screening logic that evaluates market inputs and emits entry/exit signals or promotion intents. | Strategy classes and registry. | Strategy signal generation is not broker execution approval. | `backend/app/strategies/*`, `backend/app/strategies/registry.py` |
| TERM-STRATEGY-FAMILY | Strategy family | Governance/allocation/reporting grouping for a strategy. In code this is often `family_name`, falling back to `strategy_name`. | Partially identifiable from strategy registry metadata and persisted `family_name`. | Allocation, governance, concurrency, and reporting can become misleading if family fallback behavior is inconsistent. | `backend/app/strategies/registry.py`, `backend/app/models/trade.py` |
| TERM-GOVERNANCE | Governance | Operator-approved policy for what a strategy family is allowed to do: approval state, autonomous permission, emergency stop, approved instruments/profiles, and concurrency. | `StrategyFamilyGovernance`. | Governance approval does not mean a deployment is active or a runtime is running. | `backend/app/models/strategy_governance.py`, `backend/app/services/strategy_governance_service.py` |
| TERM-DEPLOYMENT | Deployment | System-owned autonomous lifecycle choice: what the system intends to run/manage for a governed strategy family, including selected instrument/profile and open-risk management state. | `StrategyDeployment` and deployment manager. | Deployment state must not imply runtime alignment unless checked. | `backend/app/models/strategy_deployment.py`, `backend/app/services/strategy_deployment_manager_service.py` |
| TERM-RUNTIME | Runtime | Actual running strategy instance for a strategy/instrument pair, persisted as `StrategyRuntimeState` and managed in memory by `runtime_manager`. | Runtime manager and `StrategyRuntimeState`. | Runtime is not the same as deployment or governance. | `backend/app/core/runtime.py`, `backend/app/models/runtime.py` |
| TERM-CONTROL-PLANE | Control plane | Services and UI that coordinate governance, operator overrides, deployment, runtime alignment, and operational state. | Control-plane service and routes. | Control-plane reads may summarize backend truths but must not invent lifecycle, certainty, risk, broker, or runtime state not present in source data. | `backend/app/services/control_plane_service.py`, `backend/app/api/routes/control_plane.py`, `frontend/components/control-plane/*` |
| TERM-OPERATOR-OVERRIDE | Operator override | Explicit operator action that changes autonomy, governance, runtime, deployment, emergency stop, watchlist, alert, or manual-review state. | Operator control, governance routes, strategy controls, watchlist and alert routes. | Operator override is not the same as autonomous deployment choice. | `backend/app/models/operator_control.py`, `backend/app/api/routes/control_plane.py`, `backend/app/api/routes/strategies.py` |

## Risk/allocation terms

| Spec ID | Term | Definition | Current authority / evidence | Common confusion to avoid | Related files |
| --- | --- | --- | --- | --- | --- |
| TERM-ALLOCATION-CYCLE | Allocation cycle | Batch evaluation of competing entry candidates against account equity, broker sizing, risk budgets, concentration, and stale-signal gates. | `AllocationCycle` plus `TradeIntent.allocation_cycle_id`. | Allocation selection is not final broker execution. | `backend/app/services/capital_allocator_service.py`, `backend/app/models/trade.py` |
| TERM-RISK-TRUTH | Risk truth | Value plus confidence plus provenance for the current risk estimate/best-known risk of an intent, execution, position, or trade. It may be estimated, submitted, fill-derived, broker-confirmed, degraded, or provisional. | Risk fields on trade models and allocation read model. | A displayed risk number without confidence/provenance must not be treated as exact truth. | `backend/app/models/trade.py`, `backend/app/services/allocation_read_service.py` |
| TERM-RISK-TRUTH-CONFIDENCE | Risk truth confidence | Label describing the confidence/source of risk truth. Until centralized, known values are inferred from tests and model fields. Absence of confidence must be treated as unknown/degraded, not exact. | Needs confirmation; currently inferred from `risk_truth_confidence` fields and allocation read tests. | Do not assume missing confidence means exact broker-confirmed risk. | `backend/app/models/trade.py`, `backend/tests/test_allocation_read_service.py` |
| TERM-ENTRY-ELIGIBILITY | Entry eligibility | Combined decision of governance, market status, freshness, operational health, broker metadata, allocation, and risk gates determining whether a new entry may proceed. | Operational state, risk/allocation, strategy-service tests. | Tradable price data alone does not imply entry eligibility. | `backend/app/services/operational_state_service.py`, `backend/app/services/portfolio_risk_service.py`, `backend/app/services/capital_allocator_service.py` |
| TERM-EXIT-ELIGIBILITY | Exit eligibility | Decision path for reducing or closing known open risk, even when new entries are blocked. | Operational state and control-plane open-risk handling. | Entry blocks should not automatically block protective exits. | `backend/app/services/operational_state_service.py`, `backend/app/services/strategy_deployment_manager_service.py` |

## Market-data/coverage terms

| Spec ID | Term | Definition | Current authority / evidence | Common confusion to avoid | Related files |
| --- | --- | --- | --- | --- | --- |
| TERM-WATCHLIST | Watchlist | Operator/system list of instruments eligible for strategy evaluation, streaming, protective coverage, or Tier 2 refresh. | `WatchlistEntry`, `OperatorShortlistEntry`, watchlist service. | Shortlist does not necessarily imply streaming or trading. | `backend/app/models/watchlist.py`, `backend/app/services/watchlist_service.py` |
| TERM-TIER1-COVERAGE | Tier 1 coverage | Bounded active streaming coverage. Open positions and pending intents may be pinned/protective. | Watchlist streaming plan and IG streaming service. | Tier 1 streaming is not the same as entry eligibility. | `backend/app/services/watchlist_service.py`, `backend/app/services/ig_streaming_service.py` |
| TERM-TIER2-COVERAGE | Tier 2 coverage | Lower-frequency refresh/screening flow that can create promotion requests into Tier 1. | Tier 2 refresh plan and promotion service. | Tier 2 refresh should not imply live tick health. | `backend/app/services/market_data_service.py`, `backend/app/services/promotion_request_service.py` |
| TERM-MARKET-STATUS | Market status | Broker/derived status indicating open/tradable/degraded/closed/offline conditions for a market. | `MarketStatusService`, broker market details, operational-state summaries. | A price can exist while entry is still blocked. | `backend/app/services/market_status_service.py`, `backend/app/core/broker.py` |
| TERM-STREAMING-HEALTH | Streaming health | Lightstreamer enabled/connected/subscribed/tick freshness state. | `StreamHealthState`. | Successful fallback polling must not be reported as streaming connected. | `backend/app/services/ig_streaming_service.py`, `backend/tests/test_market_data_service.py` |
| TERM-FALLBACK-POLLING | Fallback polling | Broker REST market details polling used when streaming is disabled, unavailable, unsubscribed, or stale. Fallback polling can support observation and limited recovery, but entry eligibility must account for freshness, provenance, and configured risk rules. | `MarketDataService`. | Fallback data is lower-confidence than healthy live streaming and must not be hidden behind live/healthy labels. | `backend/app/services/market_data_service.py` |
| TERM-MARKET-DATA-FRESHNESS | Market-data freshness | Age, source, and provenance of market data used for strategy evaluation, risk checks, UI display, and execution revalidation. | Runtime manager, streaming health, operational-state service, market-data tests. | Latest available price is not necessarily fresh enough for entry. | `backend/app/core/runtime.py`, `backend/app/services/operational_state_service.py`, `backend/app/services/market_data_service.py` |
| TERM-PROVENANCE | Provenance | Source and confidence metadata explaining where a value came from and how much the operator should trust it. | Needs confirmation; appears across risk, feed-state, telemetry, review, and UI read models. | A displayed value without provenance should not be treated as exact truth. | `backend/app/services/allocation_read_service.py`, `frontend/lib/types.ts`, `frontend/lib/risk-allocation.ts` |

## Boundary/service terms

| Spec ID | Term | Definition | Current authority / evidence | Common confusion to avoid | Related files |
| --- | --- | --- | --- | --- | --- |
| TERM-AIMEE | AIMEE | Read-only operator companion that explains system state from passive snapshots and separate explicit advisory endpoints. Explicit advisory endpoints may persist advisory artifacts, but passive snapshot reads must remain side-effect free. | AIMEE read service and frontend drawer. | Passive AIMEE refresh must not reconcile, seed defaults, sync watchlists, call broker mutation paths, or persist reviews. | `backend/app/services/aimee_read_service.py`, `frontend/components/aimee/*` |
| TERM-READ-SERVICE | Read service | Service whose purpose is projection, summary, or query. A read service must not intentionally or indirectly mutate operational state, including through helper calls that seed defaults, refresh alerts, reconcile broker state, sync watchlists, create events, or commit/flush database changes. | Needs confirmation per service. | A service named like a read service can still be unsafe if helper calls write. Audit behavior, not names. | `backend/app/services/*_read_service.py`, dashboard/control-plane/coverage services |
| TERM-MUTATION-SERVICE | Mutation service | Service that intentionally changes operational state, broker state, governance, watchlists, alerts, runtimes, trades, reviews, or events. Mutation services must be invoked only from explicit mutation workflows, routes, jobs, or operator actions. | Service methods and route classification. | Mutations must be clear at route/UI boundaries and should not be hidden behind passive reads. | `backend/app/services/*`, `backend/app/api/routes/*` |
| TERM-BROKER-ADAPTER | Broker adapter | Broker-neutral interface implementation used by app services for reads, sizing, order placement, and position close. Raw broker payloads may be parsed inside concrete adapters, but app services should consume broker-neutral types. | `Broker` abstract base class. | App services should not consume raw IG payloads. | `backend/app/core/broker.py` |
| TERM-IG-ADAPTER | IG adapter | Concrete IG Markets implementation of broker auth/session, market details, order placement, close, sizing, and streaming credentials. | `IGBroker` and `IGStreamingService`. | IG pip/point/size semantics belong here or in broker-neutral quote objects. | `backend/app/core/ig_broker.py`, `backend/app/services/ig_streaming_service.py` |

## Known unknowns

- Exact enum set for `risk_truth_confidence` is not centralized.
- Whether all services named as reads are side-effect free is not fully proven.
- Strategy family semantics are partly inferred from registry metadata and fallbacks.
- Provenance is not a single centralized model yet.
- Frontend AIMEE drawer persistence behavior is mostly client-local from the files inspected; server-side advisory persistence belongs to explicit review/advisory endpoints.

## Required tests

- Contract tests for every lifecycle term whose state transitions affect trading safety.
- Regression tests proving UI names match backend terms for `TradeIntent`, `Execution`, governance, deployment, runtime, risk truth, and coverage states.
- Read-service tests proving no hidden helper writes for passive read paths.
- Risk truth confidence tests once the confidence label set is centralized.

## Audit questions for Codex

- Is there any code path that treats `ExecutionStatus.RISK_APPROVED` as current decision truth?
- Are `family_name` values consistently populated where allocation and risk summaries depend on them?
- Are frontend status labels directly mapped from backend semantics or reinterpreted locally?
- Which read services call helpers that can commit, flush, reconcile, seed defaults, refresh alerts, sync watchlists, or create events?
