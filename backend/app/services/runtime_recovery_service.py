from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.models.trade import Position, TradeIntent, TradeIntentState, clone_position, utc_now
from app.strategies.registry import strategy_registry
from app.services.domain_event_service import domain_event_service
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class RuntimeRecoveryService:
    def __init__(self, session: Session):
        self.session = session
        self.trade_service = TradeService(session)
        self.runtime_state_service = RuntimeStateService(session)
        self.broker = get_broker()

    def recover(self) -> list[dict[str, str]]:
        runtimes = self.runtime_state_service.list_active_runtimes()
        local_positions = self.trade_service.list_all_open_positions()
        local_by_key = {(position.strategy_name, position.instrument): position for position in local_positions}
        local_by_broker_reference = {
            position.broker_reference: position
            for position in local_positions
            if position.broker_reference is not None
        }

        broker_error: str | None = None
        remote_positions = []
        try:
            remote_positions = self.broker.get_positions()
        except Exception as exc:  # pragma: no cover - defensive recovery path
            broker_error = str(exc)
            logger.error(
                "Runtime recovery could not query broker positions",
                extra={
                    "error": broker_error,
                    "error_type": type(exc).__name__,
                    "event_category": "health",
                    "event_type": "health.runtime_recovery_failed",
                    "event_title": "Runtime recovery broker query failed",
                },
            )

        remote_by_broker_reference = {position.broker_reference: position for position in remote_positions}
        outcomes: list[dict[str, str]] = []

        for runtime in runtimes:
            runtime_manager.load_cached_price(
                runtime.instrument,
                price=runtime.last_price_seen,
                updated_at=runtime.last_price_seen_at,
            )

            if not runtime.auto_resume:
                self.runtime_state_service.mark_recovery_state(
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    recovery_state="PAUSED",
                    recovery_reason="Auto-resume disabled.",
                    status="STOPPED",
                    current_position_broker_reference=runtime.current_position_broker_reference,
                )
                outcomes.append(
                    {
                        "strategy": runtime.strategy_name,
                        "instrument": runtime.instrument,
                        "outcome": "paused",
                    }
                )
                continue

            local_position = self._resolve_local_position(runtime=runtime, local_by_key=local_by_key, local_by_broker_reference=local_by_broker_reference)
            remote_position = (
                remote_by_broker_reference.get(runtime.current_position_broker_reference)
                if runtime.current_position_broker_reference
                else None
            )

            if broker_error is not None:
                self.trade_service.record_reconciliation_event(
                    event_type="RUNTIME_RECOVERY_REQUIRED",
                    trade_intent_id=local_position.trade_intent_id if local_position is not None else None,
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    broker_reference=runtime.current_position_broker_reference,
                    local_position_id=local_position.id if local_position is not None else None,
                    details={"reason": f"Broker positions unavailable during startup recovery: {broker_error}"},
                )
                self.runtime_state_service.mark_recovery_state(
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    recovery_state="RECOVERY_REQUIRED",
                    recovery_reason=f"Broker positions unavailable during startup recovery: {broker_error}",
                    current_position_broker_reference=runtime.current_position_broker_reference,
                )
                outcomes.append(
                    {
                        "strategy": runtime.strategy_name,
                        "instrument": runtime.instrument,
                        "outcome": "recovery_required",
                    }
                )
                if "auth" in broker_error.lower():
                    domain_event_service.record_error(
                        error_type="BrokerAuthenticationFailed",
                        source="runtime_recovery_service.recover",
                        event_type="health.broker_auth_failed",
                        title="Broker authentication failed during recovery",
                        message=f"Runtime recovery could not verify broker state for {runtime.strategy_name} on {runtime.instrument}.",
                        runtime_id=runtime.runtime_id,
                        strategy_name=runtime.strategy_name,
                        instrument=runtime.instrument,
                        payload_json={"reason": broker_error},
                    )
                continue

            if runtime.current_position_broker_reference and remote_position is None:
                self.trade_service.record_reconciliation_event(
                    event_type="RUNTIME_RECOVERY_REQUIRED",
                    trade_intent_id=local_position.trade_intent_id if local_position is not None else None,
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    broker_reference=runtime.current_position_broker_reference,
                    local_position_id=local_position.id if local_position is not None else None,
                    details={"reason": "Persisted runtime references an open position that the broker did not confirm."},
                )
                self.runtime_state_service.mark_recovery_state(
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    recovery_state="RECOVERY_REQUIRED",
                    recovery_reason="Persisted runtime references an open position that the broker did not confirm.",
                    current_position_broker_reference=runtime.current_position_broker_reference,
                )
                outcomes.append(
                    {
                        "strategy": runtime.strategy_name,
                        "instrument": runtime.instrument,
                        "outcome": "recovery_required",
                    }
                )
                domain_event_service.record_event(
                    event_type="reconciliation.mismatch_detected",
                    category="reconciliation",
                    severity="warning",
                    source="runtime_recovery_service.recover",
                    title="Persisted runtime position was not confirmed by broker",
                    message=f"Startup recovery found no broker confirmation for {runtime.strategy_name} on {runtime.instrument}.",
                    runtime_id=runtime.runtime_id,
                    strategy_name=runtime.strategy_name,
                    instrument=runtime.instrument,
                    payload_json={
                        "broker_reference": runtime.current_position_broker_reference,
                        "reason": "Persisted runtime references an open position that the broker did not confirm.",
                    },
                )
                continue

            current_position = local_position
            if current_position is None and remote_position is not None:
                current_position = self._position_from_remote(runtime.strategy_name, remote_position)
                recovery_intent = self._resolve_recovered_trade_intent(runtime=runtime, position=current_position)
                current_position.trade_intent_id = recovery_intent.id
                current_position = self.trade_service.record_broker_position(current_position)
                self.trade_service.transition_trade_intent(
                    recovery_intent,
                    state=TradeIntentState.RECOVERED_POSITION_ATTACHED,
                    broker_reference=current_position.broker_reference,
                    position_id=current_position.id,
                    average_fill_price=current_position.open_price,
                    filled_size=current_position.size,
                    opened_at=current_position.open_time,
                )
            elif current_position is not None and (
                current_position.trade_intent_id is None
                or self.trade_service.get_trade_intent(current_position.trade_intent_id) is None
            ):
                recovery_intent = self._resolve_recovered_trade_intent(runtime=runtime, position=current_position)
                current_position.trade_intent_id = recovery_intent.id
                current_position = self.trade_service.upsert_position(current_position)
                self.trade_service.transition_trade_intent(
                    recovery_intent,
                    state=TradeIntentState.RECOVERED_POSITION_ATTACHED,
                    broker_reference=current_position.broker_reference,
                    position_id=current_position.id,
                    average_fill_price=current_position.open_price,
                    filled_size=current_position.size,
                    opened_at=current_position.open_time,
                )

            engine = runtime_manager.start(
                runtime.strategy_name,
                runtime.instrument,
                runtime_id=runtime.runtime_id,
                strategy_snapshot=runtime.strategy_state_snapshot,
                current_position=clone_position(current_position),
            )
            self.runtime_state_service.sync_engine_state(
                strategy_name=runtime.strategy_name,
                instrument=runtime.instrument,
                status="RUNNING",
                recovery_state="RUNNING",
                recovery_reason=None,
                auto_resume=runtime.auto_resume,
                started_at=runtime.started_at,
                last_price_seen=runtime.last_price_seen,
                last_price_seen_at=runtime.last_price_seen_at,
                current_position=clone_position(current_position),
                current_position_broker_reference=(
                    current_position.broker_reference if current_position is not None else None
                ),
            )
            outcomes.append(
                {
                    "strategy": runtime.strategy_name,
                    "instrument": runtime.instrument,
                    "outcome": "resumed" if current_position is not None else "running",
                }
            )
            domain_event_service.record_event(
                event_type="strategy.runtime_started",
                category="strategy",
                severity="info",
                source="runtime_recovery_service.recover",
                title="Persisted strategy runtime resumed",
                message=f"{runtime.strategy_name} resumed on {runtime.instrument} during startup recovery.",
                runtime_id=engine.runtime_id,
                strategy_name=runtime.strategy_name,
                instrument=runtime.instrument,
                position_id=current_position.id if current_position is not None else None,
                payload_json={
                    "recovered": True,
                    "has_position": current_position is not None,
                    "recovery_outcome": outcomes[-1]["outcome"],
                },
            )
            logger.info(
                "Recovered persisted runtime",
                extra={
                    "strategy": runtime.strategy_name,
                    "instrument": runtime.instrument,
                    "runtime_id": engine.runtime_id,
                    "has_position": current_position is not None,
                },
            )

        return outcomes

    @staticmethod
    def _resolve_local_position(
        *,
        runtime,
        local_by_key: dict[tuple[str, str], Position],
        local_by_broker_reference: dict[str, Position],
    ) -> Position | None:
        if runtime.current_position_broker_reference:
            position = local_by_broker_reference.get(runtime.current_position_broker_reference)
            if position is not None:
                return position
        return local_by_key.get((runtime.strategy_name, runtime.instrument))

    def _resolve_recovered_trade_intent(self, *, runtime, position: Position) -> TradeIntent:
        if position.trade_intent_id is not None:
            existing = self.trade_service.get_trade_intent(position.trade_intent_id)
            if existing is not None:
                return existing
        if position.broker_reference is not None:
            existing = self.trade_service.find_open_trade_intent(
                strategy_name=runtime.strategy_name,
                instrument=runtime.instrument,
                broker_reference=position.broker_reference,
                position_id=position.id,
            )
            if existing is not None:
                return existing
        return self.trade_service.create_trade_intent(
            TradeIntent(
                strategy_name=runtime.strategy_name,
                family_name=strategy_registry.get_metadata(runtime.strategy_name).family_name or runtime.strategy_name,
                instrument=runtime.instrument,
                direction=position.direction,
                state=TradeIntentState.RECOVERED_POSITION_ATTACHED.value,
                signal_time=position.open_time,
                proposed_size=position.size,
                allocated_size=position.size,
                proposed_risk_percent=position.risk_percent,
                allocated_risk_percent=position.risk_percent,
                risk_truth_confidence=position.risk_truth_confidence or "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
                observed_price=position.open_price,
                average_fill_price=position.open_price,
                filled_size=position.size,
                broker_reference=position.broker_reference,
                decision_reason_code="RECOVERED_POSITION_ATTACHED",
                decision_reason="Runtime recovery attached a broker-confirmed position to an explicit trade intent.",
                opened_at=position.open_time,
                details={"runtime_recovery_created": True},
            )
        )

    def _position_from_remote(self, strategy_name: str, remote_position) -> Position:
        now = datetime.now(UTC)
        family_name = strategy_registry.get_metadata(strategy_name).family_name or strategy_name
        return Position(
            strategy_name=strategy_name,
            family_name=family_name,
            broker_reference=remote_position.broker_reference,
            instrument=remote_position.instrument,
            direction=remote_position.direction.value,
            size=remote_position.size,
            open_price=remote_position.open_price,
            open_time=remote_position.opened_at,
            current_price=runtime_manager.get_last_price(remote_position.instrument) or remote_position.open_price,
            unrealized_pnl=0.0,
            risk_percent=None,
            risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
            reason="Recovered from persisted runtime and broker state",
            manual_override=False,
            account_type=self.broker.account_type.value,
            is_open=True,
            broker_sync_status="CONFIRMED",
            broker_open_confirmed_at=remote_position.opened_at,
            last_reconciled_at=utc_now(),
            created_at=now,
        )
