# Backtesting contract

This specification defines the first production-quality historical simulation phase. It covers manually triggered, exactly-one-strategy runs across one or more shortlisted instruments. It does not define multi-strategy portfolio simulation.

## Architecture

```text
External provider or CSV
  -> explicit ingestion action
  -> immutable local dataset snapshot
  -> UTC-normalized instrument partitions
  -> chronological candle replay
  -> production Strategy implementation
  -> simulation-specific risk and execution
  -> isolated backtest persistence
  -> typed passive result APIs and operator UI
```

The physical MVP partition format is deterministic gzip JSONL. `HistoricalDataRepository` isolates replay from storage details so a later Parquet implementation does not change strategy or replay behavior.

## Requirements

| Spec ID | Requirement | Severity | Required evidence |
| --- | --- | --- | --- |
| BT-DATA-001 | A completed historical dataset snapshot MUST be immutable, UTC-normalized, checksummed, locally stored, and identified by dataset ID. Refresh or extension creates a new snapshot. | P1 | Dataset models, storage repository, checksum/immutability tests. |
| BT-PROVIDER-001 | External providers MUST be ingestion-only. Replay MUST perform no IG, OANDA, Binance, or other network calls. Optional credentials MUST remain provider-specific, and the application MUST remain usable with CSV and public Binance ingestion when optional credentials are absent. | P0 | Provider contracts, capability responses, isolation tests. |
| BT-REPLAY-001 | Replay MUST NOT create or mutate live `TradeIntent`, `Execution`, `Position`, `Trade`, runtime, reconciliation, allocation-alert, telemetry, deployment, or broker state. | P0 | Persistence isolation tests and separate backtest tables. |
| BT-REPLAY-002 | Replay MUST process events in timestamp order with stable instrument ordering, inject event time, evaluate at candle close, execute new decisions at the next candle open, and prevent future candle access. Identical inputs MUST produce identical results. | P0 | Determinism, same-timestamp ordering, next-open, simulated-clock, and no-look-ahead tests. |
| BT-EXEC-001 | Simulation MUST persist its pricing mode and spread, slippage, fee, sizing, and end-of-run assumptions. Historical bid/ask executes buys at ask and sells at bid. Mid/trade-only data requires explicit synthetic spread. Same-candle stop/target ambiguity uses the less favorable valid result. | P1 | Execution tests, warnings, run configuration persistence. |
| BT-API-001 | Dataset and backtest routes MUST use explicit typed contracts. Run creation is a bounded simulation mutation, not a broker mutation. Result reads MUST remain passive. | P1 | Route inventory and API contract tests. |
| BT-UI-001 | The operator UI MUST show dataset provenance/checksum, pricing mode, assumptions, warnings, failures, venue specificity, and candle-resolution limitations without implying broker-grade or tick-level precision. | P1 | Frontend contract/render tests and browser verification. |
| BT-TEST-001 | Critical replay behavior MUST have focused behavioral tests, including determinism, no-look-ahead, provider isolation, live-table isolation, execution costs, conservative ambiguity, metrics, ingestion validation, and typed API results. | P1 | Named backend and frontend test suites. |

## Strategy reuse

`evaluate_strategy_update` is the shared production decision sequence. The live `TradingEngine` and `BacktestReplayEngine` both call it. Strategy classes remain registered in the existing `StrategyRegistry`; the backtest creates one instance per shortlisted instrument using the selected profile and parameter snapshot.

## Reused, adapted, and excluded checks

Reused unchanged:

- Production strategy classes, signal direction, warm-up behavior, and entry hints.
- Registry compatibility metadata and profile resolution.
- One-position-per-instrument behavior inherent in the simulation ledger.

Adapted:

- Position sizing uses fixed units or deterministic percent-risk sizing from simulated equity and a strategy/fallback stop.
- Market availability is represented by immutable dataset coverage rather than a current broker status.
- Freshness is represented by coverage, gaps, and snapshot provenance rather than wall-clock tick age.
- Single-strategy concurrency is enforced without portfolio capital arbitration.

Intentionally excluded:

- Broker platform availability and order confirmation.
- Streaming health and live-feed staleness.
- Broker reconciliation, recovery, runtime leadership, and deployment state.
- Live operational telemetry and allocation alerts.
- Cross-strategy allocation, conflict resolution, and portfolio risk.

## Price and event semantics

- Strategy evaluation occurs after the current candle closes.
- Entry and strategy-exit decisions become executable at the next candle open.
- Stops and targets are checked against the execution-side candle component: bid for long exits and ask for short exits where available.
- Midpoint or trade-price candles require `FIXED_BPS`, `FIXED_PRICE`, or explicit zero spread. `DATASET` spread is rejected without bid and ask.
- If both stop and target are reachable in one candle, stop loss wins and a warning is persisted.
- One-minute OHLC does not establish tick ordering. Optional OANDA five-second data reduces but does not eliminate quote-order ambiguity.

## Provider posture

| Provider | MVP role | Authentication | Price components | Limits and warnings |
| --- | --- | --- | --- | --- |
| OANDA v20 | Primary Forex API ingestion | Optional free practice-account token | Mid, bid, ask, volume | Maximum 5,000 candles/request; deterministic time windows; `S5`, `M1`, `M5`, `M15`, `H1`. |
| Binance Spot | Primary crypto ingestion | None for public klines | Trade OHLC and volume | Maximum 1,000 klines/request; spot venue is explicitly `BINANCE_SPOT`; not interchangeable with IG CFDs. |
| IG | Broker-aligned Forex validation | Existing IG credentials | Current adapter supplies midpoint candles | Limited historical depth and weekly allowance; not the primary large-backfill source. |
| CSV | Manual and external-file ingestion | None | Bid/ask, midpoint, or trade OHLC | Rejects mixed instruments/timeframes, duplicates, invalid OHLC, malformed values, and timezone ambiguity. |

Official references reviewed for this phase:

- [OANDA instrument candles](https://developer.oanda.com/rest-live-v20/instrument-ep/)
- [OANDA v20 introduction and demo access](https://developer.oanda.com/rest-live-v20/introduction/)
- [Binance spot market-data endpoints](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
- [Binance public data archives](https://github.com/binance/binance-public-data)
- [IG REST API guide](https://labs.ig.com/rest-trading-api-guide.html)

## Known limitations and extensions

- Synchronous runs are bounded by `BACKTEST_MAX_CANDLES_PER_RUN`.
- JSONL gzip is used instead of Parquet in this phase to avoid adding a large columnar runtime dependency.
- IG ingestion currently uses the existing recent-history adapter and is intentionally limited.
- The MVP does not model partial fills, order books, latency distributions, tick paths, margin, financing, or corporate actions.
- Future work may add Parquet partitions, quote/tick replay, walk-forward tests, parameter sweeps, benchmark comparisons, and whole-system multi-strategy simulation without changing dataset identity or strategy reuse rules.
