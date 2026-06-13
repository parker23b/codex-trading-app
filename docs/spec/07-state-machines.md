# State machines and lifecycle ownership

State ownership is safety-critical. Reviews must distinguish decision state, execution-attempt state, governance policy, deployment target, runtime reality, and open-risk management.

## Lifecycle terminology

- Decision state: durable pre-trade or recovery decision truth, owned by `TradeIntent`.
- Execution-attempt state: durable record of a broker submission, close, fill, failure, cancellation, partial outcome, or manual-review condition, owned by `Execution`.
- Governance policy: operator-approved permission and constraints for strategy families.
- Deployment target: system-owned autonomous desired state for a governed strategy family.
- Runtime reality: actual persisted and in-memory running strategy instance state.
- Open-risk management state: whether known open risk is managed, exit-only, unmanaged, or absent.
- Terminal state: a lifecycle state that must not become active again without a new explicit lifecycle record or audited recovery transition.
- Transition authority: the service or workflow allowed to move an entity from one state to another.
- Broker ambiguity: a broker result where the system cannot safely prove accepted, rejected, filled, partially filled, closed, cancelled, or failed outcome.
- Recovery provenance: explicit state/evidence showing that lifecycle state came from recovery or reconciliation rather than normal strategy-owned entry.

## State invariants

| Spec ID | Requirement | Required evidence | Severity | Current verification confidence |
| --- | --- | --- | --- | --- |
| STATE-001 | TradeIntent approval/rejection and recovery/adoption transitions MUST happen only through `TradeDecisionService`, `TradeService`, `RuntimeRecoveryService`, `ReconciliationService`, or another explicitly documented lifecycle authority. Direct field mutation outside lifecycle authority is invalid. | Decision-service, trade-service, reconciliation/recovery tests, and code review for direct state assignment. | P0 | High |
| STATE-002 | Execution records must remain execution-attempt audit and MUST NOT replace pre-trade decision state. New entry execution requires approved `TradeIntent` authority, and new execution rows must start at `SUBMISSION_PENDING` or another explicitly documented initial execution-attempt state. | Tests proving rejected/unapproved intents do not create broker order attempts and new executions start at valid initial states. | P0 | High |
| STATE-003 | Manual and AUTO runtime ownership must not be silently reclassified. Changing control mode requires explicit operator/system authority, audit evidence, and must preserve open-risk/protective state. | Control-plane/runtime tests for manual runtime, AUTO deployment, ownership conflicts, and mode-change audit evidence. | P1 | High |
| STATE-004 | Deployment state must not imply runtime alignment unless explicit alignment checks prove matching strategy family, instrument, profile, parameters, control mode, runtime mode, and open-risk state where applicable. | Control-plane alignment fields and mismatch tests. | P1 | High |
| STATE-005 | Known open risk must not be stranded without an exit-capable runtime, recovery path, reconciliation path, or explicit operator-visible manual-review/unmanaged-risk state. | Exits-only, unmanaged-risk, close-failure, recovery, and domain-event tests. | P0 | High |
| STATE-006 | Partial fills, partial closes, ambiguous broker confirmation, and unsafe broker outcomes must restrict runtime behavior until risk is safely managed or explicitly moved to manual-review/reconciliation-needed state. | Strategy-service, broker failure, partial-fill, partial-close, and runtime-mode tests. | P0 | High |
| STATE-007 | Terminal states such as `REJECTED`, `CLOSED`, `FAILED`, `CANCELLED`, `CLOSE_CONFIRMED`, and `RESOLVED` must not return to active ownership without a new lifecycle record or explicit audited recovery/reopen transition. | Transition tests and code review for direct terminal-state reactivation. | P0 | Medium |
| STATE-008 | Broker timeout, rate limit, unknown response, confirmation lookup failure, partial fill, partial close, or ambiguous outcome must not be converted into exact success or exact failure silently. It must produce explicit pending, manual-review, reconciliation-needed, partial, or degraded state. | Broker failure, execution, close, recovery, and reconciliation tests. | P0 | Medium |
| STATE-009 | Frontend state unions and label mappings must cover every backend state displayed in operator UI. Unknown backend states must render as explicit unknown/unsupported states, not healthy/default states. | Frontend enum parity tests for `TradeIntent`, `Execution`, governance, deployment, runtime, alert, health, coverage, and open-risk states. | P1 | Medium |
| STATE-010 | Open-risk management state must be explicit, backend-owned, operator-visible, and preserved across deployment changes, runtime restarts, recovery, and reconciliation. | Control-plane, runtime recovery, reconciliation, and frontend tests for `NO_OPEN_RISK`, `MANAGED`, `EXITS_ONLY`, and `UNMANAGED_OPEN_RISK`. | P0 | Medium |

## Transition ownership rules

- State transitions must happen through the owner service or an explicitly documented recovery/reconciliation workflow.
- Direct assignment to lifecycle state fields outside owner services must be treated as an audit finding.
- P0 lifecycle state fields must not be changed without durable audit evidence.
- Terminal states must not be reactivated silently.
- Recovery and reconciliation may create new lifecycle evidence or attach explicit recovery state, but must not rewrite history as if the original normal lifecycle occurred.
- Frontend code must display backend lifecycle state; it must not create, reinterpret, or upgrade lifecycle truth locally.

Owner services define transition authority. Tests must verify not only that valid transitions work, but that invalid transitions are blocked or impossible through public service/API paths.

## TradeIntent state machine

| Field | Value |
| --- | --- |
| Owner service/model | `TradeDecisionService`, `TradeService`, `StrategyService`, `RuntimeRecoveryService`, `ReconciliationService`; model `TradeIntent`. |
| Source of truth | `backend/app/models/trade.py:TradeIntent.state`. |
| Current verification confidence | High for main entry/close/recovery paths. |

Known states:

- `PROPOSED`
- `REJECTED`
- `APPROVED`
- `SUBMITTED`
- `ACKNOWLEDGED`
- `PARTIALLY_FILLED`
- `FILLED`
- `POSITION_OPENED`
- `CLOSE_REQUESTED`
- `CLOSED`
- `FAILED`
- `CANCELLED`
- `EXTERNAL_POSITION_ADOPTED`
- `RECOVERED_POSITION_ATTACHED`
- `FORCED_RECONCILIATION_CLOSE`

Transition authority:

- Entry proposal and admission are owned by `TradeDecisionService`.
- Entry execution progression may be reflected by `StrategyService`/`TradeService` only after approved intent authority exists.
- Close progression is owned by `TradeService`/`StrategyService` when linked to known open risk.
- Recovery/adoption/forced reconciliation transitions are owned by `RuntimeRecoveryService` and `ReconciliationService`.
- Direct state assignment outside these authorities is invalid unless explicitly documented and tested.

Allowed transition families:

- Entry proposal: strategy candidate -> `PROPOSED`.
- Admission: `PROPOSED` -> `APPROVED` or `REJECTED`.
- Broker attempt: `APPROVED` -> `SUBMITTED` -> `ACKNOWLEDGED` -> `FILLED`/`PARTIALLY_FILLED` -> `POSITION_OPENED` or failure terminal states.
- Close: open/adopted/recovered/partial states -> `CLOSE_REQUESTED` -> `SUBMITTED`/`ACKNOWLEDGED` -> `CLOSED` or `FAILED`/manual-review execution state.
- Recovery: broker-confirmed restored path -> `RECOVERED_POSITION_ATTACHED`.
- Reconciliation adoption: unmatched broker position -> `EXTERNAL_POSITION_ADOPTED`.
- Forced reconciliation close: local open position missing at broker -> `FORCED_RECONCILIATION_CLOSE`.

Broker ambiguity note:

- If broker outcome is unknown, pending, partial, or ambiguous, `TradeIntent` state must not be advanced to exact filled/opened/closed truth without supporting execution/broker evidence.
- If existing state enum cannot represent ambiguity directly, `Execution`/manual-review/reconciliation state must carry the ambiguity and be operator-visible.

Invalid transitions:

- `PROPOSED` directly to broker submission without `APPROVED`.
- `REJECTED` to `SUBMITTED`, `ACKNOWLEDGED`, `FILLED`, `POSITION_OPENED`, or `CLOSE_REQUESTED`.
- `APPROVED` to `POSITION_OPENED` without execution/broker or simulated-fill evidence.
- `PARTIALLY_FILLED` to normal active ownership without risk restriction/manual-review resolution.
- `CLOSED`, `FAILED`, `CANCELLED`, or `FORCED_RECONCILIATION_CLOSE` back to active ownership without new lifecycle evidence.
- `EXTERNAL_POSITION_ADOPTED` or `RECOVERED_POSITION_ATTACHED` shown as normal strategy-owned entry without recovery provenance.

Required tests:

- Transition table tests for all allowed and invalid `TradeIntent` transitions.
- Tests proving owner services are the only public paths that change `TradeIntent` state.
- Tests proving recovery/adoption states remain distinguishable from normal strategy-owned entries.
- Tests proving terminal `TradeIntent` states cannot silently reactivate.

## Execution state machine

| Field | Value |
| --- | --- |
| Owner service/model | `StrategyService`, `TradeService`; model `Execution`. |
| Source of truth | `backend/app/models/trade.py:Execution.status`. |
| Current verification confidence | High for tested execution paths; legacy states remain. |

Current execution states:

- `SUBMISSION_PENDING`
- `ORDER_SUBMITTED`
- `ORDER_ACKNOWLEDGED`
- `FILL_PARTIAL`
- `FILL_FULL`
- `POSITION_OPENED`
- `CLOSE_CONFIRMED`
- `FAILED`
- `CANCELLED`
- `NEEDS_MANUAL_REVIEW`
- Deprecated legacy values: `SIGNAL_GENERATED`, `RISK_APPROVED`, `RISK_REJECTED`, `CLOSE_REQUESTED`

Transition authority:

- `StrategyService` and `TradeService` own normal execution state progression.
- `ReconciliationService` and recovery workflows may create or update execution/manual-review evidence only when representing recovery/reconciliation behavior.
- Broker adapter returns broker-neutral result states but does not own application lifecycle transitions.

Allowed transition families:

- New attempt starts at `SUBMISSION_PENDING`.
- Submission path: `SUBMISSION_PENDING` -> `ORDER_SUBMITTED` -> `ORDER_ACKNOWLEDGED`.
- Fill path: acknowledgement -> `FILL_FULL` -> `POSITION_OPENED` or `CLOSE_CONFIRMED`.
- Partial path: acknowledgement -> `FILL_PARTIAL` -> `NEEDS_MANUAL_REVIEW` or restricted runtime.
- Failure path: pending/submitted/acknowledged -> `FAILED`, `CANCELLED`, or `NEEDS_MANUAL_REVIEW`.

Expected ambiguity handling:

- `SUBMISSION_PENDING` may move to `ORDER_SUBMITTED`, `FAILED`, `CANCELLED`, or `NEEDS_MANUAL_REVIEW` depending on broker result.
- `ORDER_SUBMITTED` or `ORDER_ACKNOWLEDGED` may move to `FILL_PARTIAL`, `FILL_FULL`, `FAILED`, `CANCELLED`, or `NEEDS_MANUAL_REVIEW`.
- Timeout, confirmation lookup failure, rate limit, unknown response, or ambiguous broker state should move to `NEEDS_MANUAL_REVIEW` or an explicit pending/reconciliation-needed state if available.
- `FILL_PARTIAL` must not be displayed as `FILL_FULL` or `POSITION_OPENED` without explicit partial-risk handling.
- `CLOSE_CONFIRMED` requires broker close confirmation, explicit simulated close evidence, or forced reconciliation evidence.

Invalid transitions:

- Deprecated legacy values written by new code.
- `SIGNAL_GENERATED`, `RISK_APPROVED`, `RISK_REJECTED`, or `CLOSE_REQUESTED` treated as current decision truth.
- Execution terminal success without broker reference, confirmation evidence, or explicit simulated/local evidence.
- `FAILED` or `CANCELLED` to success without a new execution attempt or audited correction.
- `NEEDS_MANUAL_REVIEW` silently returning to normal without operator/reconciliation evidence.

Required tests:

- Transition table tests for all allowed and invalid `Execution` transitions.
- Tests proving ambiguous broker outcomes do not become success/failure silently.
- Tests proving legacy execution states are read only for compatibility and not written by new paths.
- Tests proving partial fills and partial closes restrict runtime/open-risk behavior.

## Strategy governance states

| Field | Value |
| --- | --- |
| Owner service/model | `StrategyGovernanceService`; model `StrategyFamilyGovernance`. |
| Source of truth | `approval_state`, `autonomous_operation_allowed`, `emergency_stop`. |
| Current verification confidence | High for control-plane service behavior. |

Known approval states:

- `NOT_APPROVED`
- `APPROVED`
- `DISABLED`

Rules:

- Approval alone does not enable autonomous deployment.
- `autonomous_operation_allowed` and global operator control must also permit deployment.
- `emergency_stop` overrides approval and autonomy.
- `APPROVED` must not be displayed as running.
- `APPROVED` must not imply `autonomous_operation_allowed`.
- `DISABLED` or `emergency_stop` must block new entries.
- `emergency_stop` must not hide existing open risk or remove exit/recovery visibility.
- Global operator control must remain separate from strategy-family governance.

Required tests:

- Emergency stop with no open risk.
- Emergency stop with open risk.
- `APPROVED` but autonomy disabled.
- `APPROVED` but no aligned runtime.
- `DISABLED` while runtime/open risk exists.

## Strategy deployment states

| Field | Value |
| --- | --- |
| Owner service/model | `StrategyDeploymentManagerService`; model `StrategyDeployment`. |
| Source of truth | `StrategyDeployment.state`. |
| Current verification confidence | High for tested control-plane transitions. |

Known states:

- `NOT_APPROVED`
- `APPROVED`
- `AUTO_DEPLOYABLE`
- `AUTO_DEPLOYED`
- `AUTO_PAUSED`
- `DEGRADED`
- `BLOCKED`
- `EMERGENCY_STOPPED`

Rules:

- Deployment is system-owned desired/autonomous lifecycle, not proof of running runtime.
- `AUTO_DEPLOYED` should be accompanied by an aligned `AUTO` runtime unless a mismatch is explicitly reported.
- Non-auto transitions with open risk should retain `EXITS_ONLY` runtime where exits are eligible; otherwise mark `UNMANAGED_OPEN_RISK`.
- `AUTO_DEPLOYABLE` means eligible for autonomous deployment, not necessarily deployed or running.
- `AUTO_DEPLOYED` must still prove runtime alignment.
- `AUTO_PAUSED`, `DEGRADED`, `BLOCKED`, and `EMERGENCY_STOPPED` must preserve open-risk management state.
- Retargeting instrument/profile must not strand open risk on the previous runtime/instrument.
- Deployment transitions must emit domain/audit evidence when material.

Invalid transitions:

- `BLOCKED` or `EMERGENCY_STOPPED` to `AUTO_DEPLOYED` without governance/health/risk recheck.
- `AUTO_DEPLOYED` shown as running without aligned runtime.
- Retargeting from instrument A to instrument B while instrument A has open risk and no exit-capable path.
- Clearing `UNMANAGED_OPEN_RISK` through deployment state change alone.

Required tests:

- `AUTO_DEPLOYABLE` transition use confirmation.
- Deployment/runtime mismatch tests.
- Retargeting with open risk tests.
- Emergency stop/open-risk preservation tests.

## Runtime control and runtime mode

| Field | Value |
| --- | --- |
| Owner service/model | `StrategyService`, `RuntimeRecoveryService`, `runtime_manager`, `StrategyRuntimeState`. |
| Source of truth | Persisted runtime plus in-memory engine. |
| Current verification confidence | High for tested start/stop/recovery cases. |

Control modes:

- `MANUAL`
- `AUTO`

Runtime modes:

- `NORMAL`
- `EXITS_ONLY`
- `STOPPED`

Rules:

- Manual runtime blocks autonomous deployment for the same strategy family.
- Default starts must not silently erase persisted `EXITS_ONLY`.
- `UNMANAGED_OPEN_RISK` blocks normal restart unless explicitly handled.
- Partial fills and rotations with open risk can force `EXITS_ONLY`.
- Control mode and runtime mode are independent dimensions.
- `AUTO` plus `NORMAL` means autonomous runtime may evaluate entries/exits subject to governance/risk/health.
- `AUTO` plus `EXITS_ONLY` means autonomous runtime may manage exits but must not open new entries.
- `MANUAL` plus `NORMAL` must not be represented as autonomous deployment.
- `STOPPED` with open risk must create or preserve recovery/manual-review/unmanaged-risk state.
- Default starts, restarts, and recovery must not silently erase persisted `EXITS_ONLY` or manual-review state.
- Partial fills, partial closes, broker ambiguity, and unmanaged open risk can force `EXITS_ONLY` or `NEEDS_MANUAL_REVIEW`.

Invalid transitions:

- `MANUAL` to `AUTO` caused by `set_runtime_mode` or restart without explicit authority.
- `EXITS_ONLY` to `NORMAL` without risk-resolution evidence.
- `STOPPED` with open risk and no recovery/unmanaged-risk state.
- Runtime start implying governance approval.
- Runtime stop causing loss of exit-capable path for open risk.

Required tests:

- Manual to `AUTO` non-reclassification tests.
- `EXITS_ONLY` preservation on restart.
- `STOPPED` with open risk recovery tests.
- Partial fill forcing restricted runtime tests.
- Frontend display tests for control mode vs runtime mode.

## Open-risk management state machine

| Field | Value |
| --- | --- |
| Owner service/model | `OperationalStateService`, `StrategyDeploymentManagerService`, `RuntimeRecoveryService`, `ReconciliationService`, `StrategyService` where applicable. |
| Source of truth | No single authoritative aggregate exists yet. `StrategyDeployment` persists a management state while operational views derive state from positions, deployments, and runtimes. This is tracked under `AUDIT-ARCH-002`. |
| Current verification confidence | Medium; state is safety-critical and should be audited across runtime/deployment/recovery flows. |

Known states:

- `NO_OPEN_RISK`
- `MANAGED`
- `EXITS_ONLY`
- `UNMANAGED_OPEN_RISK`

Rules:

- `NO_OPEN_RISK` means no known open exposure requiring management.
- `MANAGED` means known open risk has an active management path.
- `EXITS_ONLY` means entries are blocked or restricted while exit/protective handling remains available.
- `UNMANAGED_OPEN_RISK` means known open risk lacks a safe active management path and must be operator-visible.
- `EXITS_ONLY` and `UNMANAGED_OPEN_RISK` must not be cleared by runtime restart, deployment retargeting, emergency stop, or reconciliation without explicit audited transition.
- Entry eligibility must remain blocked while open-risk state requires exits-only or manual review.
- Open-risk state must be shown distinctly from governance approval, deployment state, and runtime status.

Invalid transitions:

- `UNMANAGED_OPEN_RISK` to `MANAGED` without runtime/recovery/operator evidence.
- `EXITS_ONLY` to `NORMAL`/`MANAGED` without explicit risk-resolution evidence.
- `MANAGED` to `NO_OPEN_RISK` without broker/local close or reconciliation evidence.
- Open risk disappearing from operator-visible state without `Position`/`Trade`/`ReconciliationEvent` evidence.

Required tests:

- Tests for `NO_OPEN_RISK`, `MANAGED`, `EXITS_ONLY`, and `UNMANAGED_OPEN_RISK` display and transitions.
- Runtime restart/retargeting tests proving protective state is preserved.
- Reconciliation tests proving open risk cannot disappear silently.
- Frontend tests proving open-risk state is visible and distinct.

## Allocation alert states

| Field | Value |
| --- | --- |
| Owner service/model | `AllocationAlertService`; model `AllocationAlert`. |
| Source of truth | `AllocationAlert.state`. |
| Current verification confidence | High for backend tests. |

Observed states:

- `OPEN`
- `ACKNOWLEDGED`
- `RESOLVED`

Rules:

- Alerts can recur and reopen after resolution.
- Acknowledge/resolve must preserve actor and timestamp.
- Alert refresh can persist changes and must be treated as mutation-like behavior even if currently exposed via GET refresh parameter.
- `OPEN`, `ACKNOWLEDGED`, and `RESOLVED` are alert lifecycle states, not risk-resolution proof by themselves.
- `ACKNOWLEDGED` means operator saw/accepted the alert, not that the underlying condition is resolved.
- `RESOLVED` requires resolution evidence or condition no longer present.
- Alert refresh that writes/reopens alerts is mutation-like even if exposed via GET refresh parameter.
- Recurrence/reopen must preserve previous alert history where practical.

Invalid transitions:

- `ACKNOWLEDGED` to `RESOLVED` without actor/timestamp/resolution evidence.
- `RESOLVED` to `OPEN` without recurrence/reopen evidence.
- Alert state used as direct trading permission.

Required tests:

- Acknowledge actor/timestamp tests.
- Resolve actor/timestamp/reason tests.
- Reopen/recurrence tests.
- GET refresh mutation-like classification tests.

## Position/trade lifecycle

| Entity | Lifecycle |
| --- | --- |
| `Position` | Open exposure starts with broker/simulated fill or reconciliation adoption; `is_open=True` until close/reconciliation marks closed. |
| `Trade` | Created after close is confirmed or forced reconciliation close records realized/out-of-band outcome. |
| `ReconciliationEvent` | Records broker/local mismatch correction, adoption, or forced close. |

Rules:

- `Position` is open-risk authority while `is_open=True`.
- `Trade` is realized outcome evidence and must not represent open exposure.
- `Position` close requires broker confirmation, simulated close evidence, or explicit reconciliation/forced-close evidence.
- Broker-missing local position must not silently delete or close `Position` without `ReconciliationEvent` evidence.
- Unmatched broker position must create recovery/adoption lifecycle evidence.
- Simulated fills/closes must remain distinguishable from broker-confirmed fills/closes.

Invalid transitions:

- `Position is_open=True` to closed without close/reconciliation evidence.
- Open `Position` disappearing without `Trade` or `ReconciliationEvent`.
- `Trade` created for still-open exposure.
- Simulated close displayed as broker-confirmed close.

Required tests:

- Position close evidence tests.
- Broker-missing local position reconciliation tests.
- Unmatched broker position adoption tests.
- Simulated vs broker-confirmed truth tests.

## Health and coverage states

| Domain | Known states | Owner |
| --- | --- | --- |
| Feed source | `LIVE`, `POLLING_FALLBACK`, `STALE`, `DISCONNECTED` | `OperationalStateService` |
| Feed health | `HEALTHY`, `DEGRADED`, `FAILED` | `OperationalStateService` |
| Broker connectivity | `CONNECTED`, `DISCONNECTED` | `OperationalStateService` |
| Execution eligibility | `ALLOWED`, `BLOCKED` | `OperationalStateService` |
| Open risk management | `NO_OPEN_RISK`, `MANAGED`, `EXITS_ONLY`, `UNMANAGED_OPEN_RISK` | `OperationalStateService`/deployment |
| Watchlist tier | `TIER1`, `TIER2`, `TIER3` | `WatchlistEntry` |
| Watchlist status | `ACTIVE`, `COOLDOWN`, `INACTIVE` | `WatchlistEntry` |

Rules:

- `LIVE`, `POLLING_FALLBACK`, `STALE`, and `DISCONNECTED` are distinct and must not be collapsed.
- `POLLING_FALLBACK` must not mark streaming as healthy.
- Price availability must not imply execution eligibility.
- Execution eligibility `ALLOWED`/`BLOCKED` must account for governance, market status, broker connectivity, freshness, risk, and open-risk state.
- Watchlist tier/status must not imply trading approval.
- Tier 1 coverage means streaming priority/coverage, not entry eligibility.

Invalid transitions:

- `POLLING_FALLBACK` to `LIVE` without stream evidence.
- `STALE` to `HEALTHY` without fresh tick or fresh broker-supported fallback evidence.
- `DISCONNECTED` plus price cache shown as live.
- `TIER1` shown as approved to trade.
- `ACTIVE` watchlist shown as runtime running.

Required tests:

- Streaming vs fallback state tests.
- UI degraded-state tests.
- Execution eligibility tests.
- Watchlist tier/status label tests.

## Transition audit evidence

Safety-critical transitions should preserve enough evidence for operator review.

Required evidence may include:

- previous state;
- new state;
- transition owner/service;
- reason;
- triggering input or event;
- related `TradeIntent`, `Execution`, `Position`, `Trade`, deployment, runtime, alert, or reconciliation id;
- broker reference/client request id where applicable;
- timestamp;
- actor or system owner;
- whether the transition was normal, recovery, reconciliation, simulated, manual, or degraded.

P0 transitions must not rely only on logs where durable domain/event evidence is required.

## Must-not-cross state boundaries

| Boundary ID | Boundary | Rule | Required evidence | Severity |
| --- | --- | --- | --- | --- |
| STATE-BND-001 | Decision vs execution | Execution status must not replace `TradeIntent` decision authority. | Decision/execution lifecycle tests. | P0 |
| STATE-BND-002 | State transition authority | Lifecycle states must not change outside owner services or documented recovery/reconciliation workflows. | Code review and transition tests. | P0 |
| STATE-BND-003 | Terminal state protection | Terminal states must not silently reactivate. | Transition table tests. | P0 |
| STATE-BND-004 | Manual vs AUTO ownership | Runtime ownership must not be silently reclassified. | Runtime/control-plane tests. | P1 |
| STATE-BND-005 | Deployment vs runtime | Deployment state must not imply runtime alignment. | Alignment/mismatch tests. | P1 |
| STATE-BND-006 | Open-risk ownership | Open risk must not become invisible or unmanaged without explicit state/event evidence. | Recovery/close-failure/unmanaged-risk tests. | P0 |
| STATE-BND-007 | Broker ambiguity | Ambiguous broker outcomes must not become exact lifecycle truth silently. | Broker failure/manual-review tests. | P0 |
| STATE-BND-008 | Frontend enum parity | UI must not collapse missing/unknown backend states into healthy/default labels. | Frontend enum tests. | P1 |
| STATE-BND-009 | Streaming/fallback truth | Fallback polling must not be represented as healthy live streaming. | Market-data/UI tests. | P1 |

## Known unknowns

- Some state machines are implicit in service code rather than centralized transition tables.
- Frontend `ExecutionStatus` includes `SUBMISSION_PENDING`; parity tests cover the reviewed state family.
- `AUTO_DEPLOYABLE` appears in enum but current transition use needs confirmation.
- Transition authority is not centrally enforced for every state machine.
- Some lifecycle transitions may happen through direct field assignment in services rather than explicit transition helpers.
- Broker ambiguity states may not be represented centrally across `TradeIntent`, `Execution`, `Position`, and reconciliation records.
- Open-risk management state does not yet have a single versioned persistence source of truth (`AUDIT-ARCH-002`).
- Frontend enum coverage may be incomplete beyond `Execution.SUBMISSION_PENDING`.
- `AUTO_DEPLOYABLE` transition semantics need confirmation.
- Manual-review and reconciliation-needed states may not be consistently represented across execution, runtime, deployment, and UI.
- Simulated/local fills and closes may not be consistently distinguishable from broker-confirmed truth in all read models.
- Health/coverage states may be derived differently across backend services and frontend summaries.

## Required tests

- Transition matrix tests for `TradeIntent` and `Execution` covering valid and invalid transitions.
- Tests proving lifecycle states are changed only through owner services or documented recovery/reconciliation workflows.
- Tests proving terminal states cannot reactivate without new lifecycle/audit evidence.
- Tests proving broker timeout, confirmation failure, rate limit, partial fill, partial close, and ambiguous outcome produce pending/manual-review/reconciliation-needed/degraded state.
- Tests proving manual runtime cannot be silently reclassified as `AUTO`.
- Tests proving deployment state cannot be displayed as runtime alignment without explicit alignment checks.
- Tests proving `EXITS_ONLY`, emergency stop, manual-review, unmanaged-open-risk, and protective-exit states survive restart/retarget/reconciliation unless explicitly transitioned with audit evidence.
- Tests proving open-risk management states `NO_OPEN_RISK`, `MANAGED`, `EXITS_ONLY`, and `UNMANAGED_OPEN_RISK` are visible and transition safely.
- Tests proving alert acknowledge/resolve/reopen preserves actor/timestamp/reason evidence.
- Tests proving `Position` close requires broker/simulated/reconciliation evidence.
- Tests proving recovery/adoption states remain distinguishable from normal strategy-owned lifecycle.
- Tests proving frontend enums and labels cover all backend states or render unknown/unsupported states safely.
- Tests proving fallback polling does not become healthy live stream state.

## Audit questions for Codex

- Which state fields can be changed by direct assignment outside owner services?
- Is there a central transition helper/table for `TradeIntent` and `Execution`, or are transitions implicit across services?
- Can any rejected `TradeIntent` lead to broker submission?
- Can any `Execution` legacy risk state be written by new code?
- Can terminal `TradeIntent`, `Execution`, `Position`, `Trade`, deployment, runtime, or alert states reactivate silently?
- Can broker timeout, rate limit, partial fill, partial close, unknown response, or confirmation lookup failure become exact success/failure without manual-review or reconciliation evidence?
- Can `set_runtime_mode`, restart, recovery, or retargeting silently change `MANUAL` to `AUTO`?
- Can `EXITS_ONLY`, emergency stop, manual-review, unmanaged-open-risk, or protective-exit state be cleared by restart/reconcile/deployment transition alone?
- Can governance approval be shown as deployment, runtime, or entry eligibility?
- Can `AUTO_DEPLOYED` be shown as running without explicit runtime alignment?
- Can open risk disappear from `Position`/control-plane/UI without `Trade` or `ReconciliationEvent` evidence?
- Can simulated fills/closes be displayed as broker-confirmed truth?
- Are all backend states represented in frontend types and labels, including `SUBMISSION_PENDING`?
- What happens in the UI when an unknown backend state is returned?
