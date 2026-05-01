from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.promotion_request import PromotionRequest, PromotionRequestStatus
from app.models.watchlist import WatchlistEntry, WatchlistStatus
from app.services.domain_event_service import domain_event_service
from app.services.watchlist_service import WatchlistService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CoverageAllocationResult:
    accepted: int
    rejected: int
    expired: int
    skipped: int


class CoverageAllocatorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.watchlist_service = WatchlistService(session)

    def allocate_pending_promotions(
        self, *, now: datetime | None = None
    ) -> CoverageAllocationResult:
        decided_at = self._as_utc(now) or datetime.now(UTC)
        requests = list(
            self.session.exec(
                select(PromotionRequest).where(
                    PromotionRequest.status == PromotionRequestStatus.PENDING.value
                )
            ).all()
        )
        requests.sort(
            key=lambda request: (-request.score, request.requested_at, request.id or 0)
        )

        accepted = 0
        rejected = 0
        expired = 0
        skipped = 0
        accepted_recently = self._accepted_in_last_minute(decided_at)
        remaining_budget = max(
            self.settings.ig_streaming_max_promotions_per_minute - accepted_recently, 0
        )

        for request in requests:
            expires_at = self._as_utc(request.expires_at)
            if expires_at is not None and expires_at < decided_at:
                request.status = PromotionRequestStatus.EXPIRED.value
                request.updated_at = decided_at
                self.session.add(request)
                expired += 1
                continue

            watchlist_entry = self.session.exec(
                select(WatchlistEntry).where(
                    WatchlistEntry.instrument == request.instrument
                )
            ).first()
            if self._is_already_streamed(
                watchlist_entry=watchlist_entry, now=decided_at
            ):
                request.status = PromotionRequestStatus.ACCEPTED.value
                request.updated_at = decided_at
                self.session.add(request)
                skipped += 1
                continue

            if not self._passes_thresholds(request=request):
                self._reject_request(
                    request=request,
                    decided_at=decided_at,
                    reason_code="score_below_threshold",
                )
                rejected += 1
                continue

            if not self._passes_cooldown(
                watchlist_entry=watchlist_entry, now=decided_at
            ):
                self._reject_request(
                    request=request,
                    decided_at=decided_at,
                    reason_code="instrument_cooldown_active",
                )
                rejected += 1
                continue

            if remaining_budget <= 0:
                self._reject_request(
                    request=request,
                    decided_at=decided_at,
                    reason_code="promotion_budget_exhausted",
                )
                rejected += 1
                continue

            self.watchlist_service.promote_instrument(
                instrument=request.instrument,
                promoted_at=decided_at,
                expires_at=expires_at
                or (
                    decided_at
                    + timedelta(seconds=self.settings.tier2_promotion_ttl_seconds)
                ),
                score=request.score,
                requested_frequency=request.requested_frequency
                or self.settings.ig_streaming_requested_frequency,
                reason="promotion_accepted",
            )
            request.status = PromotionRequestStatus.ACCEPTED.value
            request.updated_at = decided_at
            self.session.add(request)
            domain_event_service.record_event(
                event_type="coverage.promotion_accepted",
                category="coverage",
                severity="info",
                source="coverage_allocator.allocate_pending_promotions",
                title="Promotion request accepted",
                message=f"{request.instrument} promoted into Tier 1 coverage.",
                instrument=request.instrument,
                actor_type="service",
                actor_id="coverage_allocator",
                payload_json={
                    "promotion_request_id": request.id,
                    "score": request.score,
                },
                created_at=decided_at,
            )
            accepted += 1
            remaining_budget -= 1

        self.session.commit()
        return CoverageAllocationResult(
            accepted=accepted, rejected=rejected, expired=expired, skipped=skipped
        )

    def _accepted_in_last_minute(self, now: datetime) -> int:
        cutoff = now - timedelta(minutes=1)
        accepted_requests = self.session.exec(
            select(PromotionRequest).where(
                PromotionRequest.status == PromotionRequestStatus.ACCEPTED.value
            )
        ).all()
        return len(
            [
                request
                for request in accepted_requests
                if self._as_utc(request.updated_at) is not None
                and self._as_utc(request.updated_at) >= cutoff
            ]
        )

    def _is_already_streamed(
        self, *, watchlist_entry: WatchlistEntry | None, now: datetime
    ) -> bool:
        if watchlist_entry is None:
            return False
        if (
            watchlist_entry.tier != "TIER1"
            or watchlist_entry.status != WatchlistStatus.ACTIVE.value
        ):
            return False
        promotion_expires_at = self._as_utc(watchlist_entry.promotion_expires_at)
        if watchlist_entry.pinned:
            return True
        if (
            watchlist_entry.reason == "promotion_accepted"
            and promotion_expires_at is not None
            and promotion_expires_at < now
        ):
            return False
        return True

    def _passes_thresholds(self, *, request: PromotionRequest) -> bool:
        return request.score >= self.settings.tier2_promotion_score_threshold

    def _passes_cooldown(
        self, *, watchlist_entry: WatchlistEntry | None, now: datetime
    ) -> bool:
        if watchlist_entry is None:
            return True
        cooldown_until = self._as_utc(watchlist_entry.cooldown_until)
        if cooldown_until is None:
            return True
        return cooldown_until <= now

    def _reject_request(
        self, *, request: PromotionRequest, decided_at: datetime, reason_code: str
    ) -> None:
        request.status = PromotionRequestStatus.REJECTED.value
        request.updated_at = decided_at
        self.session.add(request)
        domain_event_service.record_event(
            event_type="coverage.promotion_rejected",
            category="coverage",
            severity="info",
            source="coverage_allocator.allocate_pending_promotions",
            title="Promotion request rejected",
            message=f"Promotion request rejected for {request.instrument}.",
            instrument=request.instrument,
            actor_type="service",
            actor_id="coverage_allocator",
            payload_json={
                "promotion_request_id": request.id,
                "score": request.score,
                "reason_code": reason_code,
            },
            created_at=decided_at,
        )

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
