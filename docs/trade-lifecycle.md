# Trade Lifecycle

InvestMate uses an intent-first lifecycle. The goal is to keep pre-trade decision authority, broker attempts, live exposure, and closed outcomes separate enough to audit and recover safely.

## Core Records

- `TradeIntent` is the decision-lifecycle authority.
- `Execution` is broker-attempt and execution-audit only.
- `Position` is live local exposure.
- `Trade` is the closed realized outcome.

## Entry Flow

1. Strategy logic creates raw entry candidates from market conditions.
2. `TradeDecisionService` turns candidates into `TradeIntent` proposals.
3. Market, governance, allocation, sizing, broker-size, and same-instrument gates admit or reject the intent.
4. Rejected candidates remain decision records and do not create new `Execution` rows.
5. Approved intents can create an `Execution` beginning at `SUBMISSION_PENDING`.
6. Broker-attempt states progress through values such as `ORDER_SUBMITTED`, `ORDER_ACKNOWLEDGED`, `FILL_PARTIAL`, `FILL_FULL`, `FAILED`, `CANCELLED`, `NEEDS_MANUAL_REVIEW`, and `POSITION_OPENED`.
7. Filled executions create or update local `Position` records.

Compatibility note: legacy execution statuses such as `SIGNAL_GENERATED`, `RISK_APPROVED`, and `RISK_REJECTED` remain in the enum for older persisted rows, but new entry code should not use them as the current approval flow.

## Exit Flow

1. Exit signals require a linked open `Position`.
2. Close-side execution requires close-valid intent authority or explicit recovery/reconciliation authority.
3. Confirmed closes become `Trade` records.
4. The linked local `Position` is closed.
5. The linked `TradeIntent` moves to the appropriate closed lifecycle state.

Failed, partial, rejected, and ambiguous close paths have targeted tests preserving open-risk authority and manual-review state. The remaining architecture gap is that open-risk management ownership is split across position, deployment, runtime, and derived operational-state records (`AUDIT-ARCH-002`).

## Same-Instrument Exclusivity

The backend is intended to enforce one active instrument owner at a time.

- Application-level conflict resolution happens first in [../backend/app/services/trade_decision_service.py](../backend/app/services/trade_decision_service.py).
- Persistence-level enforcement lives in [../backend/app/models/trade.py](../backend/app/models/trade.py) as the partial unique index `uq_trade_intent_active_instrument`.
- Active ownership states include `PROPOSED`, `APPROVED`, `SUBMITTED`, `ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `POSITION_OPENED`, `CLOSE_REQUESTED`, `EXTERNAL_POSITION_ADOPTED`, and `RECOVERED_POSITION_ATTACHED`.

If two workers race to admit the same instrument, the database should reject the second active owner.

Aggregate portfolio admission is additionally serialized around snapshot calculation, allocation, risk checks, and durable intent admission. SQLite/local operation uses a process lock; Postgres uses a transaction-scoped advisory lock so distinct workers cannot approve different instruments from the same stale aggregate budget snapshot.

## Recovery And Reconciliation

Runtime recovery in [../backend/app/services/runtime_recovery_service.py](../backend/app/services/runtime_recovery_service.py) is intended to attach broker-confirmed positions to explicit local lifecycle evidence such as `RECOVERED_POSITION_ATTACHED`.

Reconciliation in [../backend/app/services/reconciliation_service.py](../backend/app/services/reconciliation_service.py) records broker/local drift:

- unmatched broker positions create adopted lifecycle records such as `EXTERNAL_POSITION_ADOPTED`
- broker-missing local positions create forced-close lifecycle records such as `FORCED_RECONCILIATION_CLOSE`

Stopped-runtime startup recovery now has backend regression coverage proving broker-confirmed open risk receives explicit `RECOVERED_POSITION_ATTACHED` intent/position evidence before the runtime remains paused.

Periodic reconciliation runs in an independent leader-owned supervisor. It continues on its configured cadence even when the active market-data watchlist is empty.

## Target Invariants

- No order submission without an authoritative `TradeIntent`.
- No exit without a linked close-valid intent or explicit recovery/reconciliation authority.
- No recovered live position without visible local lifecycle evidence.
- One active instrument owner at a time.
- Broker acknowledgement, timeout, or confirmation ambiguity must not become exact fill truth without confirmation evidence.
- Open broker risk must not become unmanaged without operator-visible state and durable evidence.

Open gaps are tracked in [audit-status.md](audit-status.md).

## Key Files

- [../backend/app/core/trading_engine.py](../backend/app/core/trading_engine.py)
- [../backend/app/models/trade.py](../backend/app/models/trade.py)
- [../backend/app/services/trade_decision_service.py](../backend/app/services/trade_decision_service.py)
- [../backend/app/services/strategy_service.py](../backend/app/services/strategy_service.py)
- [../backend/app/services/trade_service.py](../backend/app/services/trade_service.py)
- [../backend/app/services/runtime_recovery_service.py](../backend/app/services/runtime_recovery_service.py)
- [../backend/app/services/reconciliation_service.py](../backend/app/services/reconciliation_service.py)
