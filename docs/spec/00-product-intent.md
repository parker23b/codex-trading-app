# InvestMate product intent

InvestMate is an operator console and backend control system for supervised autonomous trading. This document defines the product promise and safety posture that all implementation specs should preserve.

## Current implementation evidence snapshot

| Area | Evidence | Current verification confidence |
| --- | --- | --- |
| Backend shape | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/services/*` | High |
| Frontend operator surfaces | `frontend/app/page.tsx`, `frontend/app/control-plane/page.tsx`, `frontend/app/coverage/page.tsx`, `frontend/app/markets/page.tsx`, `frontend/app/events/page.tsx`, `frontend/app/strategies/page.tsx` | High |
| Broker integration | `backend/app/core/broker.py`, `backend/app/core/ig_broker.py`, `backend/app/services/ig_streaming_service.py` | High |
| Intent/execution lifecycle | `backend/app/models/trade.py`, `backend/app/services/trade_decision_service.py`, `backend/app/services/strategy_service.py`, `backend/tests/test_intent_lifecycle_integration.py` | High |
| AIMEE read-only companion | `backend/app/services/aimee_read_service.py`, `backend/app/api/routes/aimee.py`, `backend/tests/test_aimee_read_service.py`, `frontend/components/aimee/*` | High |

## Product requirements

| Spec ID | Requirement | Evidence expected | Safety severity if violated | Current confidence |
| --- | --- | --- | --- | --- |
| PROD-001 | InvestMate is a supervised autonomous trading operator console, not a retail manual trading terminal. | Product text, backend control-plane services, frontend operator surfaces. | P2 | High |
| PROD-002A | Autonomous decisions must be observable. | Domain events, dashboard/control-plane/coverage/risk surfaces, risk truth fields. | P1 | Medium |
| PROD-002B | Operator-facing surfaces must show confidence/provenance for decision, risk, and broker state. | Domain events, dashboard/control-plane/coverage/risk surfaces, risk truth fields. | P1 | Medium |
| PROD-003 | Trading autonomy must be bounded by governance, operational health, market-data freshness, broker state, and risk limits. | Governance, operational-state, market-data, broker, allocator, and strategy-service tests. | P0 | High |
| PROD-004 | TradeIntent is the authoritative pre-trade decision boundary. Execution records must not replace decision truth. Order submission invariant: - New entry orders MUST require an APPROVED TradeIntent. - Exit/close orders MUST require either: - a linked open Position with exit eligibility, or - an auditable recovery/reconciliation record representing broker-confirmed open risk. - No order path may bypass durable local lifecycle state entirely. | `TradeIntent` model and decision-service tests proving rejected decisions do not submit orders. | P0 | High |
| PROD-005 | Execution represents an execution attempt after approval or a close/recovery path, not the pre-trade approval state itself. | `ExecutionPhase`, `ExecutionStatus`, strategy-service tests. | P0 | High |
| PROD-006 | Read-only services and passive UI surfaces must not mutate operational state. For this spec, mutation means creating, updating, deleting, flushing, committing, seeding, reconciling, refreshing, acknowledging, resolving, or otherwise changing durable operational state as a side effect of a passive read. | Tests proving no writes/side effects for read services and dashboards. | P1 | Medium |
| PROD-007 | Broker-specific behavior must be isolated behind broker adapter boundaries. | `Broker` interface, IG adapter, allocator tests proving broker-neutral sizing. | P1 | Medium |
| PROD-008 | The UI must not imply stronger certainty than backend data supports. Estimated, degraded, stale, fallback, or unknown data must be visibly distinct from exact broker-confirmed truth. | Frontend status/provenance display tests and backend confidence fields. | P1 | Low |
| PROD-009 | Recovery and reconciliation must preserve auditability for out-of-band broker truth. | Reconciliation/runtime recovery tests proving explicit intent/event records. | P0 | High |
| PROD-010 | Critical trading behavior requires behavioral tests, not only object construction or happy-path tests. | Test names and assertions around failure modes, stale data, broker errors, and state transitions. | P1 | Medium |
| PROD-011 | No known open broker position may become unmanaged without explicit operator-visible state, domain-event evidence, and either an exit-capable runtime, recovery path, or manual-review state. | | P0 | |
| PROD-012 | Material lifecycle transitions for governance, deployment, runtime, intent, execution, position, risk, allocation, reconciliation, and recovery must emit durable domain/audit evidence with enough context to reconstruct why the transition occurred. | | P1 | |
| PROD-013 | Frontend surfaces must render backend-provided trading truth and may derive presentation summaries only when the derivation is deterministic, local, and does not change certainty, severity, or lifecycle meaning. | | P1 | |
| PROD-014 | When autonomy cannot act because of health, broker, market-data, governance, or risk constraints, the system must fail closed for entries and expose the blocked/degraded reason to the operator. | | P0 | |

## What InvestMate is

InvestMate is:

- A Python FastAPI backend coordinating strategy runtimes, market data, broker access, trade decisions, execution attempts, recovery, risk/allocation, and operator read models.
- A Next.js/TypeScript operator console for supervision, investigation, intervention, and review.
- A governed autonomy system where strategies may run automatically only inside explicit operational and risk boundaries.
- An IG Markets integration through a broker adapter, with streaming through Lightstreamer where enabled and fallback polling where needed.
- A system that records enough decision, execution, risk, and reconciliation evidence for later audit.

## What InvestMate is not

InvestMate is not:

- A promise of profitable trading.
- A black-box broker wrapper where orders can be emitted without reviewable local lifecycle state.
- A UI that treats estimated or degraded risk as exact broker-confirmed truth.
- A pure manual trading terminal.
- A generic market-data platform.
- A chat assistant that can mutate trades, governance, watchlists, or broker state through passive reads.

## Target user

The target user is an operator/developer supervising autonomous trading behavior. The operator needs to see system health, open exposure, strategy/runtime state, broker connectivity, market-data freshness, allocation decisions, coverage state, domain events, and AIMEE explanations.

## Safety philosophy

Safety is based on explicit boundaries and failure-closed defaults:

- Pre-trade decisions become durable as `TradeIntent`.
- Broker execution attempts become durable as `Execution`.
- Open exposure becomes durable as `Position`.
- Realized outcomes become durable as `Trade`.
- Out-of-band broker truth becomes explicit reconciliation/recovery records.
- New entries MUST block on stale market data, broker metadata failures, operational entry ineligibility, risk budget exhaustion, or governance blocks.
- Exit paths MUST remain available for open risk even when entry autonomy is blocked.

## Autonomy philosophy

Autonomy is supervised and layered:

1. Governance defines what strategy families may do.
2. Operator control enables or overrides global autonomy.
3. Deployment chooses system-owned autonomous lifecycle state.
4. Runtime is a running strategy instance with `MANUAL` or `AUTO` control and `NORMAL`, `EXITS_ONLY`, or `STOPPED` runtime mode.
5. Coverage and market data determine which instruments can be evaluated.
6. Risk/allocation controls admit or reject entry candidates.
7. Broker execution happens only after the decision boundary is satisfied.

## Observability expectations

The product must expose:

- Current operational health and degraded conditions.
- Every operator-facing market-data display MUST expose source/provenance, freshness timestamp or age, and fallback/degraded state when applicable. The frontend MUST NOT infer these values when backend fields are absent.
- Governance, deployment, runtime alignment, and operator overrides.
- Allocation cycle decisions, reserved/live risk, and confidence.
- Execution status, broker references, failure/manual-review states, and risk drift.
- Domain events with enough context to reconstruct major lifecycle decisions.
- AIMEE passive explanations derived from read-only snapshots.

## Severity definitions

- P0: Could allow unsafe trading, unbounded risk, un-auditable broker action, or unmanaged open exposure.
- P1: Could mislead the operator, hide degraded state, mutate state unexpectedly, or weaken auditability.
- P2: Could cause product drift, confusing UX, incomplete diagnostics, or maintainability issues without directly increasing trading risk.

## Non-goals

- Multi-broker parity beyond the broker-neutral contract unless implemented and tested.
- Full migration guarantees for historical dev databases unless covered by explicit migration tests.
- Frontend-only inference of trading truth that is not backed by backend fields.
- Automatic remediation of unmanaged open broker risk without an auditable recovery or operator path.

## Known unknowns

- Whether all GET routes are side-effect free; several read routes call services that may seed defaults or refresh alerts.
- Whether OpenAPI schemas are complete for all dict-shaped responses.
- Whether all frontend surfaces have automated tests for degraded/stale/error states.
- Whether live IG partial-fill and confirmation edge cases are fully represented by fakes.

## Required tests

- Behavioural tests for every P0/P1 invariant in this spec set.
- Route tests proving passive read endpoints do not write operational state.
- Broker fake tests preserving failure, stale-data, partial-fill, and sizing semantics.
- Frontend tests for stale/degraded/estimated display semantics on dashboard, risk, coverage, and control-plane surfaces.

## Audit questions for Codex

- Does any route or read service perform `session.add`, `session.delete`, `session.commit`, or `session.flush` without being classified as a mutation?
- Can any order submission happen without an approved `TradeIntent`?
- Can any open position become unmanaged without a domain event and operator-visible state?
- Do frontend labels ever rename backend states in a way that implies higher certainty?

## Audit interpretation rules

When reviewing implementation against this spec:

- Treat P0 violations as blocking.
- Treat P1 violations as requiring either a fix or an explicit tracked exception.
- Do not accept frontend-only evidence for backend truth.
- Do not accept object construction tests as evidence for lifecycle safety.
- Prefer behavioural tests that prove forbidden transitions cannot happen.
- Any route classified as passive/read-only must be checked for direct and indirect writes.
- Any order submission path must be traced backward to its lifecycle authority.
