from __future__ import annotations

from pydantic import BaseModel
from sqlmodel import Session, select

from app.models.domain_event import DomainEvent
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position, ReconciliationEvent, Trade, TradeIntent


class HistoryResetSummary(BaseModel):
    trades_deleted: int
    trade_intents_deleted: int
    executions_deleted: int
    reconciliation_events_deleted: int
    domain_events_deleted: int
    reviews_deleted: int
    closed_positions_deleted: int
    idle_runtimes_deleted: int


class HistoryResetService:
    def __init__(self, session: Session):
        self.session = session

    def clear_test_history(self) -> HistoryResetSummary:
        closed_positions = self.session.exec(select(Position).where(Position.is_open.is_(False))).all()
        idle_runtimes = self.session.exec(select(StrategyRuntimeState).where(StrategyRuntimeState.status != "RUNNING")).all()
        trades = self.session.exec(select(Trade)).all()
        trade_intents = self.session.exec(select(TradeIntent)).all()
        executions = self.session.exec(select(Execution)).all()
        reconciliation_events = self.session.exec(select(ReconciliationEvent)).all()
        domain_events = self.session.exec(select(DomainEvent)).all()
        reviews = self.session.exec(select(GeneratedReviewRecord)).all()

        for row in closed_positions:
            self.session.delete(row)
        for row in idle_runtimes:
            self.session.delete(row)
        for row in trades:
            self.session.delete(row)
        for row in trade_intents:
            self.session.delete(row)
        for row in executions:
            self.session.delete(row)
        for row in reconciliation_events:
            self.session.delete(row)
        for row in domain_events:
            self.session.delete(row)
        for row in reviews:
            self.session.delete(row)

        self.session.commit()

        return HistoryResetSummary(
            trades_deleted=len(trades),
            trade_intents_deleted=len(trade_intents),
            executions_deleted=len(executions),
            reconciliation_events_deleted=len(reconciliation_events),
            domain_events_deleted=len(domain_events),
            reviews_deleted=len(reviews),
            closed_positions_deleted=len(closed_positions),
            idle_runtimes_deleted=len(idle_runtimes),
        )
