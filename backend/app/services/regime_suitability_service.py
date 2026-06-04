from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from app.core.config import get_settings
from app.core.instrument_catalog import InstrumentDefinition, list_market_instruments
from app.services.health_service import get_health_service
from app.services.market_status_service import MarketStatus, get_market_status_service
from app.strategies.registry import StrategyMetadata


@dataclass(frozen=True, slots=True)
class DeploymentCandidate:
    instrument: str
    asset_class: str
    score: float
    market_status: MarketStatus
    reason: str


class RegimeSuitabilityService:
    ACTIVITY_SCORES = {"HIGH": 0.25, "MEDIUM": 0.15, "LOW": 0.05}
    HEALTH_SCORES = {"ok": 0.25, "degraded": 0.1, "critical": 0.0}

    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.market_status_service = get_market_status_service()
        self.health_service = get_health_service()

    def shortlist_candidates(
        self,
        *,
        metadata: StrategyMetadata,
        approved_asset_classes: list[str],
        approved_instruments: list[str],
    ) -> list[InstrumentDefinition]:
        explicit = {instrument for instrument in approved_instruments}
        allowed_asset_classes = {
            asset_class.upper() for asset_class in approved_asset_classes
        }
        family_asset_classes = {
            asset_class.upper() for asset_class in metadata.supported_asset_classes
        }
        definitions = list_market_instruments()
        if explicit:
            candidates = [
                definition for definition in definitions if definition.epic in explicit
            ]
        else:
            candidates = [
                definition
                for definition in definitions
                if (
                    definition.category.upper() in allowed_asset_classes
                    and definition.category.upper() in family_asset_classes
                )
            ]
        if not explicit and metadata.default_instrument not in {
            candidate.epic for candidate in candidates
        }:
            default_candidate = next(
                (
                    definition
                    for definition in definitions
                    if definition.epic == metadata.default_instrument
                ),
                None,
            )
            if default_candidate is not None:
                candidates.append(default_candidate)
        ranked = sorted(
            {candidate.epic: candidate for candidate in candidates}.values(),
            key=lambda definition: (
                -self.ACTIVITY_SCORES.get(definition.activity_level.upper(), 0.0),
                definition.epic != metadata.default_instrument,
                definition.epic,
            ),
        )
        return ranked[: self.settings.autonomous_candidate_instruments_per_family]

    def select_best_candidate(
        self,
        *,
        metadata: StrategyMetadata,
        approved_asset_classes: list[str],
        approved_instruments: list[str],
    ) -> DeploymentCandidate | None:
        health_status = str(
            self.health_service.get_health_report(session=self.session)["status"]
        )
        candidates = self.shortlist_candidates(
            metadata=metadata,
            approved_asset_classes=approved_asset_classes,
            approved_instruments=approved_instruments,
        )
        scored: list[DeploymentCandidate] = []
        for definition in candidates:
            market_status = self.market_status_service.get_status(definition.epic)
            score = self.ACTIVITY_SCORES.get(definition.activity_level.upper(), 0.0)
            score += self.HEALTH_SCORES.get(health_status, 0.0)
            if market_status.market_open:
                score += 0.2
            if market_status.tradable:
                score += 0.15
            if market_status.quote_fresh:
                score += 0.1
            if market_status.spread_ok:
                score += 0.1
            if market_status.dealing_allowed:
                score += 0.1
            reason = market_status.reason or "Instrument cleared suitability checks."
            scored.append(
                DeploymentCandidate(
                    instrument=definition.epic,
                    asset_class=definition.category.upper(),
                    score=round(score, 4),
                    market_status=market_status,
                    reason=reason,
                )
            )
        if not scored:
            return None
        return max(
            scored,
            key=lambda candidate: (
                candidate.score,
                candidate.instrument == metadata.default_instrument,
            ),
        )
