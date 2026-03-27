from __future__ import annotations

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.models.trade import Position, clone_position, utc_now
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class ReconciliationService:
    """Synchronize local open positions against broker-truth positions."""

    def __init__(self, trade_service: TradeService):
        self.trade_service = trade_service
        self.broker = get_broker()
        self.runtime_state_service = RuntimeStateService(trade_service.session)

    def reconcile_open_positions(self) -> list[Position]:
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
        remote_by_broker_reference = {position.broker_reference: position for position in remote_positions}

        for remote_position in remote_positions:
            instrument = remote_position.instrument
            runtime_engines = runtime_manager.get_engines_for_instrument(instrument)
            local_position = local_by_broker_reference.get(remote_position.broker_reference)
            matching_engine = next(
                (
                    engine
                    for _, engine in runtime_engines
                    if engine.current_position is not None
                    and engine.current_position.broker_reference == remote_position.broker_reference
                ),
                None,
            )
            if local_position is None and matching_engine is None and len(runtime_engines) == 1:
                local_position = next(iter(local_by_instrument.get(instrument, [])), None)

            if local_position is not None:
                mapped_engine = runtime_manager.get_engine(local_position.strategy_name, instrument)
                if mapped_engine is not None:
                    matching_engine = mapped_engine

            strategy_name = (
                local_position.strategy_name
                if local_position
                else (matching_engine.strategy.name if matching_engine else "broker_sync")
            )
            persisted_id = local_position.id if local_position else None
            if persisted_id is None:
                runtime_position = local_by_runtime_key.get((strategy_name, instrument))
                if runtime_position is not None and runtime_position.broker_reference is None:
                    persisted_id = runtime_position.id
            runtime_manager.last_prices.setdefault(instrument, remote_position.open_price)
            synced_position = Position(
                id=persisted_id,
                strategy_name=strategy_name,
                broker_reference=remote_position.broker_reference,
                instrument=remote_position.instrument,
                direction=remote_position.direction.value,
                size=remote_position.size,
                open_price=remote_position.open_price,
                open_time=remote_position.opened_at,
                current_price=runtime_manager.get_last_price(instrument) or remote_position.open_price,
                unrealized_pnl=0.0,
                risk_percent=local_position.risk_percent if local_position else None,
                reason=local_position.reason if local_position else "Reconciled from broker",
                manual_override=local_position.manual_override if local_position else False,
                account_type=self.broker.account_type.value,
                is_open=True,
                broker_sync_status="CONFIRMED",
                broker_open_confirmed_at=remote_position.opened_at,
                last_reconciled_at=utc_now(),
            )
            persisted = self.trade_service.record_broker_position(synced_position)
            self.trade_service.record_reconciliation_event(
                event_type="POSITION_SYNCED_FROM_BROKER" if local_position is not None else "POSITION_ADOPTED_FROM_BROKER",
                strategy_name=strategy_name,
                instrument=instrument,
                broker_reference=remote_position.broker_reference,
                local_position_id=persisted.id,
                details={
                    "matched_local_position": local_position is not None,
                    "matched_runtime_engine": matching_engine is not None,
                    "size": remote_position.size,
                    "open_price": remote_position.open_price,
                },
            )
            if matching_engine is not None:
                matching_engine.current_position = clone_position(persisted)
                self.runtime_state_service.sync_engine_state(
                    strategy_name=matching_engine.strategy.name,
                    instrument=matching_engine.instrument,
                    status="RUNNING",
                    recovery_state="RUNNING",
                    last_price_seen=runtime_manager.get_last_price(instrument) or remote_position.open_price,
                    last_price_seen_at=runtime_manager.get_last_price_updated_at(instrument),
                    current_position=persisted,
                    current_position_broker_reference=persisted.broker_reference,
                )

        for local_position in local_positions:
            if local_position.broker_reference and local_position.broker_reference in remote_by_broker_reference:
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
            self.trade_service.record_reconciliation_event(
                event_type="LOCAL_POSITION_CLOSED_AFTER_BROKER_MISS",
                strategy_name=local_position.strategy_name,
                instrument=local_position.instrument,
                broker_reference=local_position.broker_reference,
                local_position_id=local_position.id,
                details={
                    "had_broker_reference": local_position.broker_reference is not None,
                    "close_price": local_position.current_price or local_position.open_price,
                },
            )
            runtime_engine = runtime_manager.get_engine(local_position.strategy_name, local_position.instrument)
            if runtime_engine is not None and runtime_engine.current_position is not None and (
                runtime_engine.current_position.broker_reference == local_position.broker_reference
                or (
                    runtime_engine.current_position.broker_reference is None
                    and local_position.broker_reference is None
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

        logger.info(
            "Broker reconciliation complete",
            extra={"remote_positions": len(remote_positions), "local_positions": len(local_positions)},
        )
        return self.trade_service.list_positions()
