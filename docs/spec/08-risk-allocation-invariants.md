# Risk and allocation invariants

Risk and allocation protect the system from admitting new entry risk when market data, broker sizing, account equity, operational state, or portfolio budgets do not support it.

## Current implementation evidence

| Area | Evidence | Current verification confidence |
| --- | --- | --- |
| Capital allocation | `backend/app/services/capital_allocator_service.py`, `backend/tests/test_capital_allocator_service.py` | High |
| Hard risk overlay | `backend/app/services/portfolio_risk_service.py`, `backend/tests/test_portfolio_risk_service.py` | High |
| Decision persistence | `backend/app/services/trade_decision_service.py`, `backend/tests/test_trade_decision_service.py` | High |
| Allocation reads/alerts | `backend/app/services/allocation_read_service.py`, `backend/app/services/allocation_alert_service.py`, `backend/tests/test_allocation_read_service.py` | High |
| Frontend risk surfaces | `frontend/components/risk/*`, `frontend/lib/risk-allocation.ts`, dashboard risk panels | Medium |

## Allocation cycle purpose

An allocation cycle ranks and filters entry candidates, requests broker/account/sizing data, applies budget constraints, reserves selected risk, persists cycle summary, and provides audit evidence for admitted/rejected candidates. It does not guarantee order submission; `TradeIntent` admission and execution-time revalidation still apply. Allocation approval must not be treated as broker execution approval, broker fill confirmation, or exact live risk truth. Allocation decisions must leave durable audit evidence for selected and rejected candidates. Allocation must fail closed for new entries when required broker, market, account, sizing, or operational inputs are unavailable or invalid.

## Risk accounting terminology

- Requested risk: the risk requested by a strategy candidate or signal before allocation caps, broker sizing, normalization, or portfolio budgets are applied.
- Allocated risk: the risk amount admitted by the allocator after budget checks, broker sizing quote, and normalization.
- Reserved risk: risk held for active intents or execution attempts that are not yet terminal. This includes approved, submitted, acknowledged, partially filled, and other active ownership states where future exposure may still exist.
- Live risk: risk from open positions or broker/local open exposure.
- Post-fill risk: risk recomputed after broker-confirmed or simulated fill data is available.
- Risk truth: the best-known risk value plus its confidence/provenance.
- Risk truth confidence: label describing whether the risk value is exact, broker-confirmed estimated, partial/provisional, submitted estimate, allocation-only, simulated, degraded, or unknown.
- Risk drift: material difference between allocated, submitted, filled, normalized, broker-confirmed, or live risk.
- Entry risk: new exposure created by a new position or increased exposure.
- Exit risk handling: actions intended to reduce, close, or safely manage existing open risk. Exit handling must not be blocked by entry-only allocation constraints.

## Invariants

| Spec ID | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- |
| RISK-001 | Allocation MUST NOT approve entries exceeding configured risk budgets after broker sizing, min-size, size-step normalization, reserved risk, live risk, and concentration limits are considered. If broker minimum size would require more risk than the available budget, the candidate must be rejected or explicitly marked under-minimum/unadmissible. | Tests for portfolio, family, strategy, instrument, currency, gross exposure, concentration, reserved/live risk, min-size round-up, and size-step normalization budgets. | P0 | High |
| RISK-002 | Stale, missing, fallback-disallowed, disconnected, closed, offline, suspended, or invalid market data MUST block new entry risk. Price availability alone must not imply entry eligibility. | Portfolio/strategy-service tests for stale prices, market status gates, fallback policy, disconnected feeds, and price-present-but-entry-blocked cases. | P0 | High |
| RISK-003 | Risk truth confidence MUST be explicit whenever risk is shown to operators or used for read-model decisions and the value is estimated, degraded, simulated, provisional, partial, submitted-only, allocation-only, fallback-derived, broker-confirmed estimated, or unknown. Absence of confidence must not be treated as exact. | Risk fields, allocation read tests, frontend risk rendering tests, and unknown-confidence fixtures. | P1 | Medium |
| RISK-004 | Post-fill risk MUST be recomputed from broker-confirmed fill size and fill price where available. Exact fill-derived risk must only be labelled exact when the required fill evidence is present. Otherwise the system must use an appropriate estimated/provisional/unknown confidence label. | Tests showing fill-derived risk, exact confidence only with supporting evidence, broker-confirmed estimated fallback, partial-fill provisional handling, and simulated fill provenance. | P1 | High |
| RISK-005 | Allocation alerts MUST be persistent, auditable, actor/timestamp preserving where applicable, reopenable on recurrence, and linked to allocation cycle, intent, execution, position, instrument, or risk context where possible. Alert acknowledgement must not imply risk resolution. | `AllocationAlert` model tests and acknowledge/resolve/recurrence/linkage tests. | P1 | High |
| RISK-006 | UI MUST NOT display estimated, provisional, simulated, submitted-only, allocation-only, fallback-derived, degraded, or unknown risk as exact broker-confirmed or exact fill-derived risk. | Frontend tests for risk confidence labels, degraded states, simulated values, partial fills, and unknown confidence. | P1 | Low |
| RISK-007 | Exit paths MUST NOT be blocked by entry-only allocation constraints. Existing open risk must retain an exit-capable, recovery, reconciliation, or manual-review path even when new entries are blocked by budgets, stale data, governance, or allocation policy. | Exits-only, close-path, broker failure, open-risk, and manual-review tests. | P0 | High |
| RISK-008 | Broker sizing and normalization MUST remain a broker-boundary concern. Risk/allocation services may consume broker-neutral quote/normalization DTOs but must not reimplement IG-specific point, pip, contract, currency, lot, precision, or minimum-size semantics. | Tests proving allocator consumes `BrokerRiskSizingQuote` and `BrokerSizeNormalization`, plus code search proving no IG-specific sizing semantics leak into allocation services. | P1 | High |
| RISK-009 | Execution-time sizing, market, account, and risk drift MUST be revalidated before broker submission and visible after submission/fill. Material drift in size, normalized size, stop distance, risk amount, account equity, market status, broker metadata, or fill-derived risk must create operator-visible evidence. | Strategy-service revalidation tests, allocation drift alerts, execution drift tests, and frontend/read-model tests for material drift. | P1 | High |
| RISK-010 | Currency exposure summaries MUST label exactness, proxy/split attribution, directional netting, gross/net mode, and any unsupported or approximate currency conversion behavior. | Allocation read notes, backend read-model tests, and UI labels for currency exposure exactness/proxy behavior. | P2 | Medium |
| RISK-011 | Risk truth confidence labels should be centralized into an explicit enum or documented contract before new labels are added. Unknown or missing labels must render as unknown/degraded, not exact. | Central enum/spec contract, backend tests for all labels, frontend enum parity tests. | P1 | Medium |
| RISK-012 | Reserved risk MUST be created, updated, released, or converted to live risk according to intent/execution/position lifecycle state. Terminal rejected, failed, cancelled, closed, or expired states must not continue reserving risk unless explicitly documented. | Tests for reservation creation, conversion to live risk, release on terminal states, partial-fill handling, and failed/cancelled execution cleanup. | P0 | Medium |
| RISK-013 | Risk accounting MUST avoid double-counting the same exposure as both reserved and live risk unless explicitly documented as conservative overlap. Any overlap must be visible in read models. | Tests for approved-to-filled transition, partial-fill transition, position-opened transition, and allocation read totals. | P0 | Medium |
| RISK-014 | Concurrent or repeated allocation cycles MUST NOT admit duplicate/conflicting exposure, exceed budgets through race conditions, or bypass active intent uniqueness. | Tests for simultaneous candidates, same-instrument conflicts, duplicate direction conflicts, overlapping cycles, and active intent uniqueness. | P0 | Medium |
| RISK-015 | Broker account equity, market metadata, sizing quote, and normalization failures MUST fail closed for new entries unless an explicit degraded-entry mode is documented and tested. | Tests for broker account failure, metadata failure, unsupported sizing, quote failure, normalization failure, and approximate sizing restrictions. | P0 | High |
| RISK-016 | Allocation cycles MUST persist enough evidence to reconstruct candidate selection, rejection reasons, budget bindings, broker sizing inputs/outputs, reserved risk, unavailable inputs, and degraded conditions. | `AllocationCycle`/read-model tests proving cycle summaries include candidate counts, approval/rejection reasons, binding budgets, unsupported sizing counts, stale-data counts, and degraded flags. | P1 | Medium |
| RISK-017 | Frontend risk surfaces MUST show or make inspectable risk provenance, including confidence, source, timestamp/freshness where applicable, reserved vs live split, degraded/unknown status, and alert linkage. | Frontend component tests for dashboard risk panels, risk page/drawer, allocation alerts, and degraded/unknown fixtures. | P1 | Low |
| RISK-018 | Allocation alert refresh that persists alert changes MUST be classified as mutation-like active read/refresh or moved to an explicit mutation endpoint. It must not be treated as passive GET behavior. | Route tests and API contract review for `GET /allocation/alerts` with `refresh=true` or replacement endpoint. | P1 | Medium |

## Candidate selection and budgets

The allocator currently considers:

- Signal freshness.
- Account equity from broker.
- Broker market metadata and risk-sized quote.
- Duplicate/direction conflict suppression.
- Portfolio position/risk budgets.
- Strategy/family/instrument/currency budgets.
- Gross notional exposure.
- Broker min size and size step normalization.
- Live account restrictions for approximate sizing.
- Reserved risk from pending/approved/submitted/acknowledged/partially filled intents.

## Budget hierarchy and binding budgets

Allocation should identify which budget or gate bound each candidate decision.

Budget/gate categories include:

- portfolio risk budget;
- family risk budget;
- strategy risk budget;
- instrument risk budget;
- currency exposure budget;
- gross notional exposure;
- reserved risk;
- live risk;
- concentration/hotspot limits;
- broker minimum size;
- broker size step/precision;
- account equity availability;
- market status/freshness;
- operational entry eligibility.

Rejected candidates should preserve rejection reasons. Approved candidates should preserve the binding budget or limiting factor where applicable.

## Requested vs allocated risk

- Requested risk is pre-allocation intent.
- Allocated risk is post-budget/post-broker-normalization admission.
- Allocated risk may be lower than requested risk.
- Allocated risk must not exceed available budget after normalization.
- Reserved risk is not the same as live risk.
- Live risk must come from open exposure and carry confidence.
- Partial fills may create both remaining reserved risk and live/provisional risk.
- Terminal states should release reservations unless explicitly documented.
- Read models must make reserved/live/estimated/provisional distinctions visible.

## Risk truth confidence

Risk truth confidence must describe both value source and degradation.

Known or expected labels may include:

- `EXACT_FILL_DERIVED`
- `PARTIAL_FILL_PROVISIONAL`
- `BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED`
- `SUBMITTED_EXECUTABLE_ESTIMATE`
- `ALLOCATION_INTENT_ONLY`
- `INCOMPLETE_DEGRADED`
- `SIMULATED_LOCAL_FILL`
- `UNKNOWN`

If the exact enum differs, this section needs confirmation rather than invented implementation truth.

Rules:

- `EXACT_FILL_DERIVED` requires filled size, fill price, and enough stop/risk context to recompute risk.
- `PARTIAL_FILL_PROVISIONAL` must not be displayed as exact live risk.
- `BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED` means broker evidence exists, but risk is still estimated.
- `ALLOCATION_INTENT_ONLY` must not be displayed as submitted, filled, or live risk.
- `SIMULATED_LOCAL_FILL` must not be displayed as broker-confirmed truth.
- `UNKNOWN` or missing confidence must render as degraded/unknown.

## Stale data and market gates

New entries must block when:

- price age exceeds configured freshness;
- market is closed, offline, suspended, unavailable, or dealing-restricted;
- feed source is stale or disconnected;
- polling fallback is disallowed by entry policy;
- broker metadata is unavailable or invalid;
- account equity is unavailable or invalid;
- broker sizing quote is unavailable, unsupported, or invalid;
- broker normalization fails or normalizes to unsafe/budget-exceeding size;
- operational entry eligibility is blocked;
- kill switch, emergency stop, unmanaged open risk, or risk budget exhaustion applies.

Exits have different gates. Exit paths may remain eligible under degraded market-data conditions only when broker connectivity, dealing rules, open-risk authority, and close safety requirements support it.

## Allocation alerts

Current alert categories include degraded cycles, approximate live sizing blocks, repeated revalidation failures, broker submission failures, under-minimum rejections, hard-risk blocks, missing broker sizing metadata, material execution drift, incomplete fill truth, concentration hotspots, stale market data, unsupported broker sizing, reservation/live-risk mismatch, ambiguous broker confirmation, and partial-fill provisional risk.

Alert state rules:

- `OPEN` means unresolved operator-visible risk/allocation issue.
- `ACKNOWLEDGED` means operator has acknowledged the alert; it does not mean the underlying condition is resolved.
- `RESOLVED` means the condition is resolved or explicitly marked resolved with actor/timestamp/reason evidence.
- Recurrence should reopen or create linked alert evidence without erasing history.
- Alert refresh that writes persisted state is mutation-like.
- Critical alerts should be surfaced on operator-critical UI surfaces.

Alerts must be:

- Persistent.
- Acknowledgeable/resolvable.
- Reopenable on recurrence.
- Linked to intent/cycle/execution IDs where possible.

## Broker sizing boundary

Risk services may request a broker-neutral sizing quote and normalization. They must not reimplement IG-specific point/pip semantics. Allocation may use quote fields like `risk_per_unit`, `stop_distance_price`, `precision`, `mode`, `normalization`, and `details`, but the meaning of those fields must be defined by the broker contract.

Rules:

- `BrokerRiskSizingQuote` and `BrokerSizeNormalization` define broker-neutral sizing semantics for allocation.
- Allocation may use quote fields but must not infer IG-specific point/pip/contract meaning.
- Unsupported sizing modes must fail closed for entries unless explicitly documented/tested.
- Broker minimum size and step normalization must not cause budget overrun.
- Details/debug fields from broker quotes must not become hidden app-service dependencies on raw IG payload shape.

## Allocation API route expectations

Allocation read routes should be classified according to the backend API contract.

Expected classifications:

- `GET /allocation/cycles`: passive read
- `GET /allocation/cycles/{cycle_id}`: passive read
- `GET /allocation/intents`: passive read
- `GET /allocation/intents/{trade_intent_id}`: passive read
- `GET /allocation/drift`: passive read/projection, needs write audit
- `GET /allocation/exposure`: passive read/projection, needs write audit
- `GET /allocation/alerts`: passive read by default
- `GET /allocation/alerts?refresh=true`: active read/refresh or redesign candidate
- `POST /allocation/alerts/{alert_id}/acknowledge`: mutation
- `POST /allocation/alerts/{alert_id}/resolve`: mutation
- `GET /allocation/alerts/unresolved-critical`: passive read of persisted unresolved critical alerts

Do not invent certainty. If the actual route behavior differs, mark Needs audit.

## Must-not-cross risk boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| RISK-BND-001 | Allocation vs execution | Allocation approval must not be treated as broker submission or fill confirmation. | Intent/execution lifecycle tests. | P0 |
| RISK-BND-002 | Entry vs exit gates | Entry-only allocation constraints must not block safe exit/open-risk handling. | Exits-only and close-path tests. | P0 |
| RISK-BND-003 | Broker sizing boundary | Allocation must consume broker-neutral sizing DTOs and not IG-specific sizing semantics. | Broker sizing boundary tests/code review. | P1 |
| RISK-BND-004 | Estimated vs exact risk | Estimated/provisional/simulated/unknown risk must not be displayed as exact. | Backend confidence and frontend rendering tests. | P1 |
| RISK-BND-005 | Reserved vs live risk | The same exposure must not be double-counted or dropped during lifecycle transitions. | Reservation/live-risk transition tests. | P0 |
| RISK-BND-006 | Stale data gate | Stale/invalid/unavailable market or broker data must fail closed for entries. | Stale/broker failure tests. | P0 |
| RISK-BND-007 | Alert lifecycle | Acknowledging an alert must not imply risk resolution. | Alert state tests. | P1 |
| RISK-BND-008 | Alert refresh side effect | Persisting alert refresh must not be treated as passive read behavior. | API route tests. | P1 |
| RISK-BND-009 | Frontend risk truth | UI must not infer stronger risk truth than backend confidence/provenance supports. | Frontend contract tests. | P1 |

## Known unknowns

- The complete `risk_truth_confidence` label set is not centralized.
- Frontend test evidence for estimated/provisional risk rendering was not found.
- Currency exposure exactness uses proxy/split attribution; this is documented in read-model notes but may need operator UI labels.
- Reservation lifecycle and release rules may not be centrally documented across intent/execution/position transitions.
- Reserved risk and live risk may overlap during partial-fill or position-opened transitions; expected overlap behavior needs confirmation.
- Concurrent allocation cycles and active intent uniqueness need explicit audit coverage.
- Execution-time revalidation drift thresholds and materiality rules need confirmation.
- Allocation alert refresh via GET `refresh=true` remains mutation-like and may later move to POST or another mutation-classified endpoint.
- Frontend risk surfaces may not consistently label confidence, timestamp/freshness, simulated values, or degraded/unknown state.
- Currency exposure exactness/proxy/split attribution may need stronger operator-facing labels.
- Broker sizing details/debug fields may leak broker-specific assumptions if app services depend on raw details shape.
- Unsupported sizing, account equity failure, and broker metadata failure paths need audit confirmation for fail-closed behavior.

## Required tests

- Behavioral tests for every `RISK` invariant.
- Tests proving allocation rejects candidates that exceed budgets after broker min-size and size-step normalization.
- Tests proving stale, disconnected, fallback-disallowed, closed, offline, suspended, unavailable, or dealing-restricted markets block entries.
- Tests proving broker account equity, metadata, quote, unsupported sizing, and normalization failures fail closed for entries.
- Tests proving reserved risk is created, updated, released, or converted to live risk according to lifecycle state.
- Tests proving reserved and live risk are not double-counted or dropped during approved/submitted/acknowledged/partial-fill/filled/position-opened/closed/failed/cancelled transitions.
- Tests for concurrent allocation cycles, duplicate same-instrument candidates, direction conflicts, and active intent uniqueness.
- Tests proving post-fill risk is exact only when fill-derived evidence is present.
- Tests for all risk truth confidence labels and unknown/missing confidence behavior.
- Tests proving simulated/local fills are not displayed as broker-confirmed risk.
- Tests proving material execution-time drift creates allocation drift evidence or alerts.
- Tests proving alert acknowledge/resolve/reopen preserves actor/timestamp/reason/linkage evidence.
- Route tests for allocation read/alert endpoints, including `GET /allocation/alerts` default passive behavior and `refresh=true` mutation-like behavior if retained.
- Frontend tests for risk confidence, degraded alerts, reserved/live/provisional/estimated/simulated/unknown risk, and currency exposure exactness labels.

## Audit questions for Codex

- Can any allocation path select a candidate with stale, disconnected, fallback-disallowed, closed, suspended, or unsupported market data?
- Can any allocation path select a candidate when broker account equity, metadata, quote, or normalization fails?
- Can broker min-size or size-step normalization cause allocated risk to exceed available budget?
- Are requested, allocated, reserved, live, post-fill, and drift risk clearly separated in models and read views?
- Can reserved risk remain after intent/execution terminal failure, rejection, cancellation, close, or expiry?
- Can the same exposure be counted as both reserved and live without explicit conservative-overlap labeling?
- Can concurrent allocation cycles exceed budgets or create duplicate/conflicting active intents?
- Are risk truth confidence labels always present when risk is shown to operators?
- What happens when risk truth confidence is missing or unknown?
- Does any frontend risk surface display estimated, provisional, simulated, submitted-only, allocation-only, fallback-derived, degraded, or unknown risk as exact?
- Does alert acknowledgement imply risk resolution anywhere in backend or frontend copy?
- Does alert refresh on GET need to move to a mutation endpoint?
- Do allocation services depend on IG-specific point/pip/contract semantics or raw quote details?
- Are currency exposure exactness, proxy attribution, and directional netting visible to operators?
- Are execution-time drift thresholds documented and tested?
