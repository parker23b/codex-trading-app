from __future__ import annotations

from dataclasses import dataclass

from app.models.trade import ExecutionStatus, TradeIntentState


TRADE_INTENT_TERMINAL_STATES = frozenset(
    {
        TradeIntentState.REJECTED,
        TradeIntentState.CLOSED,
        TradeIntentState.FAILED,
        TradeIntentState.CANCELLED,
        TradeIntentState.FORCED_RECONCILIATION_CLOSE,
    }
)

TRADE_INTENT_TRANSITIONS: dict[TradeIntentState, frozenset[TradeIntentState]] = {
    TradeIntentState.PROPOSED: frozenset(
        {
            TradeIntentState.APPROVED,
            TradeIntentState.REJECTED,
        }
    ),
    TradeIntentState.REJECTED: frozenset({TradeIntentState.REJECTED}),
    TradeIntentState.APPROVED: frozenset(
        {
            TradeIntentState.APPROVED,
            TradeIntentState.SUBMITTED,
            TradeIntentState.FAILED,
        }
    ),
    TradeIntentState.SUBMITTED: frozenset(
        {
            TradeIntentState.ACKNOWLEDGED,
            TradeIntentState.FAILED,
            TradeIntentState.CANCELLED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.ACKNOWLEDGED: frozenset(
        {
            TradeIntentState.ACKNOWLEDGED,
            TradeIntentState.FILLED,
            TradeIntentState.PARTIALLY_FILLED,
            TradeIntentState.POSITION_OPENED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FAILED,
            TradeIntentState.CANCELLED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.PARTIALLY_FILLED: frozenset(
        {
            TradeIntentState.PARTIALLY_FILLED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.FILLED: frozenset(
        {
            TradeIntentState.POSITION_OPENED,
            TradeIntentState.CLOSED,
        }
    ),
    TradeIntentState.POSITION_OPENED: frozenset(
        {
            TradeIntentState.POSITION_OPENED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.CLOSE_REQUESTED: frozenset(
        {
            TradeIntentState.SUBMITTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.CLOSED: frozenset({TradeIntentState.CLOSED}),
    TradeIntentState.FAILED: frozenset({TradeIntentState.FAILED}),
    TradeIntentState.CANCELLED: frozenset({TradeIntentState.CANCELLED}),
    TradeIntentState.EXTERNAL_POSITION_ADOPTED: frozenset(
        {
            TradeIntentState.EXTERNAL_POSITION_ADOPTED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.RECOVERED_POSITION_ATTACHED: frozenset(
        {
            TradeIntentState.RECOVERED_POSITION_ATTACHED,
            TradeIntentState.CLOSE_REQUESTED,
            TradeIntentState.FORCED_RECONCILIATION_CLOSE,
        }
    ),
    TradeIntentState.FORCED_RECONCILIATION_CLOSE: frozenset(
        {TradeIntentState.FORCED_RECONCILIATION_CLOSE}
    ),
}

TRADE_INTENT_IDEMPOTENT_STATES = frozenset(
    state for state, targets in TRADE_INTENT_TRANSITIONS.items() if state in targets
)
TRADE_INTENT_PROVENANCE_STATES = frozenset(
    {
        TradeIntentState.EXTERNAL_POSITION_ADOPTED,
        TradeIntentState.RECOVERED_POSITION_ATTACHED,
    }
)


EXECUTION_LEGACY_COMPATIBILITY_STATUSES = frozenset(
    {
        ExecutionStatus.SIGNAL_GENERATED,
        ExecutionStatus.RISK_APPROVED,
        ExecutionStatus.RISK_REJECTED,
        ExecutionStatus.CLOSE_REQUESTED,
    }
)

EXECUTION_TERMINAL_STATUSES = frozenset(
    {
        ExecutionStatus.POSITION_OPENED,
        ExecutionStatus.CLOSE_CONFIRMED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)

EXECUTION_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.SUBMISSION_PENDING: frozenset(
        {
            ExecutionStatus.SUBMISSION_PENDING,
            ExecutionStatus.ORDER_SUBMITTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.NEEDS_MANUAL_REVIEW,
        }
    ),
    ExecutionStatus.SIGNAL_GENERATED: frozenset(),
    ExecutionStatus.RISK_APPROVED: frozenset(),
    ExecutionStatus.RISK_REJECTED: frozenset(),
    ExecutionStatus.ORDER_SUBMITTED: frozenset(
        {
            ExecutionStatus.ORDER_ACKNOWLEDGED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.NEEDS_MANUAL_REVIEW,
        }
    ),
    ExecutionStatus.ORDER_ACKNOWLEDGED: frozenset(
        {
            ExecutionStatus.FILL_PARTIAL,
            ExecutionStatus.FILL_FULL,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.NEEDS_MANUAL_REVIEW,
        }
    ),
    ExecutionStatus.FILL_PARTIAL: frozenset(
        {
            ExecutionStatus.NEEDS_MANUAL_REVIEW,
        }
    ),
    ExecutionStatus.FILL_FULL: frozenset(
        {
            ExecutionStatus.POSITION_OPENED,
            ExecutionStatus.CLOSE_CONFIRMED,
        }
    ),
    ExecutionStatus.POSITION_OPENED: frozenset({ExecutionStatus.POSITION_OPENED}),
    ExecutionStatus.CLOSE_REQUESTED: frozenset(),
    ExecutionStatus.CLOSE_CONFIRMED: frozenset({ExecutionStatus.CLOSE_CONFIRMED}),
    ExecutionStatus.FAILED: frozenset({ExecutionStatus.FAILED}),
    ExecutionStatus.CANCELLED: frozenset({ExecutionStatus.CANCELLED}),
    ExecutionStatus.NEEDS_MANUAL_REVIEW: frozenset(
        {
            ExecutionStatus.POSITION_OPENED,
        }
    ),
}

EXECUTION_IDEMPOTENT_STATUSES = frozenset(
    status for status, targets in EXECUTION_TRANSITIONS.items() if status in targets
)


@dataclass(slots=True)
class LifecycleTransitionError(ValueError):
    entity_name: str
    current_state: str
    target_state: str
    allowed_targets: tuple[str, ...]
    reason: str

    def __str__(self) -> str:
        allowed = ", ".join(self.allowed_targets) or "none"
        return (
            f"{self.entity_name} cannot transition from {self.current_state} to "
            f"{self.target_state}: {self.reason}. Allowed targets: {allowed}."
        )


@dataclass(slots=True)
class LegacyLifecycleWriteError(ValueError):
    entity_name: str
    target_state: str

    def __str__(self) -> str:
        return (
            f"{self.entity_name} status {self.target_state} is compatibility-only "
            "and cannot be written by current code."
        )


def parse_trade_intent_state(value: TradeIntentState | str) -> TradeIntentState:
    if isinstance(value, TradeIntentState):
        return value
    try:
        return TradeIntentState(value)
    except ValueError as exc:
        allowed = ", ".join(state.value for state in TradeIntentState)
        raise ValueError(
            f"Unknown TradeIntent state {value}. Allowed states: {allowed}."
        ) from exc


def parse_execution_status(value: ExecutionStatus | str) -> ExecutionStatus:
    if isinstance(value, ExecutionStatus):
        return value
    try:
        return ExecutionStatus(value)
    except ValueError as exc:
        allowed = ", ".join(status.value for status in ExecutionStatus)
        raise ValueError(
            f"Unknown Execution status {value}. Allowed statuses: {allowed}."
        ) from exc


def validate_trade_intent_transition(
    *, current_state: TradeIntentState | str, target_state: TradeIntentState | str
) -> TradeIntentState:
    current = parse_trade_intent_state(current_state)
    target = parse_trade_intent_state(target_state)
    allowed = TRADE_INTENT_TRANSITIONS[current]
    if target not in allowed:
        reason = (
            "terminal trade intents cannot reactivate"
            if current in TRADE_INTENT_TERMINAL_STATES
            else "transition is not classified as valid"
        )
        raise LifecycleTransitionError(
            entity_name="TradeIntent",
            current_state=current.value,
            target_state=target.value,
            allowed_targets=tuple(state.value for state in sorted(allowed, key=str)),
            reason=reason,
        )
    return target


def validate_new_execution_status(
    target_status: ExecutionStatus | str,
) -> ExecutionStatus:
    target = parse_execution_status(target_status)
    if target in EXECUTION_LEGACY_COMPATIBILITY_STATUSES:
        raise LegacyLifecycleWriteError(
            entity_name="Execution",
            target_state=target.value,
        )
    return target


def validate_execution_transition(
    *, current_status: ExecutionStatus | str, target_status: ExecutionStatus | str
) -> ExecutionStatus:
    current = parse_execution_status(current_status)
    target = validate_new_execution_status(target_status)
    allowed = EXECUTION_TRANSITIONS[current]
    if target not in allowed:
        reason = (
            "terminal execution attempts cannot reactivate"
            if current in EXECUTION_TERMINAL_STATUSES
            else "transition is not classified as valid"
        )
        raise LifecycleTransitionError(
            entity_name="Execution",
            current_state=current.value,
            target_state=target.value,
            allowed_targets=tuple(status.value for status in sorted(allowed, key=str)),
            reason=reason,
        )
    return target
