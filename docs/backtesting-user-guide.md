# Backtesting User Guide

This guide covers the current historical-data and single-strategy backtesting
workflow. It is not a production-readiness claim and does not describe
broker-grade execution replay.

## Before You Start

Open `/backtests`. CSV and Binance public imports need no credentials. OANDA
uses the optional `OANDA_PRACTICE_TOKEN`. IG imports use the existing optional
IG credentials. Missing optional credentials disable only that provider.

All request and response timestamps are UTC instants. Browser
`datetime-local` values are interpreted in the browser timezone and converted
to explicit UTC before submission. CSV and backend timestamps must contain
`Z` or an explicit offset.

## Import Historical Data

Provider imports require a provider, one or more internal instrument IDs, a
supported timeframe, and a date range. The importer aligns the request to
timeframe boundaries, stages every partition, validates complete coverage,
publishes files, calculates Manifest V3, and then commits metadata.

CSV imports accept one instrument and one timeframe. Use explicit bid/ask,
midpoint, or trade OHLC columns. Generic `open`, `high`, `low`, and `close`
are treated as trade-price candles.

An import becomes usable only after every requested instrument covers the
aligned interval, all source metadata is present, every partition is written,
and checksum verification succeeds.

## Dataset States

Immutable content status and mutable operational availability are separate:

| Status | Availability | Meaning |
| --- | --- | --- |
| `READY` | `AVAILABLE` | Complete snapshot that currently passes file and checksum verification. |
| `READY` | `RECOVERY_REQUIRED` | Durable immutable metadata exists, but ambiguous-publication recovery found a missing, corrupt, or unverifiable partition. |
| `IMPORTING`, `PARTIAL`, or `FAILED` | `UNAVAILABLE` | Import is incomplete or failed and cannot be replayed. |

The UI can show non-usable attempts for diagnosis, but only a verified
`READY` plus `AVAILABLE` snapshot is selectable. Backtest creation repeats
public checksum verification before persisting a run.

## Ambiguous Publication Recovery

The filesystem and database cannot share one physical transaction. If a
database commit raises after it may have succeeded, the importer opens a fresh
session and re-reads the snapshot.

- A durable `READY` snapshot with existing files and a valid checksum is
  returned as successful.
- No durable state, or confirmed non-ready state, allows safe cleanup.
- A durable `READY` snapshot with missing or corrupt files is retained and
  marked `RECOVERY_REQUIRED`. Remaining files are not deleted.

Retry creates a new dataset ID and new partition paths. It never makes the old
recovery-required snapshot selectable and does not reuse its damaged files.
Recovery-required snapshots currently require operator investigation; there
is no automated repair or purge workflow.

## Verify Coverage and Provenance

Before running, inspect provider, venue, market type, asset class, timeframe,
actual coverage, candle count, price components, warnings, gaps, checksum, and
availability reason.

Manifest V3 covers immutable dataset and partition identity, provenance,
coverage, counts, source metadata, storage paths, warnings, and partition
hashes. Dataset `checksum` is its verification envelope. Nested API
`partitions` is a projection of the covered partition section. Operational
availability fields are intentionally outside the manifest so recovery state
can change without rewriting immutable provenance.

## Run a Backtest

Select one available dataset, one registered strategy, one or more dataset
instruments, timeframe, covered date range, starting capital, sizing mode,
spread, slippage, fees, and end-of-run treatment.

Midpoint or trade-only datasets require an explicit synthetic spread unless a
zero-spread assumption is intentionally selected. The simulation uses
candle-close decisions and next-candle-open fills. Results are simulation
records and never broker-confirmed executions.

## Understand Result Accounting

Spread and slippage are embedded in executable fill prices. Fees are deducted
separately, so reported spread/slippage costs are attribution and must not be
subtracted from P&L again.

```text
total_pnl = realised_pnl + unrealised_pnl - fees_paid
ending_equity = starting_capital + total_pnl
ending_equity = ending_cash + unrealised_pnl
```

`realised_pnl` is closed fill-to-fill gross P&L.
`net_closed_trade_pnl` subtracts fees belonging to closed trades.
`unrealised_pnl` marks open positions to the final executable candle side.
`open_position_value` is gross marked notional and is informational because the
simulator uses a P&L cash ledger.

With `MARK_TO_MARKET`, headline total return includes unrealised P&L and the
result shows the number of positions still open. With `CLOSE_AT_END`, remaining
positions close at the final candle close. Closed-trade win rate and
closed-trade return never treat open positions as completed trades.
Open marks use the executable bid/ask or synthetic-spread side but do not
reserve a future exit fee or hypothetical exit slippage.

Exposure is elapsed wall-clock time with at least one position open divided by
the replay interval. Overlapping and multi-instrument positions do not
double-count the same time.

Percent-risk sizing uses the expected executable entry fill, configured
spread/slippage assumptions, stop distance, and applicable entry/exit fees.
Sizes are continuous; broker lot steps, minimum sizes, margin, and financing
are not modeled.

## Verify a Result

Completed runs persist `BACKTEST_RESULT_MANIFEST_V1` and its SHA-256 checksum.
The manifest covers strategy and dataset identity, run assumptions,
deterministically ordered trades and equity, metrics, warnings, open-position
marks, and per-instrument results.

Run/row primary keys, run name and notes, wall-clock audit timestamps, and
dataset partition database IDs are projection-only and intentionally excluded.
They can differ between databases without changing the simulation result.
Changing any authoritative persisted result field causes public checksum
verification to fail. The checksum is tamper evidence for the covered
projection, not a digital signature or proof of broker-grade accuracy.

## Current Limits

- Publication uses compensating recovery, not a distributed transaction.
- Files are checksum-protected, not made physically immutable by permissions.
- SQLite trigger behavior is directly tested.
- PostgreSQL trigger execution remains unverified when
  `POSTGRES_REHEARSAL_ADMIN_URL` is unset.
- Provider imports are synchronous.
- Candle replay is not tick, queue-position, or broker execution replay.
- Percent-risk sizing does not enforce broker lot increments or margin rules.
- Result checksums do not identify the exact source build unless build
  provenance is separately supplied.
- This data-integrity foundation does not establish full backtesting
  production readiness.
