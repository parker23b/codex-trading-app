from __future__ import annotations

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.models.trade import (
    ExecutionStatus,
    Position,
    Trade,
    TradeIntent,
    TradeIntentState,
    clone_position,
    utc_now,
)
from app.strategies.registry import strategy_registry
from app.services.audit_event_recorder import record_required_domain_event
from app.services.health_service import get_health_service
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class ReconciliationService:
    """
    Synchronize local open positions against broker truth.

    Reconciliation is no longer allowed to silently mutate portfolio truth.
    If broker state appears without an internal lifecycle chain, this service
    creates explicit TradeIntent records such as `EXTERNAL_POSITION_ADOPTED` or
    `FORCED_RECONCILIATION_CLOSE` so operators can audit the out-of-band path.
    """

    def __init__(self, trade_service: TradeService):
        self.trade_service = trade_service
        self.broker = get_broker()
        self.runtime_state_service = RuntimeStateService(trade_service.session)

    def reconcile_open_positions(self) -> list[Position]:
        adopted_count = 0
        corrected_count = 0
        unmatched_local_count = 0
        remote_positions = self.broker.get_positions()
        local_positions = self.trade_service.list_all_open_positions()
        local_by_broker_reference = {
            position.broker_reference: position
            for position in local_positions
            if position.broker_reference
        }
        local_by_runtime_key = {
            (position.strategy_name, position.instrument): position
            for position in local_positions
        }
        local_by_instrument: dict[str, list[Position]] = {}
        for position in local_positions:
            local_by_instrument.setdefault(position.instrument, []).append(position)
        remote_by_broker_reference = {
            position.broker_reference: position for position in remote_positions
        }

        for remote_position in remote_positions:
            instrument = remote_position.instrument
            runtime_engines = runtime_manager.get_engines_for_instrument(instrument)
            local_position = local_by_broker_reference.get(
                remote_position.broker_reference
            )
            correlated_intent = None
            if local_position is None:
                correlated_intent = (
                    self.trade_service.find_active_trade_intent_by_broker_reference(
                        instrument=instrument,
                        broker_reference=remote_position.broker_reference,
                    )
                )
            matching_engine = next(
                (
                    engine
                    for _, engine in runtime_engines
                    if engine.current_position is not None
                    and engine.current_position.broker_reference
                    == remote_position.broker_reference
                ),
                None,
            )
            if (
                local_position is None
                and matching_engine is None
                and len(runtime_engines) == 1
            ):
                local_position = next(
                    iter(local_by_instrument.get(instrument, [])), None
                )

            if local_position is not None:
                mapped_engine = runtime_manager.get_engine(
                    local_position.strategy_name, instrument
                )
                if mapped_engine is not None:
                    matching_engine = mapped_engine

            strategy_name = (
                local_position.strategy_name
                if local_position
                else (
                    correlated_intent.strategy_name
                    if correlated_intent is not None
                    else (
                        matching_engine.strategy.name
                        if matching_engine
                        else "broker_sync"
                    )
                )
            )
            family_name = (
                local_position.family_name
                if local_position is not None
                else correlated_intent.family_name
                if correlated_intent is not None
                else (
                    strategy_registry.get_metadata(strategy_name).family_name
                    or strategy_name
                    if strategy_name != "broker_sync"
                    else "broker_sync"
                )
            )
            persisted_id = local_position.id if local_position else None
            if persisted_id is None:
                runtime_position = local_by_runtime_key.get((strategy_name, instrument))
                if (
                    runtime_position is not None
                    and runtime_position.broker_reference is None
                ):
                    persisted_id = runtime_position.id
            runtime_manager.last_prices.setdefault(
                instrument, remote_position.open_price
            )
            synced_position = Position(
                id=persisted_id,
                trade_intent_id=local_position.trade_intent_id
                if local_position is not None
                else correlated_intent.id
                if correlated_intent is not None
                else None,
                strategy_name=strategy_name,
                family_name=family_name,
                broker_reference=remote_position.broker_reference,
                instrument=remote_position.instrument,
                direction=remote_position.direction.value,
                size=remote_position.size,
                open_price=remote_position.open_price,
                open_time=remote_position.opened_at,
                current_price=runtime_manager.get_last_price(instrument)
                or remote_position.open_price,
                unrealized_pnl=0.0,
                risk_percent=local_position.risk_percent if local_position else None,
                risk_truth_confidence=(
                    local_position.risk_truth_confidence
                    if local_position is not None
                    else "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
                ),
                reason=local_position.reason
                if local_position
                else "Reconciled from broker",
                manual_override=local_position.manual_override
                if local_position
                else False,
                account_type=self.broker.account_type.value,
                is_open=True,
                broker_sync_status="CONFIRMED",
                broker_open_confirmed_at=remote_position.opened_at,
                last_reconciled_at=utc_now(),
            )
            is_adopted = local_position is None and correlated_intent is None
            needs_update = is_adopted or self._position_needs_reconciliation(
                local_position, synced_position
            )
            persisted = self.trade_service.record_broker_position(synced_position)
            intent = self._resolve_reconciled_trade_intent(
                local_position=local_position,
                correlated_intent=correlated_intent,
                persisted_position=persisted,
                matching_engine=matching_engine,
                is_adopted=is_adopted,
            )
            if intent is not None and persisted.trade_intent_id != intent.id:
                persisted.trade_intent_id = intent.id
                persisted = self.trade_service.upsert_position(persisted)
            if needs_update:
                details = {
                    "trade_intent_id": intent.id if intent is not None else None,
                    "matched_local_position": local_position is not None,
                    "matched_ambiguous_intent": correlated_intent is not None,
                    "matched_runtime_engine": matching_engine is not None,
                    "execution_client_request_id": (
                        intent.execution_client_request_id
                        if intent is not None
                        else None
                    ),
                    "size": remote_position.size,
                    "open_price": remote_position.open_price,
                }
                self.trade_service.record_reconciliation_event(
                    event_type="POSITION_SYNCED_FROM_BROKER"
                    if not is_adopted
                    else "POSITION_ADOPTED_FROM_BROKER",
                    trade_intent_id=intent.id if intent is not None else None,
                    strategy_name=strategy_name,
                    instrument=instrument,
                    broker_reference=remote_position.broker_reference,
                    local_position_id=persisted.id,
                    details=details,
                )
                if correlated_intent is not None:
                    self._resolve_reconciled_execution(
                        intent=intent,
                        persisted_position=persisted,
                        details=details,
                    )
                if is_adopted:
                    correlated_execution = self._linked_execution_for_intent(intent)
                    adopted_count += 1
                    self._record_required_reconciliation_event(
                        event_type="reconciliation.unmatched_remote_position",
                        severity="warning",
                        title="Broker position had no local match",
                        message=f"Broker position for {instrument} was adopted into local state.",
                        strategy_name=strategy_name,
                        instrument=instrument,
                        position_id=persisted.id,
                        correlation_id=(
                            intent.execution_client_request_id
                            if intent is not None
                            else None
                        ),
                        trade_id=intent.trade_id if intent is not None else None,
                        execution_id=(
                            correlated_execution.id
                            if correlated_execution is not None
                            else None
                        ),
                        payload_json={
                            **details,
                            "broker_reference": remote_position.broker_reference,
                            "execution_id": (
                                correlated_execution.id
                                if correlated_execution is not None
                                else None
                            ),
                            "execution_client_request_id": (
                                intent.execution_client_request_id
                                if intent is not None
                                else None
                            ),
                            "trade_id": intent.trade_id if intent is not None else None,
                            "allocation_cycle_id": (
                                intent.allocation_cycle_id
                                if intent is not None
                                else None
                            ),
                            "previous_state": "BROKER_ONLY",
                            "new_state": "LOCAL_POSITION_ADOPTED",
                        },
                    )
                else:
                    correlated_execution = self._linked_execution_for_intent(intent)
                    corrected_count += 1
                    self._record_required_reconciliation_event(
                        event_type="reconciliation.position_corrected",
                        severity="info",
                        title="Local position corrected from broker state",
                        message=f"Local position for {instrument} was updated to broker truth.",
                        strategy_name=strategy_name,
                        instrument=instrument,
                        position_id=persisted.id,
                        correlation_id=(
                            intent.execution_client_request_id
                            if intent is not None
                            else None
                        ),
                        trade_id=intent.trade_id if intent is not None else None,
                        execution_id=(
                            correlated_execution.id
                            if correlated_execution is not None
                            else None
                        ),
                        payload_json={
                            **details,
                            "broker_reference": remote_position.broker_reference,
                            "execution_id": (
                                correlated_execution.id
                                if correlated_execution is not None
                                else None
                            ),
                            "execution_client_request_id": (
                                intent.execution_client_request_id
                                if intent is not None
                                else None
                            ),
                            "trade_id": intent.trade_id if intent is not None else None,
                            "allocation_cycle_id": (
                                intent.allocation_cycle_id
                                if intent is not None
                                else None
                            ),
                            "previous_state": "LOCAL_POSITION_STALE",
                            "new_state": "LOCAL_POSITION_BROKER_CONFIRMED",
                        },
                    )
            if matching_engine is not None:
                matching_engine.current_position = clone_position(persisted)
                self.runtime_state_service.sync_engine_state(
                    strategy_name=matching_engine.strategy.name,
                    instrument=matching_engine.instrument,
                    status="RUNNING",
                    recovery_state="RUNNING",
                    last_price_seen=runtime_manager.get_last_price(instrument)
                    or remote_position.open_price,
                    last_price_seen_at=runtime_manager.get_last_price_updated_at(
                        instrument
                    ),
                    current_position=persisted,
                    current_position_broker_reference=persisted.broker_reference,
                )

        for local_position in local_positions:
            if (
                local_position.broker_reference
                and local_position.broker_reference in remote_by_broker_reference
            ):
                continue
            if local_position.broker_reference is None and any(
                remote_position.instrument == local_position.instrument
                for remote_position in remote_positions
            ):
                continue
            self.trade_service.close_position(
                local_position,
                close_price=local_position.current_price or local_position.open_price,
                close_time=utc_now(),
                pnl=local_position.unrealized_pnl,
                broker_sync_status="MISSING_AT_BROKER",
                close_reason="Closed locally after broker reconciliation found no matching open broker position.",
            )
            intent = self._resolve_forced_close_trade_intent(local_position)
            forced_trade = self.trade_service.record_trade(
                Trade(
                    trade_intent_id=intent.id if intent is not None else None,
                    strategy_name=local_position.strategy_name,
                    family_name=local_position.family_name,
                    broker_reference=local_position.broker_reference,
                    close_broker_reference=None,
                    instrument=local_position.instrument,
                    direction=local_position.direction,
                    size=local_position.size,
                    open_price=local_position.open_price,
                    close_price=local_position.current_price
                    or local_position.open_price,
                    open_time=local_position.open_time,
                    close_time=local_position.close_time or utc_now(),
                    pnl=local_position.unrealized_pnl or local_position.pnl or 0.0,
                    entry_risk_amount=local_position.entry_risk_amount,
                    risk_truth_confidence=local_position.risk_truth_confidence,
                    outcome="reconciled",
                    reason="Forced reconciliation close",
                    account_type=local_position.account_type,
                )
            )
            if intent is not None:
                self.trade_service.transition_trade_intent(
                    intent,
                    state=TradeIntentState.FORCED_RECONCILIATION_CLOSE,
                    trade_id=forced_trade.id,
                    position_id=local_position.id,
                    close_reason_code="FORCED_RECONCILIATION_CLOSE",
                    close_reason="Local position was force-closed because the broker no longer reported it.",
                    average_fill_price=forced_trade.close_price,
                    filled_size=forced_trade.size,
                    completed_at=forced_trade.close_time,
                    closed_at=forced_trade.close_time,
                )
            correlated_execution = self._linked_execution_for_intent(intent)
            unmatched_local_count += 1
            details = {
                "trade_intent_id": intent.id if intent is not None else None,
                "had_broker_reference": local_position.broker_reference is not None,
                "close_price": local_position.current_price
                or local_position.open_price,
                "forced_trade_id": forced_trade.id,
                "previous_state": "LOCAL_POSITION_OPEN",
                "new_state": "LOCAL_POSITION_FORCED_CLOSED",
            }
            self.trade_service.record_reconciliation_event(
                event_type="LOCAL_POSITION_CLOSED_AFTER_BROKER_MISS",
                trade_intent_id=intent.id if intent is not None else None,
                strategy_name=local_position.strategy_name,
                instrument=local_position.instrument,
                broker_reference=local_position.broker_reference,
                local_position_id=local_position.id,
                details=details,
            )
            self._record_required_reconciliation_event(
                event_type="reconciliation.unmatched_local_position",
                severity="warning",
                title="Local position missing at broker",
                message=f"Local position for {local_position.instrument} was not found remotely and was closed.",
                strategy_name=local_position.strategy_name,
                instrument=local_position.instrument,
                position_id=local_position.id,
                correlation_id=(
                    intent.execution_client_request_id if intent is not None else None
                ),
                trade_id=forced_trade.id,
                execution_id=(
                    correlated_execution.id
                    if correlated_execution is not None
                    else None
                ),
                payload_json={
                    **details,
                    "broker_reference": local_position.broker_reference,
                    "execution_client_request_id": (
                        intent.execution_client_request_id
                        if intent is not None
                        else None
                    ),
                    "execution_id": (
                        correlated_execution.id
                        if correlated_execution is not None
                        else None
                    ),
                    "trade_id": forced_trade.id,
                    "allocation_cycle_id": (
                        intent.allocation_cycle_id if intent is not None else None
                    ),
                },
            )
            self._record_required_reconciliation_event(
                event_type="reconciliation.position_corrected",
                severity="info",
                title="Position corrected after reconciliation",
                message=f"Reconciliation closed a mismatched local position for {local_position.instrument}.",
                strategy_name=local_position.strategy_name,
                instrument=local_position.instrument,
                position_id=local_position.id,
                correlation_id=(
                    intent.execution_client_request_id if intent is not None else None
                ),
                trade_id=forced_trade.id,
                execution_id=(
                    correlated_execution.id
                    if correlated_execution is not None
                    else None
                ),
                payload_json={
                    **details,
                    "broker_reference": local_position.broker_reference,
                    "execution_client_request_id": (
                        intent.execution_client_request_id
                        if intent is not None
                        else None
                    ),
                    "execution_id": (
                        correlated_execution.id
                        if correlated_execution is not None
                        else None
                    ),
                    "trade_id": forced_trade.id,
                    "allocation_cycle_id": (
                        intent.allocation_cycle_id if intent is not None else None
                    ),
                    "correction": "closed_local_position",
                },
            )
            runtime_engine = runtime_manager.get_engine(
                local_position.strategy_name, local_position.instrument
            )
            if (
                runtime_engine is not None
                and runtime_engine.current_position is not None
                and (
                    runtime_engine.current_position.broker_reference
                    == local_position.broker_reference
                    or (
                        runtime_engine.current_position.broker_reference is None
                        and local_position.broker_reference is None
                    )
                )
            ):
                runtime_engine.current_position = None
                self.runtime_state_service.mark_recovery_state(
                    strategy_name=runtime_engine.strategy.name,
                    instrument=runtime_engine.instrument,
                    recovery_state="RUNNING",
                    recovery_reason=None,
                    current_position_broker_reference=None,
                )

        changed_count = adopted_count + corrected_count + unmatched_local_count
        get_health_service().record_reconciliation(
            mismatches=changed_count, when=utc_now()
        )
        log_level = logger.info if changed_count else logger.debug
        log_level(
            "Broker reconciliation complete",
            extra={
                "remote_positions": len(remote_positions),
                "local_positions": len(local_positions),
                "adopted_positions": adopted_count,
                "corrected_positions": corrected_count,
                "closed_unmatched_local_positions": unmatched_local_count,
                "event": "reconciliation_completed",
            },
        )
        return self.trade_service.list_positions()

    def _record_required_reconciliation_event(
        self,
        *,
        event_type: str,
        severity: str,
        title: str,
        message: str,
        strategy_name: str,
        instrument: str,
        position_id: int | None,
        correlation_id: str | None = None,
        trade_id: int | None = None,
        execution_id: int | None = None,
        payload_json: dict[str, object],
    ) -> None:
        record_required_domain_event(
            session=self.trade_service.session,
            event_type=event_type,
            category="reconciliation",
            severity=severity,
            source="reconciliation_service.reconcile_open_positions",
            title=title,
            message=message,
            correlation_id=correlation_id,
            strategy_name=strategy_name,
            instrument=instrument,
            position_id=position_id,
            trade_id=trade_id,
            execution_id=execution_id,
            actor_type="service",
            actor_id="reconciliation_service",
            payload_json=payload_json,
        )

    def _linked_execution_for_intent(self, intent: TradeIntent | None):
        if intent is None or intent.execution_client_request_id is None:
            return None
        return self.trade_service.find_execution_by_client_request_id(
            intent.execution_client_request_id
        )

    @staticmethod
    def _position_needs_reconciliation(
        local_position: Position | None, remote_position: Position
    ) -> bool:
        if local_position is None:
            return True
        return any(
            (
                local_position.broker_reference != remote_position.broker_reference,
                local_position.direction != remote_position.direction,
                float(local_position.size) != float(remote_position.size),
                float(local_position.open_price) != float(remote_position.open_price),
                local_position.broker_sync_status != "CONFIRMED",
            )
        )

    def _resolve_reconciled_trade_intent(
        self,
        *,
        local_position: Position | None,
        correlated_intent: TradeIntent | None,
        persisted_position: Position,
        matching_engine,
        is_adopted: bool,
    ) -> TradeIntent | None:
        if correlated_intent is not None:
            return self.trade_service.transition_trade_intent(
                correlated_intent,
                state=TradeIntentState.POSITION_OPENED,
                broker_reference=persisted_position.broker_reference,
                position_id=persisted_position.id,
                risk_truth_confidence=(
                    persisted_position.risk_truth_confidence
                    or "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
                ),
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                opened_at=persisted_position.open_time,
                details={
                    "reconciliation_linked_ambiguous_entry": True,
                    "reconciled_broker_reference": persisted_position.broker_reference,
                    "reconciled_position_id": persisted_position.id,
                },
            )
        if local_position is not None and local_position.trade_intent_id is not None:
            intent = self.trade_service.get_trade_intent(local_position.trade_intent_id)
            if intent is not None:
                return self.trade_service.transition_trade_intent(
                    intent,
                    state=(
                        TradeIntentState.EXTERNAL_POSITION_ADOPTED
                        if is_adopted
                        else TradeIntentState.POSITION_OPENED
                    ),
                    broker_reference=persisted_position.broker_reference,
                    position_id=persisted_position.id,
                    risk_truth_confidence=(
                        persisted_position.risk_truth_confidence
                        or "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
                    ),
                    average_fill_price=persisted_position.open_price,
                    filled_size=persisted_position.size,
                    opened_at=persisted_position.open_time,
                    decision_reason_code=(
                        "UNPLANNED_POSITION_DETECTED"
                        if is_adopted
                        else intent.decision_reason_code
                    ),
                    decision_reason=(
                        "Broker position was adopted without an existing internal decision chain."
                        if is_adopted
                        else intent.decision_reason
                    ),
                )

        strategy_name = (
            local_position.strategy_name
            if local_position is not None
            else (
                matching_engine.strategy.name
                if matching_engine is not None
                else "broker_sync"
            )
        )
        intent = self.trade_service.create_trade_intent(
            TradeIntent(
                strategy_name=strategy_name,
                family_name=(
                    persisted_position.family_name
                    or (
                        strategy_registry.get_metadata(strategy_name).family_name
                        or strategy_name
                        if strategy_name != "broker_sync"
                        else "broker_sync"
                    )
                ),
                instrument=persisted_position.instrument,
                direction=persisted_position.direction,
                state=(
                    TradeIntentState.EXTERNAL_POSITION_ADOPTED.value
                    if is_adopted
                    else TradeIntentState.POSITION_OPENED.value
                ),
                signal_time=persisted_position.open_time,
                proposed_size=persisted_position.size,
                allocated_size=persisted_position.size,
                proposed_risk_percent=persisted_position.risk_percent,
                allocated_risk_percent=persisted_position.risk_percent,
                risk_truth_confidence=(
                    persisted_position.risk_truth_confidence
                    or "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
                ),
                observed_price=persisted_position.open_price,
                average_fill_price=persisted_position.open_price,
                filled_size=persisted_position.size,
                broker_reference=persisted_position.broker_reference,
                position_id=persisted_position.id,
                decision_reason_code=(
                    "UNPLANNED_POSITION_DETECTED"
                    if is_adopted
                    else "RECOVERED_POSITION_LINK"
                ),
                decision_reason=(
                    "Broker position was adopted without an existing internal decision chain."
                    if is_adopted
                    else "Reconciliation created an explicit lifecycle record for a legacy position."
                ),
                opened_at=persisted_position.open_time,
                details={"reconciliation_created": True},
            )
        )
        return intent

    def _resolve_reconciled_execution(
        self,
        *,
        intent: TradeIntent | None,
        persisted_position: Position,
        details: dict[str, object],
    ) -> None:
        if intent is None or intent.execution_client_request_id is None:
            return
        execution = self.trade_service.find_execution_by_client_request_id(
            intent.execution_client_request_id
        )
        if execution is None:
            return
        self.trade_service.transition_execution(
            execution,
            status=ExecutionStatus.POSITION_OPENED,
            trade_intent_id=intent.id,
            client_request_id=execution.client_request_id,
            broker_reference=persisted_position.broker_reference,
            local_position_id=persisted_position.id,
            completed_at=persisted_position.open_time,
            filled_size=persisted_position.size,
            average_fill_price=persisted_position.open_price,
            reason="Broker reconciliation linked ambiguous entry to an open position.",
            requires_manual_review=False,
            risk_truth_confidence=(
                persisted_position.risk_truth_confidence
                or "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
            ),
            details={
                **details,
                "reconciliation_linked_open_position": True,
                "reconciled_broker_reference": persisted_position.broker_reference,
                "reconciled_position_id": persisted_position.id,
            },
        )

    def _resolve_forced_close_trade_intent(
        self, local_position: Position
    ) -> TradeIntent | None:
        if local_position.trade_intent_id is not None:
            intent = self.trade_service.get_trade_intent(local_position.trade_intent_id)
            if intent is not None:
                return intent
        if local_position.broker_reference is not None:
            intent = self.trade_service.find_open_trade_intent(
                strategy_name=local_position.strategy_name,
                instrument=local_position.instrument,
                broker_reference=local_position.broker_reference,
                position_id=local_position.id,
            )
            if intent is not None:
                return intent
        return self.trade_service.create_trade_intent(
            TradeIntent(
                strategy_name=local_position.strategy_name,
                family_name=local_position.family_name,
                instrument=local_position.instrument,
                direction=local_position.direction,
                state=TradeIntentState.FORCED_RECONCILIATION_CLOSE.value,
                signal_time=local_position.open_time,
                proposed_size=local_position.size,
                allocated_size=local_position.size,
                proposed_risk_percent=local_position.risk_percent,
                allocated_risk_percent=local_position.risk_percent,
                observed_price=local_position.open_price,
                broker_reference=local_position.broker_reference,
                position_id=local_position.id,
                decision_reason_code="UNPLANNED_POSITION_DETECTED",
                decision_reason="Reconciliation created a lifecycle record for a position missing an intent chain.",
                details={"reconciliation_created": True, "forced_close": True},
                opened_at=local_position.open_time,
            )
        )
