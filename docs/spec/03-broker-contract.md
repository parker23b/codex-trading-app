# Broker contract

The broker contract isolates broker-specific market reads, sizing semantics, session handling, streaming credentials, order submission, and position closing from application services.

## Current broker boundary

| Layer | Current implementation | Notes |
| --- | --- | --- |
| Broker interface | `backend/app/core/broker.py` | Defines account, market, sizing, order, and position DTOs. |
| IG adapter | `backend/app/core/ig_broker.py` | Owns IG auth/session, REST calls, market parsing, order/close, local simulated fills when trading disabled. |
| Streaming | `backend/app/services/ig_streaming_service.py` | Owns Lightstreamer dependency, subscriptions, health, tick publication. |
| Broker factory | `backend/app/core/broker_factory.py` | Provides active broker. |
| Broker services | `backend/app/services/broker_service.py`, `reconciliation_service.py` | Reconcile broker truth with local positions/intents. |
| Tests | `backend/tests/test_ig_broker_sizing.py`, `test_capital_allocator_service.py`, `test_market_data_service.py`, `test_reconciliation_service.py`, `test_strategy_service.py` | Cover sizing, stale/fallback, reconciliation, execution failure cases. |

## Broker contract terminology

- Broker read: a broker call that retrieves broker/account/market/position/sizing information without intentionally changing broker state.
- Broker mutation: a broker call that can place, close, amend, cancel, or otherwise change broker-side trading state.
- Broker-neutral DTO: an application-facing data object defined by InvestMate, not by IG or any other broker payload schema.
- Lifecycle authority: durable local state that authorizes a broker mutation, such as an approved `TradeIntent`, a known open `Position`, a recovery/reconciliation path, or explicit operator action.
- Broker confirmation ambiguity: any state where the app cannot safely prove whether the broker accepted, rejected, filled, partially filled, or lost an order/close request.
- Simulated broker behavior: local development/demo behavior used when live trading is disabled. Simulated fills/closes are not broker-confirmed truth and must remain clearly distinguishable from live broker truth.

## Contract invariants

| Spec ID | Expected behavior | Required evidence | Severity if violated | Current verification confidence |
| --- | --- | --- | --- | --- |
| BROKER-001 | Application services outside broker adapter/streaming code MUST use broker-neutral interfaces and normalized DTOs for broker reads, sizing, order submission, and closes. They must not depend on raw IG payloads, IG enum strings, IG headers, IG session tokens, Lightstreamer implementation details, or IG pip/point/contract-value semantics. | Code search showing services depend on `Broker`, `OrderRequest`, `BrokerMarketDetails`, `BrokerRiskSizingQuote`, `BrokerSizeNormalization`, `BrokerOrderResult`, and `BrokerPosition`, not raw IG payloads. | P1 | Medium |
| BROKER-002 | Broker mutations MUST be reachable only through lifecycle-authorized paths and must be auditable with originating intent/recovery/operator authority, execution record where applicable, client request id where supported, broker reference/deal id where returned, and domain/reconciliation event or error evidence. | Strategy-service, trade-service, reconciliation, and route tests for success, failure, timeout, confirmation ambiguity, manual-review, and recovery paths. | P0 | Medium |
| BROKER-003 | Entry order submission must be linked to an approved `TradeIntent`. | Tests proving non-approved intents cannot submit and rejected decisions create no order attempts. | P0 | High |
| BROKER-004 | Exits must preserve an exit-capable path for open broker risk. | Control-plane/runtime tests for `EXITS_ONLY`, unmanaged risk events, and close failure manual review. | P0 | High |
| BROKER-005 | IG pip/point/size semantics must not leak into unrelated services. | Broker sizing quote/normalization tests; allocator should use broker-owned quote model. | P1 | High |
| BROKER-006 | Streaming health must not be falsely inferred from fallback polling unless explicitly designed and documented. Fallback polling can support observation and limited recovery, but it must remain visibly lower-confidence than healthy live streaming and must not by itself imply entry eligibility. | Market-data/telemetry tests proving fallback does not mark stream connected; UI tests proving fallback is displayed as degraded/provenanced data. | P1 | Medium |
| BROKER-007 | Broker read failures during allocation or market metadata lookup must fail closed for entries. | Allocator and strategy-service stale/metadata failure tests. | P0 | High |
| BROKER-008 | Position reconciliation must create explicit local lifecycle records for unmatched broker truth. | Reconciliation tests for adopted and forced-close intents/events. | P0 | High |
| BROKER-009 | Broker size normalization must be revalidated before submission and drift must be visible. | Strategy-service revalidation tests and allocation read drift tests. | P1 | High |
| BROKER-010 | Session/auth tokens and IG-specific headers must stay inside IG adapter/streaming code. | Code review of `ig_broker.py` and `ig_streaming_service.py`. | P1 | Medium |
| BROKER-011 | Entry orders require approved `TradeIntent` admission. Exit/close orders require known open risk, recovery/reconciliation authority, or explicit operator action. No broker-mutating path may exist as a raw utility call from arbitrary routes/services. | Tests tracing every `place_order` and `close_position` path back to lifecycle authority. | P0 | Medium |
| BROKER-012 | Broker confirmation ambiguity must fail safe. If an order or close request times out, loses confirmation, receives an unclear broker response, or cannot prove final broker state, the local lifecycle must move to explicit pending/manual-review/reconciliation-needed state rather than assuming success or failure silently. | Failure tests for order timeout, confirmation lookup failure, partial confirmation, close timeout, and ambiguous broker responses. | P0 | Medium |
| BROKER-013 | Broker-mutating requests should use stable `client_request_id` values where supported so retries and reconciliation can correlate local attempts with broker-side outcomes. Reuse, regeneration, and missing client request ids must be intentional and auditable. | Tests or code review proving client request ids are generated, persisted, passed to broker calls, and surfaced in execution/reconciliation evidence. | P1 | Medium |
| BROKER-014 | Simulated fills/closes when `trading_enabled` is false must remain clearly marked as simulated/local and must not be presented as broker-confirmed truth. Simulated behavior should exercise the same lifecycle/audit paths as live broker behavior wherever practical. | Tests proving simulated order/close results carry distinguishable provenance and still create/update expected lifecycle/audit records. | P1 | Medium |
| BROKER-015 | Broker reads used for entry admission, risk sizing, market status, or operator-critical UI must expose enough provenance, timestamp/freshness, and failure information for downstream services and UI to distinguish fresh broker truth from stale, fallback, simulated, unavailable, or estimated data. | DTO/read-model tests and frontend rendering tests for stale/fallback/unavailable broker data. | P1 | Medium |
| BROKER-016 | IG environment selection MUST be derived from canonical HTTPS `IG_API_BASE_URL` values only. Unknown hosts, altered paths, malformed URLs, or non-HTTPS URLs must fail closed before any credentialed request is attempted. Live dealing requires explicit acknowledgement beyond merely selecting the live gateway. | Config and adapter tests covering canonical demo/live acceptance, malformed/HTTP/lookalike host rejection, no-credential-use-before-validation, and live-dealing acknowledgement. | P0 | High |
| BROKER-017 | Every real broker order or close MUST require current fenced runtime leadership at the adapter mutation boundary. A missing, expired, released, superseded, or wrong-generation lease must fail before the credentialed broker request. Test-only adapters and explicitly simulated non-dealing paths may bypass the real-mutation fence only when their classification is unambiguous. | Adapter tests for missing/stale leadership, takeover overlap tests, and proof that simulated/test-only paths remain distinguishable. | P0 | High |

## Broker-neutral interface expectations

Application services may call:

- `place_order(OrderRequest) -> BrokerOrderResult`
- `close_position(instrument, broker_reference, client_request_id) -> BrokerOrderResult`
- `get_positions() -> list[BrokerPosition]`
- `get_latest_price(instrument) -> float` only when the caller can obtain freshness/provenance through another broker-neutral path. Operator-critical entry/risk paths should prefer DTOs or read models that carry freshness, source, and degraded-state information.
- `get_account_summary() -> BrokerAccountSummary`
- `get_market_details(instrument) -> BrokerMarketDetails`
- `quote_risk_sized_order(...) -> BrokerRiskSizingQuote`
- `normalize_order_size(instrument, requested_size) -> BrokerSizeNormalization`

Application services must not:

- Build IG REST payloads.
- Inspect IG session headers or token names.
- Depend on raw IG market payload paths.
- Reimplement IG point/pip/contract value conversion outside broker-owned quote/normalization DTOs.
- Depend on Lightstreamer item names, field names, subscription mechanics, or IG session token names outside the IG adapter/streaming boundary.
- Instantiate `IGBroker` directly outside approved composition/factory code.
- Treat fallback polling success as streaming health.
- Treat simulated fills/closes as broker-confirmed truth.
- Retry ambiguous broker mutations without preserving client request id/audit correlation.
- Convert broker unknown/pending/partial outcomes into exact local truth.

Broker-neutral DTO rules:

- DTOs must preserve broker-independent semantics for account, market details, risk sizing, size normalization, order result, and position reads.
- DTOs used for decisions must expose enough freshness/provenance/confidence to support fail-closed entry behavior.
- DTOs must not require callers to know IG units, pips, points, contract-value rules, raw payload paths, or session/auth header names.
- If a broker-specific field is unavoidable, it must stay in adapter-owned metadata and must not become a decision dependency outside the broker boundary without a new contract entry.

## Read-only broker calls

Read-only broker calls include account summary, market details, latest price, position reads, sizing quotes, and size normalization. Read-only broker calls do not intentionally mutate broker state, but they are still safety-critical when used for entry admission, allocation, sizing, reconciliation, or operator display.

Read failures, stale data, missing market metadata, unavailable account state, and unsupported sizing must fail closed for new entries unless a degraded mode is explicitly specified and tested.

Read-only broker calls must not be treated as passive application reads when they can trigger reconciliation, alerts, health transitions, or other durable local state changes.

Broker read data used by allocation, risk, market-status, runtime, or UI surfaces must retain provenance:

- source broker/adapter,
- fetched or observed time when known,
- freshness/staleness classification when used for trading decisions,
- confidence/precision when used for sizing or risk truth,
- degraded/fallback reason when live broker or stream truth is unavailable.

## Mutating broker calls

Mutating broker calls include order submission and position close. They must be linked to lifecycle authority and audit evidence:

- approved `TradeIntent` for new entries;
- known open `Position`, recovery/reconciliation authority, or explicit operator action for exits/closes;
- `Execution` for submission/fill/failure/manual-review audit where the attempt is part of strategy execution;
- stable `client_request_id` where supported;
- broker reference/deal id where returned;
- domain/reconciliation events for out-of-band, failure, timeout, ambiguous, partial-fill, or manual-review paths.

A broker mutation must never be a fire-and-forget utility call. Broker mutations must not be issued from passive read routes, passive AIMEE snapshot paths, dashboard projections, or frontend-only inference. They must originate from an explicit mutation, broker-action, strategy execution, recovery, reconciliation, or operator workflow with lifecycle authority.

## Fill and confirmation expectations

Broker order results may be accepted, rejected, filled, partially filled, pending, timed out, or ambiguous.

The broker contract should preserve:

- submitted size;
- broker-confirmed filled size where available;
- average fill price where available;
- partial-fill state where applicable;
- broker rejection/failure reason;
- confirmation lookup status;
- whether risk truth is exact, broker-confirmed estimated, partial-fill provisional, submitted estimate, allocation-only, simulated, or unknown.

Application services must not convert unknown, pending, or partial broker outcomes into exact filled truth without explicit confirmation.

## Idempotency and confirmation ambiguity

Broker mutations must be designed around duplicate-prevention and ambiguous-confirmation failure modes.

Expected behavior:

- Use `client_request_id`, deal reference, broker reference, or an equivalent correlation key where supported.
- Persist the local execution/recovery context before or at the point of broker submission so ambiguous responses can be investigated.
- Treat timeout, lost confirmation, partial fill, broker rejection, and unknown confirmation as distinct operator-visible states where possible.
- Do not assume a broker mutation failed only because local confirmation failed.
- Do not assume a broker mutation succeeded only because submission returned an acknowledgement.
- Ambiguous states should move to `NEEDS_MANUAL_REVIEW`, equivalent degraded execution state, or explicit recovery/reconciliation path.
- Retrying after ambiguity requires duplicate-exposure checks against broker state and local lifecycle state.

## IG adapter responsibilities

The IG adapter owns:

- Base-URL validation and environment classification before auth or request use.
- Session/auth flow and token storage.
- REST request timeout and response parsing.
- Market details parsing into `BrokerMarketDetails`.
- Account summary parsing.
- Risk-sized order quote and order size normalization.
- Order submission to IG and confirmation lookup.
- Position close and confirmation.
- Local simulated fill/close behavior when `trading_enabled` is false.
- Translate IG-specific dealing rules, market payloads, error payloads, order statuses, deal references, and confirmation responses into broker-neutral DTOs.
- Preserve enough raw-response-derived context for diagnostics without leaking raw IG dependency into app services.
- Normalize IG rejection, timeout, rate-limit, partial-fill, and confirmation ambiguity into broker-neutral result/error states.
- Mark simulated/local fills and closes distinctly from live broker-confirmed outcomes.

IG isolation rules:

- The accepted IG REST base URLs are exactly `https://demo-api.ig.com/gateway/deal` and `https://api.ig.com/gateway/deal`.
- Unknown hosts, altered paths, non-HTTPS URLs, and lookalike hosts must be rejected before API keys, credentials, or session tokens are used.
- Live dealing requires an additional explicit acknowledgement beyond selecting the live gateway.
- IG REST payload shape, API versioning, session headers, token names, account switching, and Lightstreamer credentials belong inside IG adapter/streaming code.
- IG pip, point, minimum size, step size, stop-distance, contract risk, and market-order preference semantics must be normalized into broker-neutral sizing/market DTOs before app services consume them.
- App services may inspect normalized DTO fields and generic `metadata`, but must not branch on raw IG payload paths or raw Lightstreamer fields.
- If a new broker-specific behavior becomes decision-critical, the broker contract must add a broker-neutral field or explicit adapter-owned normalization rule.

## Streaming and fallback responsibilities

Streaming health and fallback polling are separate truths.

`IGStreamingService` owns Lightstreamer connection, subscription, tick receipt, tick age, and stream health. `MarketDataService` may use fallback polling for observation, recovery, Tier 2 refresh, or degraded operation, but fallback polling must not mark streaming as connected or healthy.

Fallback-derived prices must remain visibly lower-confidence than healthy live stream data unless an explicit strategy-specific degraded mode says otherwise and is tested.

Entry eligibility must account for freshness, source, broker status, dealing restrictions, and risk rules. A price existing is not enough to imply entry eligibility.

Streaming/fallback truth rules:

- Streaming health is about Lightstreamer enablement, connection, subscription, and tick freshness.
- Fallback polling is broker-read data, not streaming health.
- Fallback polling may support observation, recovery, charting, or limited exit decisions when configured, but it must not automatically imply entry eligibility.
- UI and read models must label fallback, stale, unavailable, and live stream states distinctly.
- Fallback polling must not overwrite or mask the reason streaming is unavailable/stale.

## Simulated trading expectations

Simulated broker behavior is useful for development and dry-run flows, but it is not broker-confirmed truth.

Expected behavior:

- Simulated order/close results must remain distinguishable from live broker confirmations in execution details, risk truth confidence, account type, or operator-facing provenance.
- Simulated fills must still pass through the same local lifecycle/audit model as real broker fills.
- Simulated behavior must not teach app services to depend on shortcuts that live broker paths cannot provide, such as immediate fill certainty or missing confirmation ambiguity.
- Tests using simulated broker behavior must separately cover live-like failure modes through fakes or adapter tests.

## Retry, backoff, and circuit-breaker expectations

A centralized broker retry/backoff/circuit-breaker policy is not yet clearly identifiable. Until one exists:

- broker metadata failures must block new entries;
- entry admission and submission MUST fail closed on broker metadata, market status, sizing, account, or order errors unless an explicit degraded-entry mode is specified and tested;
- order submission failures must create explicit execution failure/manual-review evidence;
- ambiguous order outcomes must trigger reconciliation/manual-review rather than duplicate blind retries;
- close paths MUST keep open risk visible and mark execution/manual-review/reconciliation-needed state when close confirmation is unsafe or ambiguous;
- close failures must keep open risk visible and exit-capable where possible;
- repeated broker failures must surface in health, domain events, alerts, or operator-visible degraded state;
- retry behavior must preserve client request id correlation where supported.

## Broker construction and dependency boundary

`backend/app/core/broker_factory.py` provides the active broker. Services should obtain brokers through approved dependency boundaries rather than constructing concrete adapters directly.

Direct `get_broker()` usage outside composition/root wiring should be audited. It may be acceptable where currently established, but route/service code must not instantiate `IGBroker` directly unless explicitly classified as adapter/composition code.

## Must-not-cross broker boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| BROKER-BND-001 | Broker DTO boundary | Application services must consume broker-neutral DTOs, not raw IG payloads. | Code search and broker DTO tests. | P1 |
| BROKER-BND-002 | Broker mutation authority | Broker-mutating calls require lifecycle authority and durable audit evidence. | Entry/exit/recovery mutation path tests. | P0 |
| BROKER-BND-003 | IG adapter isolation | IG auth, headers, REST payloads, response paths, dealing-rule semantics, and Lightstreamer details stay inside IG adapter/streaming code. | Adapter boundary review. | P1 |
| BROKER-BND-004 | Streaming vs fallback truth | Fallback polling must not mark streaming healthy or imply entry eligibility by itself. | Market-data and UI provenance tests. | P1 |
| BROKER-BND-005 | Confirmation ambiguity | Unknown, timeout, partial, or ambiguous broker outcomes must not be silently treated as exact success/failure. | Broker failure and reconciliation tests. | P0 |
| BROKER-BND-006 | Simulated vs live truth | Simulated local fills/closes must not be presented as broker-confirmed truth. | Simulated trading tests. | P1 |

## Known unknowns

- Whether broker-neutral DTOs fully preserve partial-fill, pending, rejected, timeout, rate-limit, and ambiguous confirmation states.
- Whether live IG confirmation edge cases, partial fills, rejected confirmations, and rate-limit behavior are fully represented by fakes.
- Whether `get_latest_price(...) -> float` is too weak for any operator-critical entry/risk path without accompanying freshness/provenance.
- Whether all broker mutations use stable client request ids and persist them for reconciliation.
- Whether simulated fills/closes are clearly distinguished from broker-confirmed live truth in all backend read models and frontend surfaces.
- Whether direct `get_broker()` use is acceptable everywhere it appears or should be replaced with dependency injection/composition boundaries.
- Whether broker retry behavior could duplicate orders or closes when broker confirmation is ambiguous.
- Whether a centralized broker retry/backoff/circuit-breaker policy exists or needs to be introduced.
- Whether broker read DTO provenance is uniformly available for allocation, execution, reconciliation, runtime, and operator UI decisions.

## Required tests

- Contract tests proving broker DTOs can represent accepted, rejected, filled, partial-fill, pending, timeout, rate-limit, and ambiguous confirmation states.
- Tests proving no broker mutation can be reached without lifecycle authority.
- Tests proving ambiguous order/close outcomes create manual-review or reconciliation-needed state instead of silent success/failure.
- Tests proving client request ids are generated, persisted, passed to broker calls, and visible in execution/reconciliation evidence where supported.
- Tests proving simulated fills/closes are marked as simulated/local and not broker-confirmed.
- Tests proving operator-critical read models include freshness/provenance for broker-derived price, market, sizing, position, and risk data.
- Tests proving fallback polling never marks streaming healthy and never implies entry eligibility by itself.
- Tests or review checklist proving non-adapter services do not consume raw IG payloads, headers, token names, or IG-specific dealing-rule semantics.
- Failure tests for broker read failures, stale market details, unsupported sizing, order rejection, partial fill, close failure, timeout, and confirmation lookup failure.
- Retry tests proving ambiguous mutations cannot duplicate exposure without client request id correlation and broker/local state checks.

## Audit questions for Codex

- Does any non-adapter/non-streaming code import, inspect, or branch on IG-specific payload fields, headers, token names, constants, deal-status strings, or Lightstreamer details?
- Can every `place_order` and `close_position` call be traced back to lifecycle authority and durable audit state?
- Can any broker mutation be retried after an ambiguous outcome without preserving client request id and reconciliation evidence?
- Can `get_latest_price(...) -> float` be used in an entry/risk/operator-critical path without freshness/provenance from another source?
- Are partial fills, rejected confirmations, rate limits, timeouts, and unknown broker states represented distinctly in broker-neutral DTOs?
- Are simulated fills/closes clearly marked all the way through backend read models and frontend operator surfaces?
- Does fallback polling ever mark stream health as connected, subscribed, fresh, or healthy?
- Are close failures visible to the operator, recoverable, and prevented from losing open-risk ownership?
