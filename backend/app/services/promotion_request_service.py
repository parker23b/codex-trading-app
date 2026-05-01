from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models.promotion_request import PromotionRequest, PromotionRequestStatus


class PromotionRequestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_refresh(
        self,
        *,
        instrument: str,
        source: str,
        reason: str,
        score: float,
        requested_at: datetime,
        expires_at: datetime | None,
        market_status: str | None,
        tradable: bool | None,
        requested_frequency: str | None,
    ) -> PromotionRequest:
        existing = self._find_active_request(
            instrument=instrument, source=source, requested_at=requested_at
        )
        if existing is None:
            request = PromotionRequest(
                instrument=instrument,
                source=source,
                reason=reason,
                score=score,
                status=PromotionRequestStatus.PENDING.value,
                requested_at=requested_at,
                expires_at=expires_at,
                market_status=market_status,
                tradable=tradable,
                requested_frequency=requested_frequency,
                updated_at=requested_at,
            )
            self.session.add(request)
            self.session.commit()
            self.session.refresh(request)
            return request

        existing.reason = reason
        existing.score = max(existing.score, score)
        existing.expires_at = expires_at
        existing.market_status = market_status
        existing.tradable = tradable
        existing.requested_frequency = requested_frequency
        existing.updated_at = requested_at
        self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing

    def _find_active_request(
        self,
        *,
        instrument: str,
        source: str,
        requested_at: datetime,
    ) -> PromotionRequest | None:
        statement = (
            select(PromotionRequest)
            .where(PromotionRequest.instrument == instrument)
            .where(PromotionRequest.source == source)
            .where(PromotionRequest.status == PromotionRequestStatus.PENDING.value)
        )
        candidates = self.session.exec(statement).all()
        now = requested_at.astimezone(UTC)
        for candidate in candidates:
            if candidate.expires_at is None:
                return candidate
            expires_at = (
                candidate.expires_at.replace(tzinfo=UTC)
                if candidate.expires_at.tzinfo is None
                else candidate.expires_at.astimezone(UTC)
            )
            if expires_at >= now:
                return candidate
            candidate.status = PromotionRequestStatus.EXPIRED.value
            candidate.updated_at = requested_at
            self.session.add(candidate)
        self.session.commit()
        return None
