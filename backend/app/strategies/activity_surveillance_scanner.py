from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.strategies.base import PromotionIntent, ScreeningSnapshot, ScreeningStrategy


@dataclass(slots=True)
class ActivitySurveillanceScanner(ScreeningStrategy):
    name: ClassVar[str] = "activity_surveillance_scanner"
    tradable_threshold: float = 0.75
    requested_frequency: str = "2.0"

    def evaluate(self, snapshot: ScreeningSnapshot) -> PromotionIntent | None:
        details = snapshot.market_details
        if snapshot.streamed:
            return None
        if not details.tradable:
            return None
        market_status = (details.market_status or "").upper()
        if market_status not in {"TRADEABLE", "TRADEABLE_ONLINE"}:
            return None
        score = self._score(snapshot)
        if score < self.tradable_threshold:
            return None
        return PromotionIntent(
            scanner_name=self.name,
            instrument=snapshot.instrument,
            score=score,
            reason="activity_regime_alignment",
            requested_frequency=self.requested_frequency,
        )

    @staticmethod
    def _score(snapshot: ScreeningSnapshot) -> float:
        details = snapshot.market_details
        score = 0.45
        score += 0.2 if details.tradable else 0.0
        score += (
            0.1
            if (details.market_status or "").upper()
            in {"TRADEABLE", "TRADEABLE_ONLINE"}
            else 0.0
        )
        score += min(abs(details.percentage_change or 0.0) / 2.0, 0.2)
        if (
            details.bid is not None
            and details.offer is not None
            and details.offer > details.bid
        ):
            score += 0.05
        return round(min(score, 1.0), 4)
