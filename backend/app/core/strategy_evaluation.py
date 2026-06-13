from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate, Strategy


class StrategyDecisionKind(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    kind: StrategyDecisionKind
    direction: OrderDirection | None = None
    hints: dict[str, Any] = field(default_factory=dict)


def evaluate_strategy_update(
    *,
    strategy: Strategy,
    update: PriceUpdate,
    has_open_position: bool,
    runtime_mode: str = "NORMAL",
) -> StrategyDecision | None:
    """Run the production strategy decision sequence for one market event."""

    strategy.on_price_update(update)
    if (
        runtime_mode != "EXITS_ONLY"
        and not has_open_position
        and strategy.should_enter_trade()
    ):
        return StrategyDecision(
            kind=StrategyDecisionKind.ENTRY,
            direction=strategy.entry_direction(),
            hints=dict(strategy.entry_signal_hints() or {}),
        )
    if has_open_position and strategy.should_exit_trade():
        return StrategyDecision(kind=StrategyDecisionKind.EXIT)
    return None
