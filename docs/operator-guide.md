# Operator Guide

This guide covers local development setup and operator-facing surfaces. It is not a production runbook. InvestMate is not ready for broker-connected demo dealing, unattended autonomy, or live trading.

## Prerequisites

- Python 3.11 or newer.
- Node.js and npm compatible with `frontend/package-lock.json`.
- Network access for dependency installation.
- Optional IG demo credentials for broker-read checks.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -c requirements.txt -e .
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Default backend behavior:

- uses SQLite at `backend/trading_platform.db`
- applies Alembic migrations automatically on startup
- upgrades existing unversioned SQLite dev databases through a legacy compatibility bridge before stamping the baseline revision
- uses the IG broker adapter with `IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal`
- keeps `IG_TRADING_ENABLED=false`
- enables IG streaming by default
- keeps `IG_LIVE_TRADING_ACKNOWLEDGED=false`
- keeps test-only backend routes disabled by default
- keeps AIMEE/AI reviewer LLM augmentation disabled by default

Backend URL: [http://localhost:8000](http://localhost:8000)

Useful startup checks without IG credentials:

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/system/health](http://localhost:8000/system/health)
- [http://localhost:8000/system/broker-environment](http://localhost:8000/system/broker-environment)
- [http://localhost:8000/control-plane/summary](http://localhost:8000/control-plane/summary)
- [http://localhost:8000/coverage/summary](http://localhost:8000/coverage/summary)
- [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- [http://localhost:8000/reviews/operator-summary](http://localhost:8000/reviews/operator-summary)

Expected degraded states with blank IG credentials:

- `/health` should return an app-level health response
- `/system/health` and `/dashboard` can report disconnected broker or stream state
- `/reviews/operator-summary` can include disabled LLM or degraded stream warnings
- `/broker/positions` and `/markets/overview?category=forex` return credential-required errors
- startup can log missing IG settings during recovery

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL: [http://localhost:3000](http://localhost:3000)

## Optional IG Demo Read Connectivity

Update `backend/.env` with demo credentials only when you want broker-read checks:

```env
BROKER_PROVIDER=IG
IG_API_KEY=your-demo-api-key
IG_USERNAME=your-demo-username
IG_PASSWORD=your-demo-password
IG_ACCOUNT_ID=your-demo-account-id
IG_API_BASE_URL=https://demo-api.ig.com/gateway/deal
IG_TRADING_ENABLED=false
IG_LIVE_TRADING_ACKNOWLEDGED=false
IG_VERIFY_SSL=true
IG_CA_BUNDLE_PATH=
TESTING_ROUTES_ENABLED=false
```

Read-only verification progression:

1. Keep `IG_TRADING_ENABLED=false`.
2. Start the backend.
3. Verify `GET /system/broker-environment` returns `DEMO`, `IG_DEMO_GATEWAY`, and the expected dealing state.
4. Verify auth via `GET /broker/positions`.
5. Verify stream or market health via `GET /health/stream` and `GET /system/health`.
6. Verify market inspection via `GET /markets/overview?category=forex`.
7. Verify `POST /testing/reset-history` returns `404`.

Allowed broker gateway values:

- demo: `https://demo-api.ig.com/gateway/deal`
- live: `https://api.ig.com/gateway/deal`

Any other host, path, or non-HTTPS URL is rejected during backend configuration. The frontend must not infer environment from URL strings.

Live-dealing guard:

- `IG_API_BASE_URL=https://api.ig.com/gateway/deal` with `IG_TRADING_ENABLED=false` is allowed for read-only posture.
- `IG_API_BASE_URL=https://api.ig.com/gateway/deal` with `IG_TRADING_ENABLED=true` requires `IG_LIVE_TRADING_ACKNOWLEDGED=true`.
- This acknowledgement only permits startup. It does not imply live-trading readiness.

Do not enable real broker dealing until the pending Postgres concurrency rehearsal and supervised-demo preflight have passed.

## Broker-Connected Demo Posture

Read-only broker connectivity is allowed with `IG_TRADING_ENABLED=false`. The three `2026-06-12` P0 implementation defects are fixed locally, but broker mutation remains operationally blocked until CI runs the committed Postgres allocation-lock and runtime-fence rehearsals and the supervised-demo preflight is repeated.

For read-only broker investigation:

1. Start with a fresh versioned database.
2. Keep `IG_TRADING_ENABLED=false`.
3. Confirm `/system/broker-environment` shows the expected environment and dealing is disabled.
4. Confirm test-only controls remain gated unless you are in an explicit dev/test workflow.

Manual decisions remain outside the repo:

- purge historical SQLite DB blobs before broader sharing or publication
- rotate any local/demo credentials if the repository or workstation state was shared
- do not claim stronger supply-chain attestation than the current hash, audit, and SBOM controls actually provide

## Main Surfaces

- `/` - overview dashboard for positions, executions, broker state, stream health, coverage, and control-plane summary.
- `/live` - live system view with trust rail, anomalies, runtime state, instrument inspection, and operational context.
- `/risk` - allocation exposure, drift, cycles, intents, and alert workflow.
- `/control-plane` - autonomous-control state, governance, deployment alignment, and family detail.
- `/coverage` - Tier 1 streaming, Tier 2 refresh, promotion activity, and operating limits.
- `/markets` - market-category investigation, catalogue data, shortlist, and strategy-watchlist workflows.
- `/events` - domain-event console and local test reset control.
- `/strategies` - strategy registry, runtime state, profile visibility, and manual runtime controls.
- `/reviewer` - persisted reviewer summaries and review history.
- AIMEE drawer - persistent assistant-style operational overview and Q&A surface.

## Identifier Visibility And Retention

Operator-facing APIs and UI surfaces no longer need raw broker/account/request/runtime/correlation identifiers for ordinary investigation.

- What stays raw internally:
  - broker/deal references used for reconciliation and later close authority
  - execution client request ids used for duplicate suppression and retry correlation
  - runtime ids and recovered broker position references used for recovery/lifecycle joins
  - persisted domain-event correlation/runtime ids used for internal traceability
- What operators see:
  - reviewed surfaces now return a masked `display` plus stable `fingerprint`
  - the masked display is for quick recognition without exposing the raw identifier
  - the fingerprint is for cross-surface correlation across dashboard, events, trades, strategies, control-plane, and allocation views
- What is forbidden:
  - `Authorization`, `CST`, `X-SECURITY-TOKEN`, session/header/token/password/api-key fields must not survive persistence or serialization
  - do not treat `NEXT_PUBLIC_*` values as secrets; they are browser-visible transport configuration
- Retention limits:
  - the repository still contains historical cleanup work outside this code change
  - raw internal authority identifiers are intentionally retained in the database where lifecycle correctness still depends on exact values

## Environment Variables

Backend env file: `backend/.env`.

Most important backend variables:

- `DATABASE_URL` - SQLModel connection string. Relative SQLite paths are normalized against `backend/`.
  Supported posture today: clean SQLite development remains the default, versioned Postgres creation/rehearsal is supported for migration proof, and existing unversioned non-SQLite databases are intentionally refused at startup until they are migrated manually.
- `BROKER_PROVIDER` - current allowed value is `IG`.
- `OPERATOR_API_CREDENTIALS` - server-side JSON registry of named operator credentials, scopes, and enabled/revoked state. Production-like environments require this instead of the shared legacy token.
- `OPERATOR_API_TOKEN` - local-development compatibility token only; production-like startup/auth rejects it as the sole operator credential.
- `IG_API_BASE_URL` - canonical broker gateway and the single source of truth for environment selection. Allowed values are `https://demo-api.ig.com/gateway/deal` and `https://api.ig.com/gateway/deal`.
- `IG_TRADING_ENABLED` - safety switch for broker dealing. Keep this `false`.
- `IG_LIVE_TRADING_ACKNOWLEDGED` - required before any live gateway plus live dealing configuration may start.
- `IG_STREAMING_ENABLED` - starts the streaming loop when enabled.
- `BROKER_READ_MAX_ATTEMPTS`, `BROKER_READ_BACKOFF_BASE_SECONDS`, `BROKER_READ_BACKOFF_MAX_SECONDS`, `BROKER_READ_CIRCUIT_FAILURE_THRESHOLD`, and `BROKER_READ_CIRCUIT_COOLDOWN_SECONDS` - operation-aware retry/circuit limits for broker reads. They never enable automatic order/close retries.
- `TESTING_ROUTES_ENABLED` - keep this `false` outside explicit dev/test harnesses.
- `MARKET_DATA_POLL_INTERVAL_SECONDS` - market-data loop cadence.
- `AI_REVIEWER_LLM_ENABLED` - keeps reviewer output deterministic when `false`.
- `STARTING_ACCOUNT_VALUE` - dashboard baseline value.

Frontend env file: `frontend/.env.local`.

Most important frontend variables:

- `NEXT_PUBLIC_API_BASE_URL` - backend URL for frontend requests.
- `NEXT_PUBLIC_ENABLE_DEV_FALLBACK` - present in the env example, but current shared client behavior does not actively branch on it.

## Verification Commands

Backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Backend migration and drift checks:

```bash
cd backend
source .venv/bin/activate
alembic current
alembic upgrade head
pytest tests/test_database_migrations.py tests/test_initialize_database.py -q
POSTGRES_REHEARSAL_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres \
  pytest tests/test_postgres_migration_rehearsal.py -m postgres_rehearsal -q
```

Frontend static checks:

```bash
cd frontend
npm run audit
```

Current evidence gaps are tracked in [audit-status.md](audit-status.md).
# Historical data and backtests

## Optional credentials

- Binance spot klines require no credentials.
- CSV import requires no credentials.
- OANDA imports require `OANDA_PRACTICE_TOKEN` from a free practice account. This token is separate from IG credentials.
- IG validation imports reuse `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, and optional `IG_ACCOUNT_ID`.

The application remains usable when OANDA or IG credentials are absent. Provider cards show the missing optional configuration.

Binance ingestion currently uses paginated public REST klines. Automatic use of
the official daily/monthly archive files is not implemented in this slice, so
prefer bounded imports until that large-backfill path is added.

## Import data

Open `/backtests`.

For CSV, choose a file with:

```csv
timestamp,instrument,timeframe,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,mid_open,mid_high,mid_low,mid_close,trade_open,trade_high,trade_low,trade_close,volume
```

Only one instrument and one timeframe may appear in a CSV. Timestamps must contain `Z` or an explicit offset. Generic `open,high,low,close` columns are accepted as trade-price OHLC.

For provider import, choose a configured provider, enter internal instrument
IDs, timeframe, and a browser-local date/time range. The UI converts that
range to explicit UTC instants before submission. Imports are synchronous in
this phase. Only imports with complete aligned coverage for every requested
instrument become selectable `READY` snapshots. Partial and failed attempts
remain visible with warnings and a failure reason.

Dataset status and operational availability are separate. A snapshot is
selectable only when its immutable status is `READY`, its operational
availability is `AVAILABLE`, every partition file exists, and public checksum
verification succeeds. A durable snapshot that fails ambiguous-commit
reconciliation remains `READY` for provenance but is marked
`RECOVERY_REQUIRED`, shown for diagnosis, and excluded from selection and
replay.

## Inspect coverage

The dataset panel shows:

- provider, venue, market type, and asset class;
- earliest/latest timestamps and candle count;
- bid, ask, midpoint, or trade components;
- gaps and warnings;
- append-only status, canonical checksum, and storage format.

`READY` metadata and partition rows are protected from application and direct
database update/delete paths, including attempts to move a partition into or
out of a `READY` dataset. Local partition files are checksum-verified; the
application detects file edits or deletion rather than claiming filesystem
permissions make the bytes physically immutable. SQLite trigger behavior is
covered directly. PostgreSQL uses equivalent triggers, but verification
depends on the separately configured migration rehearsal.

Filesystem publication and the database commit are not one transaction. If
commit acknowledgement is ambiguous, the importer re-reads the snapshot using
a fresh database session. Verified durable `READY` snapshots retain their
files and are treated as successful; confirmed non-ready attempts are cleaned
and recorded. If reconciliation itself is unavailable or contradictory,
artifacts are retained and the operator receives a recovery error.
If durable `READY` metadata exists but a referenced file is missing, corrupt,
or fails checksum verification, the importer does not delete more artifacts.
It records the mutable operational state `RECOVERY_REQUIRED` and a reason.
A retry creates a separate snapshot; it does not repair or reuse the damaged
snapshot.

The canonical manifest covers all authoritative dataset and partition
provenance, coverage, identity, storage, warning, and checksum fields.
Partition `id` and `dataset_id` are covered. The dataset checksum is excluded
from its own hash because it is the verification envelope; the nested API
`partitions` property is projection-only because the same rows are already
represented in the manifest partition section.
Operational `availability`, `availability_reason`, and
`availability_updated_at` fields are intentionally excluded from Manifest V3
because they may change without changing immutable snapshot identity.

## Run a backtest

Choose exactly one registered strategy, one immutable dataset, one or more dataset instruments, timeframe, range, starting capital, sizing, spread, slippage, fees, and end-of-run treatment. Runs are bounded by `BACKTEST_MAX_CANDLES_PER_RUN`.

Date/time form values are browser-local wall times. The UI converts them to
explicit UTC instants before submission. Timestamps returned by the backend
must already contain `Z` or an explicit offset and are rejected if ambiguous.

Use `DATASET` spread only when both bid and ask are present. For midpoint or trade-price data, choose an explicit fixed-price or basis-point spread. A zero synthetic spread is allowed only when intentionally configured and remains visible in the run assumptions.

## Interpret results

- Signals use the completed candle and fill at the next candle open.
- Same-timestamp cycles process queued exits, queued entries, stop/target
  handling, and close evaluation in that order, with stable instrument ordering.
- Equity and drawdown use candle-resolution marks.
- A stop and target inside the same candle resolves to the stop unless higher-resolution data establishes ordering.
- Gap-through stops use the less favorable candle open; end-of-run closes use
  the final candle close.
- Binance spot data is venue-specific and does not reproduce an IG crypto CFD.
- One-minute OHLC is not tick or quote replay and cannot prove exact intraminute fill order.
- Backtest trades are isolated simulation records, never broker-confirmed executions.

The result summary keeps closed and open performance separate:

- `Realised P&L` is closed fill-to-fill gross P&L.
- `Unrealised P&L` marks positions left open to the final executable candle
  side.
- `Fees paid` includes closed entry/exit fees and entry fees already paid on
  positions left open.
- `Total P&L = realised P&L + unrealised P&L - fees paid`.
- `Ending equity = starting capital + total P&L`.
- `Ending cash` excludes unrealised P&L. `Open position value` is gross marked
  notional and is not deducted from the P&L cash ledger.
- Spread and slippage are embedded in fill prices. Their cost fields are
  attribution and are not subtracted again.
- Closed-trade win rate and return exclude positions still open at the end.

`MARK_TO_MARKET` retains positions and includes unrealised P&L in total return.
`CLOSE_AT_END` closes them at the final candle close. Exposure is the
wall-clock union of closed and open position intervals, so overlapping
instruments do not count the same elapsed time twice.
Open marks use the executable bid/ask or synthetic-spread side but do not
reserve a future exit fee or hypothetical exit slippage.

Percent-risk sizing uses the expected spread/slippage-adjusted entry fill,
stop-exit slippage, and configured entry/exit fees. It uses continuous units
and does not apply broker lot steps, minimum sizes, margin, or financing. The
persisted absolute sizing tolerance is `1e-9` account units; non-gap stop
execution tests require actual simulated net loss to remain within that
tolerance of the configured risk budget.

Backtests do not currently persist a real account currency. Monetary values in
the UI are labelled as account units and must not be read as GBP. Price
decimals are adaptive display formatting, not broker tick precision.

Profit factor is null unless both winning and losing closed trades exist. The
typed API supplies `NO_CLOSED_TRADES`, `NO_LOSING_TRADES`, or
`NO_WINNING_TRADES` as the null reason.

Completed runs show a result checksum covering deterministic strategy,
dataset, assumptions, trades, equity, metrics, warnings, and per-instrument
results. Database IDs, display name/notes, wall-clock audit timestamps, and
dataset partition row IDs are excluded. The checksum proves equality of the
covered persisted projection, not source-build authenticity or broker realism.

Completed runs must have no failure reason; the API and checksum verifier
reject inconsistent completed rows. Failed runs retain the failure reason and
configuration for diagnosis, but do not receive a completed-result manifest or
checksum.

The Binance still-open-candle filter and staged import
publication/reconciliation behavior are retained as explicitly reviewed
dataset-integrity fixes. Their focused provider tests do not count as proof of
accounting correctness, and replay still makes no provider, broker, strategy,
or live-trading mutation.

See [backtesting-user-guide.md](backtesting-user-guide.md) for the complete
operator workflow, availability states, recovery behavior, and current limits.
