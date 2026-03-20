from __future__ import annotations

from app.core.broker_factory import get_broker
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.models.trade import Position
from app.services.trade_service import TradeService

logger = get_logger(__name__)


class ReconciliationService:
    """Synchronize local open positions against broker-truth positions."""

    def __init__(self, trade_service: TradeService):
        self.trade_service = trade_service
        self.broker = get_broker()

    def reconcile_open_positions(self) -> list[Position]:
        remote_positions = self.broker.get_positions()
        local_positions = self.trade_service.list_all_open_positions()
        local_by_instrument = {position.instrument: position for position in local_positions}
        remote_by_instrument = {position.instrument: position for position in remote_positions}

        for instrument, remote_position in remote_by_instrument.items():
            runtime_engine = runtime_manager.engines.get(instrument)
            local_position = local_by_instrument.get(instrument)
            strategy_name = runtime_engine.strategy.name if runtime_engine else (local_position.strategy_name if local_position else "broker_sync")
            runtime_manager.last_prices.setdefault(instrument, remote_position.open_price)
            synced_position = Position(
                id=local_position.id if local_position else None,
                strategy_name=strategy_name,
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
            )
            persisted = self.trade_service.upsert_position(synced_position)
            if runtime_engine is not None:
                runtime_engine.current_position = persisted

        for instrument, local_position in local_by_instrument.items():
            if instrument in remote_by_instrument:
                continue
            local_position.is_open = False
            self.trade_service.close_position(local_position)
            runtime_engine = runtime_manager.engines.get(instrument)
            if runtime_engine is not None:
                runtime_engine.current_position = None

        logger.info(
            "Broker reconciliation complete",
            extra={"remote_positions": len(remote_positions), "local_positions": len(local_positions)},
        )
        return self.trade_service.list_positions()
