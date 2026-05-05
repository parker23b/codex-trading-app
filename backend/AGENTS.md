# backend/AGENTS.md

## Backend review guidelines

Pay special attention to:

- GET routes that mutate state.
- Services that bypass the broker abstraction.
- Broker-specific semantics leaking outside app/core/ig_broker.py or the broker boundary.
- Any code path that creates Execution records without an approved TradeIntent.
- Any runtime ownership change that can strand open broker risk.
- Read services calling session.add, session.delete, session.commit, session.flush.
- Broad exception handling around broker calls.
- Tests that mock away market-status or broker-failure behaviour.
