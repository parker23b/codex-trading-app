# Broker Integration Guide

This backend is designed so broker-specific code stays behind the shared execution contract in [broker.py](../backend/app/core/broker.py).

## Current Flow

- API routes call services.
- Services coordinate persistence and runtime state.
- Trading and application services consume the broker-neutral `Broker` interface or broker-neutral DTOs.
- Strategy classes stay pure and never touch broker SDKs, HTTP clients, or the database.

That separation is the reason a new broker can be added without rewriting the trading engine or API layer.

## Files Involved

- [broker.py](../backend/app/core/broker.py): shared broker contract
- [broker_factory.py](../backend/app/core/broker_factory.py): provider selection and construction
- [ig_broker.py](../backend/app/core/ig_broker.py): current IG implementation
- [trading_engine.py](../backend/app/core/trading_engine.py): one broker consumer
- service consumers include market status, reconciliation, recovery, account, allocation, and market-data paths

## Adding A New Broker

### 1. Create the adapter

Add a file under `backend/app/core/`, for example:

```text
backend/app/core/oanda_broker.py
backend/app/core/interactive_brokers_broker.py
backend/app/core/custom_exchange_broker.py
```

Implement the `Broker` abstract base class:

- `account_type`
- `place_order`
- `close_position`
- `get_positions`
- `get_latest_price`
- `get_account_summary`
- `get_market_details`
- `quote_risk_sized_order`
- `normalize_order_size`

Return the shared dataclasses already defined in `broker.py`:

- `BrokerOrderResult`
- `BrokerPosition`
- `BrokerAccountSummary`
- `BrokerMarketDetails`
- `BrokerRiskSizingQuote`
- `BrokerSizeNormalization`

Do not leak raw SDK responses or broker-specific payloads outside the adapter.

### 2. Add configuration

Add provider-specific settings to [config.py](../backend/app/core/config.py) and document them in `backend/.env.example`.

Typical settings:

- API base URL
- API key
- Username or client id
- Password, secret, or private key reference
- Account id
- Demo/live selector
- Request timeout

### 3. Update the broker factory

Extend [broker_factory.py](../backend/app/core/broker_factory.py) so the application can choose the correct adapter from configuration.

Good pattern:

- `BROKER_PROVIDER=IG`
- `BROKER_PROVIDER=OANDA`
- `BROKER_PROVIDER=IBKR`

The factory should be the only place that decides which concrete broker class gets instantiated.

### 4. Keep order translation inside the adapter

The trading engine emits normalized `OrderRequest` objects. Translate those into broker-specific HTTP or SDK calls inside the adapter only.

Examples of adapter responsibilities:

- Map `BUY` and `SELL` to broker-specific direction values
- Convert instrument ids or epics
- Apply broker-specific order payload structure
- Parse fill responses into `BrokerOrderResult`
- Parse open positions into `BrokerPosition`

Examples of responsibilities that should stay out of the adapter:

- FastAPI request parsing
- Dashboard calculations
- Strategy signal generation
- Database queries unrelated to syncing broker state

### 5. Handle auth and token refresh

Broker authentication belongs in the adapter or a helper module used only by that adapter.

For production-grade behavior:

- Refresh tokens before expiry
- Log auth failures with structured context
- Avoid logging secrets
- Retry only when the broker's API semantics make retries safe

### 6. Add reconciliation support

For a real broker, `get_positions()` should return broker-truth positions so the rest of the backend can reconcile local state against the external account when needed.

That becomes important for:

- process restarts
- partial fills
- manual trades placed outside this app
- session expiry or reconnects

Reconciliation runs through `BrokerReconciliationSupervisor`, a leader-owned fixed-cadence task independent of watchlist, streaming, and strategy-deployment coverage. An empty active watchlist therefore does not suppress broker-position discovery.

Real IG order and close mutations also require the active runtime-leadership generation. The adapter validates the lease immediately before mutation and holds the lease row until the broker operation finishes, preventing takeover from overlapping an in-flight stale-leader mutation.

### 7. Test at the adapter boundary

Add tests for:

- order request translation
- auth header construction
- token refresh behavior
- response parsing
- error mapping
- every required broker capability and DTO field
- pending, partial, rejected, timeout, rate-limit, unknown, and ambiguous outcomes
- stable client request-id correlation
- read freshness and provenance
- safe retry classification

Mock the broker API at the HTTP client layer. The rest of the backend should continue to test only against the shared `Broker` contract.

Every broker adapter should also pass one shared conformance suite. Adapter-specific unit tests alone are not enough to prove equivalent failure semantics.

## Retry And Circuit Policy

The current repository does not yet have one centralized broker policy for retry, backoff, and circuit state (`AUDIT-BROKER-006`).

Required design:

- Retry only operations that are explicitly safe and idempotent.
- Use bounded exponential backoff with jitter for retry-safe reads.
- Surface circuit state and the last successful broker/reconciliation timestamps to operators.
- Do not blindly retry an order or close after timeout, transport loss, or ambiguous confirmation.
- Resolve ambiguous mutations through stable client request IDs, broker confirmation lookup, reconciliation, and manual review.
- Keep entry and close policies separate: entry failures may block new risk, while close failures must preserve visible open-risk and an exit/recovery path.

## IG-Specific Notes

For IG demo integration, the official setup path is:

1. Create an IG account.
2. Create a demo account from the account switcher.
3. Generate a demo API key while switched to demo.
4. Authenticate with the session API and carry forward the returned auth material on subsequent requests.
5. Add streaming separately if you want live prices and account notifications.

Official references:

- Getting started: [https://labs.ig.com/gettingstarted](https://labs.ig.com/gettingstarted)
- REST guide: [https://labs.ig.com/rest-trading-api-guide.html](https://labs.ig.com/rest-trading-api-guide.html)
- Streaming guide: [https://labs.ig.com/streaming-api-guide.html](https://labs.ig.com/streaming-api-guide.html)
