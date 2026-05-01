from __future__ import annotations

from collections import Counter

from sqlmodel import Session, desc, select

from app.models.domain_event import DomainEvent
from app.models.promotion_request import PromotionRequest
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier
from app.services.market_status_service import get_market_status_service
from app.services.watchlist_service import WatchlistService


class CoverageService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.watchlist_service = WatchlistService(session)

    def get_summary(self) -> dict[str, object]:
        streaming_plan = self.watchlist_service.get_streaming_plan()
        tier2_plan = self.watchlist_service.get_tier2_refresh_plan()
        watchlist_entries = list(
            self.session.exec(
                select(WatchlistEntry).where(
                    WatchlistEntry.status == WatchlistStatus.ACTIVE.value
                )
            ).all()
        )
        promotion_requests = list(
            self.session.exec(
                select(PromotionRequest)
                .order_by(desc(PromotionRequest.updated_at))
                .limit(12)
            ).all()
        )
        promotion_counts = Counter(request.status for request in promotion_requests)
        allocator_events = list(
            self.session.exec(
                select(DomainEvent)
                .where(
                    DomainEvent.event_type.in_(
                        [
                            "strategy.trade_allocator_selected",
                            "strategy.trade_allocator_rejected",
                        ]
                    )
                )
                .order_by(desc(DomainEvent.created_at), desc(DomainEvent.id))
                .limit(20)
            ).all()
        )
        allocator_counts = Counter(event.event_type for event in allocator_events)
        allocator_reason_counts = Counter(
            str((event.payload_json or {}).get("reason_code") or "unknown")
            for event in allocator_events
        )

        tier1_entries = [
            entry
            for entry in watchlist_entries
            if entry.tier == WatchlistTier.TIER1.value
            and entry.status == WatchlistStatus.ACTIVE.value
        ]
        tier2_entries = [
            entry
            for entry in watchlist_entries
            if entry.tier == WatchlistTier.TIER2.value
            and entry.status == WatchlistStatus.ACTIVE.value
        ]

        return {
            "streaming": {
                "active_instruments": [
                    self._serialize_watchlist_entry(
                        entry, streamed=entry.instrument in streaming_plan.instruments
                    )
                    for entry in sorted(
                        tier1_entries,
                        key=lambda item: (
                            0 if item.pinned else 1,
                            -item.priority_score,
                            item.instrument,
                        ),
                    )
                ],
                "execution_readiness": [
                    get_market_status_service()
                    .get_status(entry.instrument)
                    .model_dump()
                    for entry in sorted(
                        tier1_entries,
                        key=lambda item: (
                            0 if item.pinned else 1,
                            -item.priority_score,
                            item.instrument,
                        ),
                    )
                ],
                "desired_instruments": list(streaming_plan.instruments),
                "pinned_instruments": list(streaming_plan.pinned_instruments),
                "capped_instruments": list(streaming_plan.capped_instruments),
                "asset_class_usage": streaming_plan.asset_class_usage,
            },
            "tier2": {
                "refresh_queue": list(tier2_plan.instruments),
                "active_candidates": [
                    self._serialize_watchlist_entry(entry, streamed=False)
                    for entry in sorted(
                        tier2_entries,
                        key=lambda item: (-item.priority_score, item.instrument),
                    )
                ],
            },
            "promotions": {
                "pending_count": promotion_counts.get("PENDING", 0),
                "accepted_count": promotion_counts.get("ACCEPTED", 0),
                "rejected_count": promotion_counts.get("REJECTED", 0),
                "expired_count": promotion_counts.get("EXPIRED", 0),
                "recent_requests": [
                    self._serialize_promotion_request(request)
                    for request in promotion_requests
                ],
            },
            "trade_allocator": {
                "selected_count": allocator_counts.get(
                    "strategy.trade_allocator_selected", 0
                ),
                "rejected_count": allocator_counts.get(
                    "strategy.trade_allocator_rejected", 0
                ),
                "reason_counts": dict(allocator_reason_counts),
                "recent_decisions": [
                    self._serialize_allocator_event(event) for event in allocator_events
                ],
            },
        }

    @staticmethod
    def _serialize_watchlist_entry(
        entry: WatchlistEntry, *, streamed: bool
    ) -> dict[str, object]:
        return {
            "instrument": entry.instrument,
            "tier": entry.tier,
            "status": entry.status,
            "asset_class": entry.asset_class,
            "pinned": entry.pinned,
            "reason": entry.reason,
            "priority_score": entry.priority_score,
            "requested_frequency": entry.requested_frequency,
            "promotion_expires_at": entry.promotion_expires_at,
            "last_streamed_at": entry.last_streamed_at,
            "last_refreshed_at": entry.last_refreshed_at,
            "streamed": streamed,
        }

    @staticmethod
    def _serialize_promotion_request(request: PromotionRequest) -> dict[str, object]:
        return {
            "id": request.id,
            "instrument": request.instrument,
            "source": request.source,
            "reason": request.reason,
            "score": request.score,
            "status": request.status,
            "requested_at": request.requested_at,
            "expires_at": request.expires_at,
            "market_status": request.market_status,
            "tradable": request.tradable,
            "requested_frequency": request.requested_frequency,
            "updated_at": request.updated_at,
        }

    @staticmethod
    def _serialize_allocator_event(event: DomainEvent) -> dict[str, object]:
        payload = event.payload_json or {}
        return {
            "id": event.id,
            "created_at": event.created_at,
            "event_type": event.event_type,
            "selected": event.event_type == "strategy.trade_allocator_selected",
            "strategy_name": event.strategy_name,
            "instrument": event.instrument,
            "reason_code": payload.get("reason_code"),
            "reason": payload.get("reason"),
            "score": payload.get("score"),
            "direction": payload.get("direction"),
            "source_tier": payload.get("source_tier"),
        }
