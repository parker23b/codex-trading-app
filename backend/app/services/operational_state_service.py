from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.runtime import runtime_manager
from app.models.runtime import StrategyRuntimeState
from app.services.health_service import get_health_service
from app.services.open_risk_authority_service import OpenRiskAuthorityService


class FeedSourceState(str, Enum):
    LIVE = "LIVE"
    POLLING_FALLBACK = "POLLING_FALLBACK"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"


class FeedHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class BrokerConnectivityState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class ExecutionEligibilityState(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


class OpenRiskManagementState(str, Enum):
    NO_OPEN_RISK = "NO_OPEN_RISK"
    MANAGED = "MANAGED"
    EXITS_ONLY = "EXITS_ONLY"
    UNMANAGED_OPEN_RISK = "UNMANAGED_OPEN_RISK"


class OperationalStateSnapshot(BaseModel):
    feed_source_state: FeedSourceState
    feed_health_state: FeedHealthState
    broker_connectivity_state: BrokerConnectivityState
    entry_eligible: bool
    exit_eligible: bool
    entry_eligibility_state: ExecutionEligibilityState
    exit_eligibility_state: ExecutionEligibilityState
    entry_block_reason: str | None
    exit_block_reason: str | None
    open_risk_management_state: OpenRiskManagementState
    open_risk_management_reason: str | None
    open_risk_authority_version: int | None = None
    open_risk_authority_updated_at: datetime | None = None
    open_risk_reconciliation_status: str | None = None


def get_operational_streaming_service():
    from app.services.ig_streaming_service import get_ig_streaming_service

    return get_ig_streaming_service()


class OperationalStateService:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.health_service = get_health_service()

    def get_summary(self) -> OperationalStateSnapshot:
        now = datetime.now(UTC)
        health_details = self.health_service.get_system_health()
        stream_health = get_operational_streaming_service().get_health()
        return self._build_summary(
            broker_connected=bool(health_details.broker_connected),
            price_updated_at=health_details.last_price_update,
            stream_tick_at=stream_health.last_tick_at,
            stream_connected=bool(health_details.stream_connected)
            and bool(stream_health.connected),
            now=now,
        )

    def get_summary_for_instrument(self, instrument: str) -> OperationalStateSnapshot:
        now = datetime.now(UTC)
        health_details = self.health_service.get_system_health()
        stream_health = get_operational_streaming_service().get_health()
        return self._build_summary(
            broker_connected=bool(health_details.broker_connected),
            price_updated_at=(
                runtime_manager.get_last_price_updated_at(instrument)
                or self._get_runtime_last_price_seen_at(instrument)
            ),
            stream_tick_at=get_operational_streaming_service().get_last_tick_at(
                instrument
            ),
            stream_connected=bool(health_details.stream_connected)
            and bool(stream_health.connected),
            now=now,
        )

    def _build_summary(
        self,
        *,
        broker_connected: bool,
        price_updated_at: datetime | None,
        stream_tick_at: datetime | None,
        stream_connected: bool,
        now: datetime,
    ) -> OperationalStateSnapshot:
        price_fresh = self._is_fresh(price_updated_at, now)
        live_stream_fresh = stream_connected and self._is_fresh(stream_tick_at, now)

        if live_stream_fresh:
            feed_source_state = FeedSourceState.LIVE
        elif broker_connected and price_fresh and not live_stream_fresh:
            feed_source_state = FeedSourceState.POLLING_FALLBACK
        elif price_updated_at is not None:
            feed_source_state = FeedSourceState.STALE
        else:
            feed_source_state = FeedSourceState.DISCONNECTED

        if feed_source_state is FeedSourceState.LIVE:
            feed_health_state = FeedHealthState.HEALTHY
        elif feed_source_state in {
            FeedSourceState.POLLING_FALLBACK,
            FeedSourceState.STALE,
        }:
            feed_health_state = FeedHealthState.DEGRADED
        else:
            feed_health_state = FeedHealthState.FAILED

        broker_connectivity_state = (
            BrokerConnectivityState.CONNECTED
            if broker_connected
            else BrokerConnectivityState.DISCONNECTED
        )
        entry_eligible = (
            broker_connectivity_state is BrokerConnectivityState.CONNECTED
            and feed_source_state is FeedSourceState.LIVE
            and feed_health_state is FeedHealthState.HEALTHY
            and price_fresh
        )
        exit_eligible = (
            broker_connectivity_state is BrokerConnectivityState.CONNECTED
            and price_fresh
            and feed_source_state
            in {FeedSourceState.LIVE, FeedSourceState.POLLING_FALLBACK}
        )

        authority = self._open_risk_authority()
        return OperationalStateSnapshot(
            feed_source_state=feed_source_state,
            feed_health_state=feed_health_state,
            broker_connectivity_state=broker_connectivity_state,
            entry_eligible=entry_eligible,
            exit_eligible=exit_eligible,
            entry_eligibility_state=(
                ExecutionEligibilityState.ALLOWED
                if entry_eligible
                else ExecutionEligibilityState.BLOCKED
            ),
            exit_eligibility_state=(
                ExecutionEligibilityState.ALLOWED
                if exit_eligible
                else ExecutionEligibilityState.BLOCKED
            ),
            entry_block_reason=self._entry_block_reason(
                broker_connected=broker_connected,
                price_fresh=price_fresh,
                feed_source_state=feed_source_state,
            ),
            exit_block_reason=self._exit_block_reason(
                broker_connected=broker_connected,
                price_fresh=price_fresh,
                feed_source_state=feed_source_state,
            ),
            open_risk_management_state=OpenRiskManagementState(authority.state),
            open_risk_management_reason=authority.reason,
            open_risk_authority_version=authority.version,
            open_risk_authority_updated_at=authority.updated_at,
            open_risk_reconciliation_status=authority.reconciliation_status,
        )

    def _entry_block_reason(
        self,
        *,
        broker_connected: bool,
        price_fresh: bool,
        feed_source_state: FeedSourceState,
    ) -> str | None:
        if not broker_connected:
            return "broker_disconnected"
        if feed_source_state is FeedSourceState.DISCONNECTED:
            return "data_disconnected"
        if not price_fresh:
            return "stale_price_data"
        if feed_source_state is FeedSourceState.POLLING_FALLBACK:
            return "polling_fallback_active"
        if feed_source_state is FeedSourceState.STALE:
            return "stale_price_data"
        return None

    def _exit_block_reason(
        self,
        *,
        broker_connected: bool,
        price_fresh: bool,
        feed_source_state: FeedSourceState,
    ) -> str | None:
        if not broker_connected:
            return "broker_disconnected"
        if feed_source_state is FeedSourceState.DISCONNECTED:
            return "data_disconnected"
        if not price_fresh:
            return "stale_price_data"
        return None

    def _is_fresh(self, value: datetime | None, now: datetime) -> bool:
        if value is None:
            return False
        normalized = (
            value.astimezone(UTC)
            if value.tzinfo is not None
            else value.replace(tzinfo=UTC)
        )
        age_ms = (now - normalized).total_seconds() * 1000
        return age_ms <= self.settings.max_price_age_ms

    def _get_runtime_last_price_seen_at(self, instrument: str) -> datetime | None:
        if self.session is None:
            return None
        runtime = self.session.exec(
            select(StrategyRuntimeState.last_price_seen_at)
            .where(StrategyRuntimeState.instrument == instrument)
            .where(StrategyRuntimeState.status == "RUNNING")
            .order_by(StrategyRuntimeState.updated_at.desc())
            .limit(1)
        ).first()
        return runtime

    def _open_risk_authority(self):
        if self.session is None:
            from app.models.open_risk_authority import OpenRiskAuthority

            return OpenRiskAuthority(version=1)
        return OpenRiskAuthorityService(self.session).get_or_derive()
