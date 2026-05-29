from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.process_identity import get_process_identity
from app.db.session import engine
from app.models.observability import ObservabilityState
from app.models.runtime_leadership import RuntimeLease

logger = get_logger(__name__)


OBSERVABILITY_MODE_AGGREGATED = "AGGREGATED"
OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK = "LOCAL_ONLY_FALLBACK"
OBSERVABILITY_STATE_AUDIT_WRITE = "audit_write_degraded"
OBSERVABILITY_STATE_POLLING_FALLBACK = "polling_fallback_active"
OBSERVABILITY_STATE_STREAM_STALE = "stream_stale"
OBSERVABILITY_STATE_STREAM_CONNECTION = "stream_connection"
OBSERVABILITY_STATE_RUNTIME_PAUSED = "runtime_paused_by_health"


@dataclass(frozen=True, slots=True)
class RuntimeLeaderSnapshot:
    owner_id: str | None
    heartbeat_at: datetime | None
    expires_at: datetime | None
    stale: bool


class ObservabilityStateService:
    SYSTEM_SCOPE = "SYSTEM"
    INSTRUMENT_SCOPE = "INSTRUMENT"
    GLOBAL_SCOPE_ID = "global"
    ACTIVE_STATUS = "ACTIVE"
    CLEARED_STATUS = "CLEARED"

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    @classmethod
    def record_state(
        cls,
        *,
        state_key: str,
        source: str,
        active: bool,
        observed_at: datetime | None = None,
        expires_at: datetime | None = None,
        scope_type: str = SYSTEM_SCOPE,
        scope_id: str = GLOBAL_SCOPE_ID,
        payload: dict[str, Any] | None = None,
        worker_id: str | None = None,
        hostname: str | None = None,
        process_id: int | None = None,
    ) -> bool:
        identity = get_process_identity()
        resolved_worker_id = worker_id or identity.worker_id
        resolved_hostname = hostname or identity.hostname
        resolved_process_id = process_id or identity.process_id
        timestamp = cls._as_utc(observed_at)
        with Session(engine) as session:
            statement = select(ObservabilityState).where(
                ObservabilityState.state_key == state_key,
                ObservabilityState.scope_type == scope_type,
                ObservabilityState.scope_id == scope_id,
                ObservabilityState.worker_id == resolved_worker_id,
            )
            record = session.exec(statement).first()
            if record is None:
                record = ObservabilityState(
                    state_key=state_key,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    worker_id=resolved_worker_id,
                    hostname=resolved_hostname,
                    process_id=resolved_process_id,
                    source=source,
                    status=cls.ACTIVE_STATUS if active else cls.CLEARED_STATUS,
                    observed_at=timestamp,
                    expires_at=expires_at,
                    payload_json=payload or {},
                )
            else:
                record.hostname = resolved_hostname
                record.process_id = resolved_process_id
                record.source = source
                record.status = cls.ACTIVE_STATUS if active else cls.CLEARED_STATUS
                record.observed_at = timestamp
                record.expires_at = expires_at
                record.payload_json = payload or {}
            try:
                session.add(record)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "Failed to persist observability state",
                    extra={
                        "state_key": state_key,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "worker_id": resolved_worker_id,
                    },
                )
                return False
        return True

    def list_states(self) -> list[ObservabilityState]:
        if self.session is None:
            with Session(engine) as session:
                return list(session.exec(select(ObservabilityState)))
        return list(self.session.exec(select(ObservabilityState)))

    def get_runtime_leader_snapshot(
        self, *, now: datetime | None = None
    ) -> RuntimeLeaderSnapshot:
        timestamp = self._as_utc(now)
        try:
            lease = None
            if self.session is None:
                with Session(engine) as session:
                    lease = session.get(RuntimeLease, "runtime-autonomy")
            else:
                lease = self.session.get(RuntimeLease, "runtime-autonomy")
        except Exception:
            logger.exception("Failed to load runtime leader snapshot")
            return RuntimeLeaderSnapshot(
                owner_id=None,
                heartbeat_at=None,
                expires_at=None,
                stale=False,
            )
        if lease is None or lease.released_at is not None:
            return RuntimeLeaderSnapshot(
                owner_id=None,
                heartbeat_at=None,
                expires_at=None,
                stale=False,
            )
        expires_at = self._as_utc(lease.expires_at)
        heartbeat_at = self._as_utc(lease.heartbeat_at)
        return RuntimeLeaderSnapshot(
            owner_id=lease.owner_id,
            heartbeat_at=heartbeat_at,
            expires_at=expires_at,
            stale=expires_at < timestamp,
        )

    def build_summary(
        self,
        *,
        now: datetime,
        local_details: Any,
        stale_runtime_count: int,
        stale_price_runtime_count: int,
        local_stream_degraded: bool,
        local_polling_fallback_active: bool,
    ) -> dict[str, Any]:
        try:
            return self._build_aggregated_summary(
                now=now,
                local_details=local_details,
                stale_runtime_count=stale_runtime_count,
                stale_price_runtime_count=stale_price_runtime_count,
                local_stream_degraded=local_stream_degraded,
                local_polling_fallback_active=local_polling_fallback_active,
            )
        except Exception:
            logger.exception("Falling back to local-only observability summary")
            return self._build_local_fallback_summary(
                now=now,
                local_details=local_details,
                stale_runtime_count=stale_runtime_count,
                stale_price_runtime_count=stale_price_runtime_count,
                local_stream_degraded=local_stream_degraded,
                local_polling_fallback_active=local_polling_fallback_active,
            )

    def _build_aggregated_summary(
        self,
        *,
        now: datetime,
        local_details: Any,
        stale_runtime_count: int,
        stale_price_runtime_count: int,
        local_stream_degraded: bool,
        local_polling_fallback_active: bool,
    ) -> dict[str, Any]:
        states = self.list_states()
        leader = self.get_runtime_leader_snapshot(now=now)
        observation_dicts = [self._serialize_state(state, now=now) for state in states]
        current_identity = get_process_identity()
        if local_details.audit_write_failures_last_5m > 0 and not any(
            observation["state_key"] == OBSERVABILITY_STATE_AUDIT_WRITE
            and observation["worker_id"] == current_identity.worker_id
            and observation["stale"] is False
            for observation in observation_dicts
        ):
            observation_dicts.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
                    now=local_details.last_audit_write_failure or now,
                    source="health_service.local_overlay",
                    payload={
                        "failure_count_window": local_details.audit_write_failures_last_5m
                    },
                )
            )
        if local_details.strategies_paused_by_health > 0 and not any(
            observation["state_key"] == OBSERVABILITY_STATE_RUNTIME_PAUSED
            and observation["worker_id"] == current_identity.worker_id
            and observation["stale"] is False
            for observation in observation_dicts
        ):
            observation_dicts.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_RUNTIME_PAUSED,
                    now=now,
                    source="health_service.local_overlay",
                    payload={"paused_count": local_details.strategies_paused_by_health},
                )
            )
        latest_update_at = max(
            (state["observed_at"] for state in observation_dicts),
            default=None,
        )
        active_states = [state for state in observation_dicts if not state["stale"]]
        active_audit_states = [
            state
            for state in active_states
            if state["state_key"] == OBSERVABILITY_STATE_AUDIT_WRITE
            and state["status"] == self.ACTIVE_STATUS
        ]
        active_polling_states = [
            state
            for state in active_states
            if state["state_key"] == OBSERVABILITY_STATE_POLLING_FALLBACK
            and state["status"] == self.ACTIVE_STATUS
        ]
        active_stale_stream_states = [
            state
            for state in active_states
            if state["state_key"] == OBSERVABILITY_STATE_STREAM_STALE
            and state["status"] == self.ACTIVE_STATUS
        ]
        active_stream_connection_states = [
            state
            for state in active_states
            if state["state_key"] == OBSERVABILITY_STATE_STREAM_CONNECTION
        ]
        active_runtime_pause_states = [
            state
            for state in active_states
            if state["state_key"] == OBSERVABILITY_STATE_RUNTIME_PAUSED
            and state["status"] == self.ACTIVE_STATUS
        ]
        aggregated_audit_failures = sum(
            int(state["payload"].get("failure_count_window") or 1)
            for state in active_audit_states
        )
        active_polling_instruments = sorted(
            {
                str(state["scope_id"])
                for state in active_polling_states
                if state["scope_type"] == self.INSTRUMENT_SCOPE
            }
        )
        polling_fallback_instrument_count = len(active_polling_instruments)
        if polling_fallback_instrument_count == 0:
            polling_fallback_instrument_count = max(
                local_details.polling_fallback_active_instrument_count, 0
            )
        active_stale_instruments = sorted(
            {
                str(state["scope_id"])
                for state in active_stale_stream_states
                if state["scope_type"] == self.INSTRUMENT_SCOPE
            }
        )
        stale_stream_instrument_count = len(active_stale_instruments)
        if stale_stream_instrument_count == 0:
            stale_stream_instrument_count = max(
                local_details.stale_stream_instrument_count, 0
            )
        disconnected_stream_observed = any(
            not bool(state["payload"].get("connected", True))
            for state in active_stream_connection_states
        )
        runtime_pause_count = sum(
            int(state["payload"].get("paused_count") or 0)
            for state in active_runtime_pause_states
        )
        audit_write_degraded = bool(active_audit_states)
        polling_fallback_active = (
            polling_fallback_instrument_count > 0 or local_polling_fallback_active
        )
        stream_degraded = (
            local_stream_degraded
            or disconnected_stream_observed
            or polling_fallback_instrument_count > 0
            or stale_stream_instrument_count > 0
        )
        runtime_degraded = (
            stale_runtime_count > 0
            or stale_price_runtime_count > 0
            or runtime_pause_count > 0
        )
        degradation_reasons = []
        if audit_write_degraded:
            degradation_reasons.append("audit_write_degraded")
        if not local_details.broker_connected:
            degradation_reasons.append("broker_disconnected")
        if polling_fallback_active:
            degradation_reasons.append("polling_fallback_active")
        if stale_stream_instrument_count > 0:
            degradation_reasons.append("stream_stale")
        elif stream_degraded:
            degradation_reasons.append("stream_degraded")
        if stale_runtime_count > 0:
            degradation_reasons.append("runtime_heartbeat_stale")
        if stale_price_runtime_count > 0:
            degradation_reasons.append("runtime_price_stale")
        if runtime_pause_count > 0:
            degradation_reasons.append("runtime_paused_or_restricted")
        return {
            "mode": OBSERVABILITY_MODE_AGGREGATED,
            "aggregation_available": True,
            "local_details_scope": "CURRENT_PROCESS",
            "degradation_scope": OBSERVABILITY_MODE_AGGREGATED,
            "current_process": asdict(get_process_identity()),
            "runtime_leader": asdict(leader),
            "last_aggregate_update_at": latest_update_at,
            "active_observation_count": len(active_states),
            "stale_observation_count": len(observation_dicts) - len(active_states),
            "observations": observation_dicts,
            "audit_write_degraded": audit_write_degraded,
            "audit_write_failures_last_5m": aggregated_audit_failures,
            "last_audit_write_failure": max(
                (state["observed_at"] for state in active_audit_states),
                default=local_details.last_audit_write_failure,
            ),
            "polling_fallback_active": polling_fallback_active,
            "polling_fallback_active_instrument_count": polling_fallback_instrument_count,
            "stale_stream_instrument_count": stale_stream_instrument_count,
            "stream_degraded": stream_degraded,
            "runtime_degraded": runtime_degraded,
            "degradation_reasons": degradation_reasons,
        }

    def _build_local_fallback_summary(
        self,
        *,
        now: datetime,
        local_details: Any,
        stale_runtime_count: int,
        stale_price_runtime_count: int,
        local_stream_degraded: bool,
        local_polling_fallback_active: bool,
    ) -> dict[str, Any]:
        leader = self.get_runtime_leader_snapshot(now=now)
        identity = get_process_identity()
        observations = []
        if local_details.audit_write_failures_last_5m > 0:
            observations.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_AUDIT_WRITE,
                    now=now,
                    source="health_service.local_fallback",
                    payload={
                        "failure_count_window": local_details.audit_write_failures_last_5m,
                    },
                )
            )
        if (
            local_details.polling_fallback_active_instrument_count > 0
            or local_polling_fallback_active
        ):
            observations.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_POLLING_FALLBACK,
                    now=now,
                    source="health_service.local_fallback",
                    payload={
                        "instrument_count": local_details.polling_fallback_active_instrument_count,
                    },
                )
            )
        if local_details.stale_stream_instrument_count > 0:
            observations.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_STREAM_STALE,
                    now=now,
                    source="health_service.local_fallback",
                    payload={
                        "instrument_count": local_details.stale_stream_instrument_count,
                    },
                )
            )
        if local_details.strategies_paused_by_health > 0:
            observations.append(
                self._synthetic_local_observation(
                    state_key=OBSERVABILITY_STATE_RUNTIME_PAUSED,
                    now=now,
                    source="health_service.local_fallback",
                    payload={"paused_count": local_details.strategies_paused_by_health},
                )
            )
        degradation_reasons = []
        if local_details.audit_write_failures_last_5m > 0:
            degradation_reasons.append("audit_write_degraded")
        if not local_details.broker_connected:
            degradation_reasons.append("broker_disconnected")
        if (
            local_details.polling_fallback_active_instrument_count > 0
            or local_polling_fallback_active
        ):
            degradation_reasons.append("polling_fallback_active")
        if local_details.stale_stream_instrument_count > 0:
            degradation_reasons.append("stream_stale")
        elif local_stream_degraded:
            degradation_reasons.append("stream_degraded")
        if stale_runtime_count > 0:
            degradation_reasons.append("runtime_heartbeat_stale")
        if stale_price_runtime_count > 0:
            degradation_reasons.append("runtime_price_stale")
        if local_details.strategies_paused_by_health > 0:
            degradation_reasons.append("runtime_paused_or_restricted")
        return {
            "mode": OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK,
            "aggregation_available": False,
            "local_details_scope": "CURRENT_PROCESS",
            "degradation_scope": OBSERVABILITY_MODE_LOCAL_ONLY_FALLBACK,
            "current_process": asdict(identity),
            "runtime_leader": asdict(leader),
            "last_aggregate_update_at": None,
            "active_observation_count": len(observations),
            "stale_observation_count": 0,
            "observations": observations,
            "audit_write_degraded": local_details.audit_write_failures_last_5m > 0,
            "audit_write_failures_last_5m": local_details.audit_write_failures_last_5m,
            "last_audit_write_failure": local_details.last_audit_write_failure,
            "polling_fallback_active": (
                local_details.polling_fallback_active_instrument_count > 0
                or local_polling_fallback_active
            ),
            "polling_fallback_active_instrument_count": local_details.polling_fallback_active_instrument_count,
            "stale_stream_instrument_count": local_details.stale_stream_instrument_count,
            "stream_degraded": local_stream_degraded,
            "runtime_degraded": (
                stale_runtime_count > 0
                or stale_price_runtime_count > 0
                or local_details.strategies_paused_by_health > 0
            ),
            "degradation_reasons": degradation_reasons,
        }

    def _serialize_state(
        self, state: ObservabilityState, *, now: datetime
    ) -> dict[str, Any]:
        expires_at = self._as_utc(state.expires_at) if state.expires_at else None
        observed_at = self._as_utc(state.observed_at)
        return {
            "state_key": state.state_key,
            "scope_type": state.scope_type,
            "scope_id": state.scope_id,
            "worker_id": state.worker_id,
            "hostname": state.hostname,
            "process_id": state.process_id,
            "source": state.source,
            "status": state.status,
            "observed_at": observed_at,
            "expires_at": expires_at,
            "stale": expires_at is not None and expires_at < now,
            "payload": dict(state.payload_json or {}),
        }

    def _synthetic_local_observation(
        self,
        *,
        state_key: str,
        now: datetime,
        source: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        identity = get_process_identity()
        return {
            "state_key": state_key,
            "scope_type": self.SYSTEM_SCOPE,
            "scope_id": self.GLOBAL_SCOPE_ID,
            "worker_id": identity.worker_id,
            "hostname": identity.hostname,
            "process_id": identity.process_id,
            "source": source,
            "status": self.ACTIVE_STATUS,
            "observed_at": now,
            "expires_at": None,
            "stale": False,
            "payload": payload,
        }

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        timestamp = value or datetime.now(UTC)
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    @staticmethod
    def default_ttl(seconds: float) -> timedelta:
        return timedelta(seconds=seconds)
