# Backtesting contract

This specification defines the first historical simulation phase. It covers manually triggered, exactly-one-strategy runs across one or more shortlisted instruments. It does not claim production readiness and does not define multi-strategy portfolio simulation.

## Architecture

```text
External provider or CSV
  -> explicit ingestion action
  -> append-only dataset metadata and checksum-verified local files
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
| BT-WARMUP-001 | Runs MUST distinguish warm-up from the tradable performance window. Warm-up candles may update strategy state but MUST NOT create positions, pending executable decisions, exposure, or performance equity. Warm-up configuration, sufficiency, warnings, per-instrument consumption, and first tradable timestamps MUST be persisted and checksummed. | P1 | Replay boundary, dataset coverage, checksum, API, UI, and degraded-warning tests. |
| BT-EXEC-001 | Simulation MUST persist its pricing mode and spread, slippage, fee, sizing, and end-of-run assumptions. Historical bid/ask executes buys at ask and sells at bid. Mid/trade-only data requires explicit synthetic spread. Same-candle stop/target ambiguity uses the less favorable valid result. | P1 | Execution tests, warnings, run configuration persistence. |
| BT-RESULT-001 | Completed result accounting MUST separate realised, unrealised, fee, fill-cost, cash, equity, open-position, and closed-trade values; ordering and the canonical result checksum MUST be deterministic. | P1 | Accounting identity, ordering, public checksum mutation, independent-database, API, and browser-label tests. |
| BT-API-001 | Dataset and backtest routes MUST use explicit typed contracts. Run creation is a bounded simulation mutation, not a broker mutation. Result reads MUST remain passive. | P1 | Route inventory and API contract tests. |
| BT-UI-001 | The operator UI MUST show dataset provenance/checksum, pricing mode, assumptions, warnings, failures, venue specificity, and candle-resolution limitations without implying broker-grade or tick-level precision. | P1 | Frontend contract/render tests and browser verification. |
| BT-TEST-001 | Critical replay behavior MUST have focused behavioral tests, including determinism, no-look-ahead, provider isolation, live-table isolation, execution costs, conservative ambiguity, metrics, ingestion validation, and typed API results. | P1 | Named backend and frontend test suites. |

## Strategy reuse

`evaluate_strategy_update` is the shared production decision sequence. The live `TradingEngine` and `BacktestReplayEngine` both call it. Strategy classes remain registered in the existing `StrategyRegistry`; the backtest creates one instance per shortlisted instrument using the selected profile and parameter snapshot.

## Reused, adapted, and excluded checks

Reused unchanged:

- Production strategy classes, signal direction, internal readiness logic, and entry hints.
- Registry compatibility metadata and profile resolution.
- One-position-per-instrument behavior inherent in the simulation ledger.

Adapted:

- Explicit replay pre-roll feeds the production strategy evaluator while
  suppressing all executable decisions until the trading boundary.
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

- `requested_start_at` is the operator-requested trading boundary.
  `warmup_start_at` is the effective first pre-roll candle,
  `trading_start_at` is the first eligible trading-window candle, and
  `requested_end_at` remains the exclusive requested end.
- `warmup_mode=NONE` consumes no pre-roll. `warmup_mode=CANDLE_COUNT` consumes
  the configured number of target-timeframe candles immediately before
  `trading_start_at` for each instrument.
- Warm-up candles call the shared strategy evaluator so rolling state and
  indicators can mature, but all warm-up decisions are discarded. No pending
  entry or exit crosses into the trading window.
- Strict warm-up is the default. Insufficient pre-roll fails validation.
  The failed run persists diagnostics for every requested instrument, including
  consumed count, first tradable timestamp when known, and typed error details.
  Failed strict runs do not persist trades, equity, or completed-run metrics.
  `allow_insufficient_warmup=true` permits a completed but degraded run with
  `INSUFFICIENT_WARMUP` warnings and exact per-instrument consumed counts.
- Warm-up diagnostics use the stable fields `code`, `severity`,
  `instrument_id`, `requested_warmup_candles`, `available_warmup_candles`,
  `message`, optional `first_available_at`, and optional `trading_start_at`.
- Strategy evaluation occurs after the current candle closes.
- Entry and strategy-exit decisions become executable at the next candle open.
- Every same-timestamp replay cycle executes queued exits, then queued entries,
  then stop/target handling, then close evaluation; instruments are ordered by
  internal identifier within each phase.
- Stops and targets are checked against the execution-side candle component: bid for long exits and ask for short exits where available.
- Gap-through stops fill at the less favorable candle open. End-of-run
  `CLOSE_AT_END` positions fill at the final candle close.
- Midpoint or trade-price candles require `FIXED_BPS`, `FIXED_PRICE`, or explicit zero spread. `DATASET` spread is rejected without bid and ask.
- If both stop and target are reachable in one candle, stop loss wins and a warning is persisted.
- Entry fees reduce cash immediately. Mark-to-market results therefore include
  paid entry fees even when the position remains open.
- One-minute OHLC does not establish tick ordering. Optional OANDA five-second data reduces but does not eliminate quote-order ambiguity.

## Result accounting and reproducibility

The simulation uses a P&L cash ledger rather than deducting full position
notional. Spread and slippage are embedded in executable entry/exit fill
prices. Their reported cost fields are attribution values and are not
subtracted a second time. Fees are separate cash charges.

```text
realised_pnl = sum(closed fill-to-fill gross P&L)
unrealised_pnl = sum(open entry-fill-to-final-executable-mark P&L)
fees_paid = closed entry/exit fees + open entry fees
net_closed_trade_pnl = realised_pnl - closed-trade fees
total_pnl = realised_pnl + unrealised_pnl - fees_paid
ending_cash = starting_capital + realised_pnl - fees_paid
ending_equity = ending_cash + unrealised_pnl
              = starting_capital + total_pnl
return_pct = total_pnl / starting_capital * 100
```

`open_position_value` is gross marked notional and is informational; it is not
deducted from cash. Headline return includes unrealised P&L only when
`MARK_TO_MARKET` leaves positions open. `CLOSE_AT_END` closes at the final
available candle close and reports zero open positions and unrealised P&L.
Closed-trade return and win rate exclude open positions.
Open marks use the directionally executable bid/ask or synthetic-spread side,
but do not reserve a hypothetical future exit fee or exit slippage; only costs
already incurred are included.

No real account currency is persisted in this phase. Monetary API values use
`account_currency=null` and `monetary_unit_label="account units"`. The UI must
not infer GBP or another currency. Price decimals are adaptive display
formatting only; they are not broker tick precision unless future instrument
metadata explicitly supplies that precision.

`profit_factor` is defined only when the run has at least one winning and one
losing closed trade. Otherwise it is `null`, with
`profit_factor_null_reason` equal to `NO_CLOSED_TRADES`,
`NO_LOSING_TRADES`, or `NO_WINNING_TRADES`.

Exposure is wall-clock exposure: the union of all position-open intervals
divided by the interval from `trading_start_at` to the final mark.
Overlapping instruments do not double-count time. Open-at-end positions run
through the final mark.

The performance equity curve begins only after the first trading-window candle
closes. Warm-up candles do not create equity points, returns begin from
`starting_capital` at `trading_start_at`, and maximum drawdown uses only that
performance curve.

Percent-risk sizing solves against the expected executable entry fill,
configured entry and stop-exit slippage, and modeled entry/exit fees. A
strategy stop is used when supplied; otherwise the fallback stop percentage is
measured from the executable entry fill. The simulator permits continuous
position sizes and does not model broker lot steps, minimum sizes, margin, or
financing. The persisted numerical acceptance tolerance is
`percent_risk_sizing_absolute_tolerance=1e-9` account units. Non-gap stop
regressions compare actual simulated net loss with the configured risk budget
using that tolerance; sizing itself remains conservative at the budget
boundary.

New completed runs persist `BACKTEST_RESULT_MANIFEST_V2`. Its canonical projection
covers strategy and dataset identity, configuration and assumptions, final
status, accounting summary and open-position marks, deterministic trades,
equity, metrics, warnings, warm-up configuration and sufficiency, and
per-instrument warm-up/trading results. Trades order by
`(open_time, instrument, deterministic_sequence)`; equity orders by timestamp;
warnings use deterministic sequence; instruments and metrics use lexical keys.

The checksum excludes run and row primary keys, run name/notes, wall-clock
creation/start/completion timestamps, warning creation timestamps, and
`dataset_partition_id`. Those are database or display projections, not
simulation output. `result_manifest_version` and `result_checksum` are the
verification envelope. The public verifier reconstructs the persisted
projection and rejects authoritative-field mutation. Equal inputs copied into
independent databases produce the same checksum even when run IDs and
wall-clock timestamps differ.

The verifier remains version-dispatched. Historical
`BACKTEST_RESULT_MANIFEST_V1` results are reconstructed with the original V1
projection, which excludes warm-up fields. V2 results use the warm-up-aware
projection. Unknown versions and corrupted checksums fail verification; schema
migration does not silently invalidate V1 audit artifacts.

Completed runs are required to have `failure_reason=null`; the API and public
verifier reject a completed row with a non-null failure reason even though
that status-constrained field is not part of the canonical completed-result
projection. Failed runs retain `failure_reason` for diagnosis but do not
receive a completed-result manifest or result checksum.

Derived candles require complete, UTC epoch-aligned source buckets. Partial
buckets are rejected rather than silently incorporating candles outside the
requested range. Dataset identity covers provider provenance, instrument
mappings, coverage metadata, partition checksums, detected gaps, and warnings;
all of it is re-verified before replay.

## Dataset publication and completeness

- Provider requests are aligned outward to UTC timeframe boundaries. The
  original requested start/end and the aligned actual coverage remain distinct
  manifest fields.
- Every requested instrument must reach both aligned boundaries, contain the
  requested timeframe and instrument identity, and carry matching
  provider/venue/instrument provenance. Empty, truncated, internally gapped, or
  still-open responses are not published as `READY`.
- Partitions are written under a staging path first. Partition rows and final
  dataset metadata are committed only after every instrument validates and all
  partition hashes and the canonical manifest checksum are available.
- Filesystem publication and database commit cannot be one physical
  transaction. A commit exception is reconciled through a fresh database
  session before any cleanup: a durable `READY` snapshot is accepted only when
  every partition file and the manifest checksum verify; a confirmed non-ready
  import is cleaned and recorded as `PARTIAL` or `FAILED`. If the database
  outcome cannot be read or verified, artifacts are retained and an explicit
  recovery error is raised rather than risking deletion of files referenced by
  durable metadata. This is compensating publication, not a claim of a
  distributed transaction.
- `READY` dataset and partition updates/deletes are blocked by application
  service policy and database triggers. Partition updates are rejected when
  either the old or new parent dataset is `READY`, preventing reparenting into
  or out of a completed snapshot. Direct file tampering is detected by
  partition and manifest verification rather than prevented by filesystem
  permissions.
- Manifest V3 defines dataset and partition identity in code. It covers dataset
  identity, provenance, requested and actual coverage, counts, UTC rule,
  components, completeness, gaps, warnings, import metadata, storage format,
  and immutable status. It also covers partition row ID, parent dataset ID,
  instrument mappings, timeframe, coverage, counts, components, partition
  checksum, storage path, gaps, warnings, and source metadata. The dataset
  `checksum` is intentionally outside its own hash as the verification
  envelope; the API's nested `partitions` property is projection-only because
  the canonical partition array is already a top-level manifest section.
- Dataset operational availability is separate from immutable Manifest V3
  identity. `availability`, `availability_reason`, and
  `availability_updated_at` are mutable operational fields intentionally
  excluded from the checksum. Selection and replay require `status=READY`,
  `availability=AVAILABLE`, existing partition files, and successful public
  checksum verification.
- If ambiguous publication leaves durable `READY` metadata whose files or
  checksum do not verify, reconciliation retains the remaining artifacts,
  marks the snapshot `RECOVERY_REQUIRED`, records the reason, and raises a
  recovery error. The snapshot remains visible for diagnosis but cannot be
  selected or replayed. Retry creates a new snapshot ID.
- SQLite restores UTC awareness in the ORM/API layer because SQLite does not
  preserve timezone offsets as a native datetime type. PostgreSQL uses
  `TIMESTAMP WITH TIME ZONE`; the migration interprets legacy backtesting
  timestamps as UTC. PostgreSQL trigger behavior remains dependent on the
  environment-gated migration rehearsal.
- The warm-up migration backfills historical instrument
  `first_tradable_at` from the parent run's `trading_start_at`, falling back to
  `requested_start_at`, before enforcing non-null storage.
- Backend timestamps require `Z` or an explicit offset. Browser
  `datetime-local` values are separately interpreted in the browser timezone
  and converted to explicit UTC instants before API submission; backend values
  are never repaired by appending `Z`.

The Binance still-open-candle filter and staged publication/reconciliation
changes were explicitly reviewed as dataset-integrity prerequisites for
immutable replay inputs. They are not evidence of accounting correctness and
do not change replay, strategy, broker, or live-trading behavior. Focused
provider tests cover still-open candle exclusion, truncation, multi-instrument
failure, publication failure, recovery, and retry.

## Provider posture

| Provider | MVP role | Authentication | Price components | Limits and warnings |
| --- | --- | --- | --- | --- |
| OANDA v20 | Primary Forex API ingestion | Optional free practice-account token | Mid, bid, ask, volume | Maximum 5,000 candles/request; deterministic time windows; `S5`, `M1`, `M5`, `M15`, `H1`. |
| Binance Spot | Primary crypto ingestion | None for public klines | Trade OHLC and volume | Maximum 1,000 klines/request; spot venue is explicitly `BINANCE_SPOT`; not interchangeable with IG CFDs. |
| IG | Broker-aligned Forex validation | Existing IG credentials | Current adapter supplies midpoint candles | Limited historical depth and weekly allowance; not the primary large-backfill source. |
| CSV | Manual and external-file ingestion | None | Bid/ask, midpoint, or trade OHLC | Rejects mixed instruments/timeframes, duplicates, invalid OHLC, malformed values, and timezone ambiguity. |

Official references reviewed for this phase:

- [OANDA v20 introduction and demo access](https://developer.oanda.com/rest-live-v20/introduction/)
- [Binance spot market-data endpoints](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
- [Binance public data archives](https://github.com/binance/binance-public-data)
- [IG REST API guide](https://labs.ig.com/rest-trading-api-guide.html)
- [QuantConnect warm-up periods](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/warm-up-periods)
- [Backtrader minimum-period lifecycle](https://www.backtrader.com/docu/operating/)

These official sources were rechecked on June 14, 2026. OANDA still documents
demo-account access, Binance documents public spot klines with a maximum of
1,000 records per request, and Binance's official public-data repository
documents daily/monthly downloadable archives. The IG source remains an
existing-credentials validation path, not a dependency for general app use.

## Known limitations and extensions

- Synchronous runs are bounded by `BACKTEST_MAX_CANDLES_PER_RUN`.
- JSONL gzip is used instead of Parquet in this phase to avoid adding a large columnar runtime dependency.
- IG ingestion currently uses the existing recent-history adapter and is intentionally limited.
- Completeness validation has no provider-specific exchange calendar. A range
  containing absent timeframe boundaries, including scheduled closures, is
  conservatively retained as partial rather than called complete.
- Candle-count warm-up uses available target-timeframe candles, not a
  provider-specific session calendar or duration model. Gaps can therefore
  make strict warm-up insufficient even when wall-clock coverage looks long
  enough.
- Binance ingestion currently uses deterministic paginated REST. Automatic
  daily/monthly archive ingestion is not yet implemented, so very large
  backfills remain a documented next slice.
- The MVP does not model partial fills, order books, latency distributions, tick paths, margin, financing, or corporate actions.
- Result checksums detect mutation and prove equality of the covered
  completed-result projection plus the completed-run failure invariant; they
  are not signatures and do not establish source-build provenance.
- Future work may add Parquet partitions, quote/tick replay, walk-forward tests, parameter sweeps, benchmark comparisons, and whole-system multi-strategy simulation without changing dataset identity or strategy reuse rules.
