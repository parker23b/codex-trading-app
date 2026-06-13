from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Iterator

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.session import engine
from app.models.runtime_leadership import RuntimeLease


@dataclass(frozen=True, slots=True)
class RuntimeLeaseAcquisition:
    acquired: bool
    owner_id: str
    current_owner_id: str | None
    generation: int | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActiveRuntimeLeadership:
    owner_id: str
    generation: int


class RuntimeLeadershipFenceError(RuntimeError):
    pass


_ACTIVE_RUNTIME_LEADERSHIP: ActiveRuntimeLeadership | None = None
_ACTIVE_RUNTIME_LEADERSHIP_LOCK = RLock()


def activate_runtime_leadership(*, owner_id: str, generation: int) -> None:
    global _ACTIVE_RUNTIME_LEADERSHIP
    with _ACTIVE_RUNTIME_LEADERSHIP_LOCK:
        _ACTIVE_RUNTIME_LEADERSHIP = ActiveRuntimeLeadership(
            owner_id=owner_id,
            generation=generation,
        )


def deactivate_runtime_leadership(
    *, owner_id: str, generation: int | None = None
) -> None:
    global _ACTIVE_RUNTIME_LEADERSHIP
    with _ACTIVE_RUNTIME_LEADERSHIP_LOCK:
        active = _ACTIVE_RUNTIME_LEADERSHIP
        if active is None or active.owner_id != owner_id:
            return
        if generation is not None and active.generation != generation:
            return
        _ACTIVE_RUNTIME_LEADERSHIP = None


@contextmanager
def hold_active_runtime_leadership_fence() -> Iterator[ActiveRuntimeLeadership]:
    """Hold the lease row against takeover for one real broker mutation."""

    with _ACTIVE_RUNTIME_LEADERSHIP_LOCK:
        active = _ACTIVE_RUNTIME_LEADERSHIP
    if active is None:
        raise RuntimeLeadershipFenceError(
            "Real broker mutation requires active runtime leadership."
        )

    with engine.connect() as connection:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
        try:
            statement = (
                select(
                    RuntimeLease.owner_id,
                    RuntimeLease.generation,
                    RuntimeLease.expires_at,
                    RuntimeLease.released_at,
                )
                .where(
                    RuntimeLease.lease_name
                    == RuntimeLeadershipService.RUNTIME_LEASE_NAME
                )
                .with_for_update()
            )
            lease = connection.execute(statement).mappings().one_or_none()
            now = datetime.now(UTC)
            if (
                lease is None
                or lease["owner_id"] != active.owner_id
                or lease["generation"] != active.generation
                or lease["released_at"] is not None
                or _as_utc(lease["expires_at"]) <= now
            ):
                raise RuntimeLeadershipFenceError(
                    "Runtime leadership changed before broker mutation."
                )
            yield active
            connection.commit()
        except Exception:
            connection.rollback()
            raise


class RuntimeLeadershipService:
    RUNTIME_LEASE_NAME = "runtime-autonomy"
    DEFAULT_TTL = timedelta(seconds=15)

    def __init__(self, session: Session, *, owner_id: str):
        self.session = session
        self.owner_id = owner_id

    def acquire(
        self,
        *,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> RuntimeLeaseAcquisition:
        timestamp = _as_utc(now)
        lease_ttl = ttl or self.DEFAULT_TTL
        expires_at = timestamp + lease_ttl
        lease = RuntimeLease(
            lease_name=self.RUNTIME_LEASE_NAME,
            owner_id=self.owner_id,
            generation=1,
            acquired_at=timestamp,
            heartbeat_at=timestamp,
            expires_at=expires_at,
            released_at=None,
        )
        self.session.add(lease)
        try:
            self.session.commit()
            return RuntimeLeaseAcquisition(
                acquired=True,
                owner_id=self.owner_id,
                current_owner_id=self.owner_id,
                generation=1,
                expires_at=expires_at,
            )
        except IntegrityError:
            self.session.rollback()

        return self._take_existing_lease(now=timestamp, ttl=lease_ttl)

    def renew(
        self,
        *,
        generation: int,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> bool:
        timestamp = _as_utc(now)
        lease_ttl = ttl or self.DEFAULT_TTL
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(RuntimeLease.owner_id == self.owner_id)
            .where(RuntimeLease.generation == generation)
            .where(RuntimeLease.released_at.is_(None))
            .where(RuntimeLease.expires_at > timestamp)
            .values(heartbeat_at=timestamp, expires_at=timestamp + lease_ttl)
        )
        self.session.commit()
        return result.rowcount == 1

    def release(self, *, generation: int, now: datetime | None = None) -> bool:
        timestamp = _as_utc(now)
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(RuntimeLease.owner_id == self.owner_id)
            .where(RuntimeLease.generation == generation)
            .where(RuntimeLease.released_at.is_(None))
            .values(released_at=timestamp, expires_at=timestamp)
        )
        self.session.commit()
        return result.rowcount == 1

    def _take_existing_lease(
        self, *, now: datetime, ttl: timedelta
    ) -> RuntimeLeaseAcquisition:
        expires_at = now + ttl
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(
                or_(
                    RuntimeLease.owner_id == self.owner_id,
                    RuntimeLease.released_at.is_not(None),
                    RuntimeLease.expires_at <= now,
                )
            )
            .values(
                owner_id=self.owner_id,
                generation=RuntimeLease.generation + 1,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
                released_at=None,
            )
        )
        if result.rowcount == 1:
            self.session.commit()
            lease = self.session.get(RuntimeLease, self.RUNTIME_LEASE_NAME)
            return RuntimeLeaseAcquisition(
                acquired=True,
                owner_id=self.owner_id,
                current_owner_id=self.owner_id,
                generation=lease.generation if lease is not None else None,
                expires_at=expires_at,
            )
        self.session.rollback()
        lease = self.session.get(RuntimeLease, self.RUNTIME_LEASE_NAME)
        return RuntimeLeaseAcquisition(
            acquired=False,
            owner_id=self.owner_id,
            current_owner_id=lease.owner_id if lease is not None else None,
            generation=lease.generation if lease is not None else None,
            expires_at=lease.expires_at if lease is not None else None,
        )


def _as_utc(value: datetime | None = None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
